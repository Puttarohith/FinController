from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from rapidfuzz import fuzz

from .audit import AuditEntry


AMOUNT_TOLERANCE = 1.0
AUTO_RESOLVE_THRESHOLD = 0.95
AI_VERIFY_MIN = 0.85
NEEDS_REVIEW_MIN = 0.60


@dataclass
class ReconciliationRecord:
    payment_id: str
    order_id: str | None
    status: str
    exception_type: str | None
    order_amount: float | None
    razorpay_net_amount: float | None
    bank_settled_amount: float | None
    discrepancy: float
    method: str
    confidence: float
    reason: str
    source_order: dict[str, Any] | None = None
    source_razorpay: dict[str, Any] | None = None
    source_bank: dict[str, Any] | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["confidence"] = round(float(data["confidence"]), 4)
        data["discrepancy"] = round(float(data["discrepancy"]), 2)
        return data


@dataclass
class ReconciliationReport:
    run_id: str
    run_at: str
    total_records: int
    matched: int
    exceptions: int
    match_rate: float
    total_razorpay_net: float
    total_bank_settled: float
    total_discrepancy: float
    records: list[dict]
    exception_summary: dict[str, int]
    audits: list[dict]
    processing_time_ms: float
    records_per_second: float


def reconcile(data_dir: str | Path, bank_df: pd.DataFrame | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    run_at = datetime.now(timezone.utc).isoformat()
    data_dir = Path(data_dir)
    audits: list[AuditEntry] = []

    orders, order_errors = _safe_read_csv(data_dir / "orders.csv", "orders")
    ledger, ledger_errors = _safe_read_csv(data_dir / "razorpay_ledger.csv", "razorpay")
    if bank_df is not None:
        bank = bank_df.copy()
        bank_errors = []
    else:
        bank, bank_errors = _safe_read_csv(data_dir / "bank_settlement.csv", "bank")
    parse_errors = order_errors + ledger_errors + bank_errors

    orders = _normalize(orders, ["amount"], ["created_at"])
    ledger = _normalize(ledger, ["amount", "fees", "tax", "net_amount"], ["captured_at"])
    bank = _normalize(bank, ["settled_amount"], ["settlement_date"])

    records: list[ReconciliationRecord] = []
    used_bank_rows: set[int] = set()

    if not bank.empty:
        duplicate_ids = bank["payment_id"][bank["payment_id"].duplicated(keep=False)].unique().tolist()
        for dup_pid in duplicate_ids:
            duplicate_rows = bank[bank["payment_id"] == dup_pid]
            for idx in duplicate_rows.index:
                used_bank_rows.add(idx)
            row = duplicate_rows.iloc[0]
            pid = str(row.get("payment_id", "")).strip()
            rec = _record(
                pid,
                row.get("order_id"),
                "UNABLE_TO_RESOLVE",
                "DUPLICATE_BANK",
                None,
                None,
                row.get("settled_amount"),
                row.get("settled_amount", 0),
                "deterministic",
                1.0,
                "Unable to resolve: duplicate bank payment_id has multiple bank rows and was not auto-reconciled.",
                None,
                None,
                row.to_dict(),
                {"duplicate": True, "duplicate_count": int(len(duplicate_rows))},
            )
            records.append(rec)
            audits.append(_audit(rec, f"duplicate_count={len(duplicate_rows)}"))

    bank_eligible = bank.drop(index=list(used_bank_rows), errors="ignore")
    ledger_by_pid = {str(row["payment_id"]): row for _, row in ledger.iterrows()}
    order_by_pid = {str(row["payment_id"]): row for _, row in orders.iterrows()}
    bank_by_pid = {str(row["payment_id"]): (idx, row) for idx, row in bank_eligible.iterrows()}

    for pid, lrow in ledger_by_pid.items():
        order = order_by_pid.get(pid)
        if str(lrow.get("status", "")).lower() == "failed":
            rec = _record(
                pid,
                lrow.get("order_id"),
                "UNABLE_TO_RESOLVE",
                "FAILED",
                _maybe_amount(order, "amount"),
                lrow.get("net_amount"),
                None,
                0,
                "deterministic",
                1.0,
                "Unable to resolve: failed payment is excluded from settlement.",
                _maybe_dict(order),
                lrow.to_dict(),
                None,
                {"ledger_status": "failed"},
            )
            records.append(rec)
            audits.append(_audit(rec, "ledger_status=failed"))
            continue

        if pid in bank_by_pid:
            idx, brow = bank_by_pid[pid]
            used_bank_rows.add(idx)
            rec = _classify_exact(pid, order, lrow, brow)
            records.append(rec)
            audits.append(_audit(rec, f"amount_delta={rec.discrepancy:.2f}, id_similarity=1.00, date_delta={_date_delta(lrow, brow)}d"))

    unmatched_ledger = [
        (pid, row)
        for pid, row in ledger_by_pid.items()
        if not any(record.payment_id == pid for record in records)
    ]
    unmatched_bank = [
        (idx, row)
        for idx, row in bank_eligible.iterrows()
        if idx not in used_bank_rows
    ]

    for pid, lrow in unmatched_ledger:
        order = order_by_pid.get(pid)
        candidate = _best_fuzzy_candidate(pid, lrow, unmatched_bank)
        if candidate:
            idx, brow, score, signals = candidate
            if score >= AUTO_RESOLVE_THRESHOLD:
                used_bank_rows.add(idx)
                rec = _matched_record(pid, order, lrow, brow, "fuzzy", score, "Fuzzy evidence reconciled payment above auto threshold.", signals)
                records.append(rec)
                audits.append(_audit(rec, _signals_text(signals)))
                continue
            if score >= AI_VERIFY_MIN:
                verdict = _ai_verify(lrow.to_dict(), brow.to_dict(), signals)
                if verdict["verdict"] == "match" and verdict["confidence"] >= AI_VERIFY_MIN:
                    used_bank_rows.add(idx)
                    rec = _matched_record(
                        pid,
                        order,
                        lrow,
                        brow,
                        "ai",
                        min(float(verdict["confidence"]), score),
                        verdict["reason"],
                        {**signals, "ai_verdict": verdict},
                    )
                    records.append(rec)
                    audits.append(_audit(rec, _signals_text(signals)))
                    continue
                rec = _record(
                    pid,
                    lrow.get("order_id"),
                    "UNABLE_TO_RESOLVE",
                    "INSUFFICIENT_EVIDENCE",
                    _maybe_amount(order, "amount"),
                    lrow.get("net_amount"),
                    brow.get("settled_amount"),
                    _discrepancy(lrow, brow),
                    "ai",
                    float(verdict.get("confidence", score)),
                    f"Unable to resolve: {verdict.get('reason', 'AI verification did not confirm a match.')}",
                    _maybe_dict(order),
                    lrow.to_dict(),
                    brow.to_dict(),
                    {**signals, "ai_verdict": verdict},
                )
                records.append(rec)
                audits.append(_audit(rec, _signals_text(signals)))
                continue
            if score >= NEEDS_REVIEW_MIN:
                rec = _record(
                    pid,
                    lrow.get("order_id"),
                    "UNABLE_TO_RESOLVE",
                    "INSUFFICIENT_EVIDENCE",
                    _maybe_amount(order, "amount"),
                    lrow.get("net_amount"),
                    brow.get("settled_amount"),
                    _discrepancy(lrow, brow),
                    "fuzzy",
                    score,
                    "Unable to resolve: fuzzy evidence requires human review.",
                    _maybe_dict(order),
                    lrow.to_dict(),
                    brow.to_dict(),
                    signals,
                )
                records.append(rec)
                audits.append(_audit(rec, _signals_text(signals)))
                continue

        rec = _record(
            pid,
            lrow.get("order_id"),
            "UNABLE_TO_RESOLVE",
            "MISSING_IN_BANK",
            _maybe_amount(order, "amount"),
            lrow.get("net_amount"),
            None,
            lrow.get("net_amount", 0),
            "deterministic",
            1.0,
            "Unable to resolve: captured Razorpay payment has no bank settlement.",
            _maybe_dict(order),
            lrow.to_dict(),
            None,
            {"missing_bank": True},
        )
        records.append(rec)
        audits.append(_audit(rec, "bank_record=missing"))

    for idx, brow in bank_eligible.iterrows():
        if idx in used_bank_rows:
            continue
        pid = str(brow.get("payment_id", "")).strip()
        exception = "REFUND_MISSING" if brow.get("credit_debit") == "DR" else "GHOST_ENTRY"
        rec = _record(
            pid,
            None,
            "UNABLE_TO_RESOLVE",
            exception,
            None,
            None,
            brow.get("settled_amount"),
            brow.get("settled_amount", 0),
            "deterministic",
            1.0,
            f"Unable to resolve: bank {'refund debit' if exception == 'REFUND_MISSING' else 'credit'} has no eligible Razorpay match.",
            None,
            None,
            brow.to_dict(),
            {"orphan_bank_row": True},
        )
        records.append(rec)
        audits.append(_audit(rec, "razorpay_record=missing"))

    for error in parse_errors:
        rec = _record(
            error["payment_id"],
            None,
            "UNABLE_TO_RESOLVE",
            "PARSE_ERROR",
            None,
            None,
            None,
            0,
            "deterministic",
            1.0,
            f"Unable to resolve: malformed {error['source']} row was quarantined.",
            None,
            None,
            error,
            {"parse_error": error},
        )
        records.append(rec)
        audits.append(_audit(rec, "parse_error=true"))

    record_dicts = [record.to_dict() for record in sorted(records, key=lambda item: item.payment_id)]
    
    # ── AI Fraud & Anomaly Detection ──────────────────────────────────────────
    from .fraud_detector import detect_anomalies
    fraud_alerts = detect_anomalies(record_dicts)

    # ── Dispute Aging & Analytics ──────────────────────────────────────────────
    from .analytics import calculate_dispute_analytics
    analytics = calculate_dispute_analytics(record_dicts)

    matched = sum(1 for record in record_dicts if record["status"] == "MATCHED")
    exceptions = len(record_dicts) - matched
    exception_summary: dict[str, int] = {}
    for record in record_dicts:
        if record["exception_type"]:
            exception_summary[record["exception_type"]] = exception_summary.get(record["exception_type"], 0) + 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    report_dict = asdict(ReconciliationReport(
        run_id=str(uuid.uuid4()),
        run_at=run_at,
        total_records=len(record_dicts),
        matched=matched,
        exceptions=exceptions,
        match_rate=matched / len(record_dicts) if record_dicts else 0,
        total_razorpay_net=round(float(ledger.get("net_amount", pd.Series(dtype=float)).sum()), 2),
        total_bank_settled=round(float(bank.get("settled_amount", pd.Series(dtype=float)).sum()), 2),
        total_discrepancy=round(sum(abs(record["discrepancy"]) for record in record_dicts if record["status"] != "MATCHED"), 2),
        records=record_dicts,
        exception_summary=exception_summary,
        audits=[audit.to_dict() for audit in audits],
        processing_time_ms=round(elapsed_ms, 2),
        records_per_second=round(len(record_dicts) / (elapsed_ms / 1000), 2) if elapsed_ms else 0,
    ))

    report_dict["fraud_alerts"] = fraud_alerts
    report_dict["fraud_count"] = len(fraud_alerts)
    report_dict["analytics"] = analytics
    return report_dict


def _safe_read_csv(path: Path, source: str) -> tuple[pd.DataFrame, list[dict]]:
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception as exc:
        return pd.DataFrame(), [{"source": source, "payment_id": f"parse_error_{source}", "error": str(exc)}]
    errors = []
    malformed = df[df.apply(lambda row: all(str(value).strip() == "" for value in row), axis=1)]
    for idx, row in malformed.iterrows():
        errors.append({"source": source, "payment_id": f"parse_error_{source}_{idx}", "raw": row.to_dict()})
    df = df.drop(index=malformed.index)
    return df, errors


def _normalize(df: pd.DataFrame, amount_cols: list[str], date_cols: list[str]) -> pd.DataFrame:
    df = df.copy()
    for col in df.columns:
        df[col] = df[col].map(lambda value: value.strip() if isinstance(value, str) else value)
    for col in amount_cols:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    for col in date_cols:
        if col in df:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date.astype(str)
    return df


def _classify_exact(pid: str, order: pd.Series | None, lrow: pd.Series, brow: pd.Series) -> ReconciliationRecord:
    delta = _discrepancy(lrow, brow)
    if brow.get("credit_debit") == "DR":
        return _record(pid, lrow.get("order_id"), "UNABLE_TO_RESOLVE", "REFUND_MISSING", _maybe_amount(order, "amount"), lrow.get("net_amount"), brow.get("settled_amount"), delta, "deterministic", 1.0, "Unable to resolve: bank has a refund debit instead of settlement credit.", _maybe_dict(order), lrow.to_dict(), brow.to_dict(), {"credit_debit": "DR"})
    if abs(delta) <= AMOUNT_TOLERANCE:
        date_delta_days = _date_delta(lrow, brow)
        evidence: dict[str, Any] = {"amount_delta": delta, "id_similarity": 1.0, "date_delta_days": date_delta_days}
        if date_delta_days > 3:
            evidence["late_settlement_warning"] = True
            evidence["late_settlement_days"] = date_delta_days
        return _matched_record(pid, order, lrow, brow, "deterministic", 1.0, "Exact payment_id, amount, and settlement evidence matched.", evidence)
    return _record(pid, lrow.get("order_id"), "UNABLE_TO_RESOLVE", "AMOUNT_MISMATCH", _maybe_amount(order, "amount"), lrow.get("net_amount"), brow.get("settled_amount"), delta, "deterministic", 1.0, "Unable to resolve: bank settled amount differs from Razorpay net amount beyond INR 1.00.", _maybe_dict(order), lrow.to_dict(), brow.to_dict(), {"amount_delta": delta})


def _matched_record(pid: str, order: pd.Series | None, lrow: pd.Series, brow: pd.Series, method: str, confidence: float, reason: str, evidence: dict[str, Any]) -> ReconciliationRecord:
    return _record(pid, lrow.get("order_id"), "MATCHED", None, _maybe_amount(order, "amount"), lrow.get("net_amount"), brow.get("settled_amount"), _discrepancy(lrow, brow), method, confidence, reason, _maybe_dict(order), lrow.to_dict(), brow.to_dict(), evidence)


def _record(payment_id: str, order_id: Any, status: str, exception_type: str | None, order_amount: Any, rz_net: Any, bank_amount: Any, discrepancy: Any, method: str, confidence: float, reason: str, order: dict | None, rz: dict | None, bank: dict | None, evidence: dict[str, Any]) -> ReconciliationRecord:
    return ReconciliationRecord(str(payment_id), None if pd.isna(order_id) else str(order_id), status, exception_type, _float_or_none(order_amount), _float_or_none(rz_net), _float_or_none(bank_amount), float(discrepancy or 0), method, confidence, reason, order, rz, bank, evidence)


def _best_fuzzy_candidate(pid: str, lrow: pd.Series, bank_rows: list[tuple[int, pd.Series]]) -> tuple[int, pd.Series, float, dict[str, Any]] | None:
    best = None
    for idx, brow in bank_rows:
        if brow.get("credit_debit") == "DR":
            continue
        amount_delta = abs(_discrepancy(lrow, brow))
        if amount_delta > AMOUNT_TOLERANCE:
            continue
        date_delta = _date_delta(lrow, brow)
        if date_delta > 5:
            continue
        id_similarity = fuzz.ratio(pid, str(brow.get("payment_id", ""))) / 100
        order_similarity = fuzz.partial_ratio(str(lrow.get("order_id", "")), str(brow.get("narration", ""))) / 100
        narration_similarity = fuzz.partial_ratio(pid, str(brow.get("narration", ""))) / 100
        date_score = max(0.0, 1 - (date_delta / 5))
        score = (id_similarity * 0.5) + (order_similarity * 0.2) + (narration_similarity * 0.15) + (date_score * 0.15)
        signals = {
            "amount_delta": round(amount_delta, 2),
            "id_similarity": round(id_similarity, 4),
            "order_similarity": round(order_similarity, 4),
            "narration_similarity": round(narration_similarity, 4),
            "date_delta_days": date_delta,
            "candidate_bank_payment_id": str(brow.get("payment_id", "")),
        }
        if best is None or score > best[2]:
            best = (idx, brow, round(score, 4), signals)
    return best


def _ai_verify(rz: dict[str, Any], bank: dict[str, Any], signals: dict[str, Any]) -> dict[str, Any]:
    fallback = {
        "verdict": "match" if signals.get("id_similarity", 0) >= 0.85 and signals.get("amount_delta", 99) <= AMOUNT_TOLERANCE else "insufficient_evidence",
        "confidence": max(float(signals.get("id_similarity", 0)), 0.85),
        "reason": "Deterministic fallback verified fuzzy ID, amount, and date signals because Claude was unavailable.",
    }
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return fallback
    schema = {"verdict": "match|no_match|insufficient_evidence", "confidence": "0.0-1.0", "reason": "one sentence"}
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={
                "model": "claude-3-5-sonnet-20241022",
                "max_tokens": 160,
                "temperature": 0,
                "system": "Return only valid JSON matching the requested schema. Never invent financial facts.",
                "messages": [{"role": "user", "content": json.dumps({"schema": schema, "razorpay": rz, "bank": bank, "signals": signals})}],
            },
            timeout=8,
        )
        response.raise_for_status()
        parsed = json.loads(response.json()["content"][0]["text"])
        if parsed.get("verdict") not in {"match", "no_match", "insufficient_evidence"}:
            raise ValueError("invalid verdict")
        confidence = float(parsed.get("confidence"))
        if not 0 <= confidence <= 1:
            raise ValueError("invalid confidence")
        return {"verdict": parsed["verdict"], "confidence": confidence, "reason": str(parsed.get("reason", "No reason supplied."))[:240]}
    except Exception:
        return fallback


def _safe_date(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _date_delta(lrow: pd.Series, brow: pd.Series) -> int:
    left = _safe_date(lrow.get("captured_at"))
    right = _safe_date(brow.get("settlement_date"))
    if not left or not right:
        return 99
    return abs((right.date() - left.date()).days)


def _discrepancy(lrow: pd.Series, brow: pd.Series) -> float:
    return round(float(lrow.get("net_amount", 0) or 0) - float(brow.get("settled_amount", 0) or 0), 2)


def _maybe_dict(row: pd.Series | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return row.to_dict()


def _maybe_amount(row: pd.Series | None, col: str) -> float | None:
    if row is None:
        return None
    return _float_or_none(row.get(col))


def _float_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return round(float(value), 2)
    except Exception:
        return None


def _signals_text(signals: dict[str, Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in signals.items() if key != "ai_verdict")


def _audit(record: ReconciliationRecord, signals: str) -> AuditEntry:
    return AuditEntry.create(record.payment_id, record.status if not record.exception_type else record.exception_type, record.confidence, signals, record.reason, record.method)
