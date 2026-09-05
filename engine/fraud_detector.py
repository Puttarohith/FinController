from __future__ import annotations

from typing import Any
from rapidfuzz import fuzz


def detect_anomalies(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Evaluates reconciliation records against 3 AI Fraud vectors."""
    fraud_alerts = []

    # 1. Velocity Checks (Detecting rapid duplicate refunds or duplicate attempts within batch)
    payment_ids = [r["payment_id"] for r in records]
    pid_counts: dict[str, int] = {}
    for pid in payment_ids:
        pid_counts[pid] = pid_counts.get(pid, 0) + 1

    for record in records:
        pid = record["payment_id"]
        anomalies = []
        disc = abs(record.get("discrepancy") or 0)
        exc = record.get("exception_type")
        bank_info = record.get("source_bank") or {}
        order_info = record.get("source_order") or {}

        # Vector 1: Velocity Check (Duplicate entries)
        if pid_counts.get(pid, 0) > 1 or exc == "DUPLICATE_BANK":
            anomalies.append({
                "type": "HIGH_VELOCITY_ALERT",
                "severity": "HIGH",
                "description": "Multiple settlement attempts detected for single Payment ID within short window."
            })

        # Vector 2: Beneficiary Name Mismatch
        user_name = str(order_info.get("customer_name") or order_info.get("user_name") or "").strip()
        account_holder = str(bank_info.get("narration") or bank_info.get("account_holder") or "").strip()
        if user_name and account_holder and len(user_name) > 3 and len(account_holder) > 3:
            ratio = fuzz.partial_ratio(user_name.lower(), account_holder.lower()) / 100.0
            if ratio < 0.40:
                anomalies.append({
                    "type": "BENEFICIARY_MISMATCH",
                    "severity": "MEDIUM",
                    "description": f"Customer name '{user_name}' does not align with bank narration '{account_holder}' (Match: {ratio:.0%})."
                })

        # Vector 3: High-Value Suspicious Ghost Credit (>₹25,000)
        if exc == "GHOST_ENTRY" or (record.get("bank_settled_amount") or 0) > 25000:
            bank_amt = record.get("bank_settled_amount") or 0
            if bank_amt > 25000:
                anomalies.append({
                    "type": "SUSPICIOUS_GHOST_CREDIT",
                    "severity": "CRITICAL",
                    "description": f"Unmatched high-value bank credit of ₹{bank_amt:,.2f} (>₹25,000 threshold) detected with no Razorpay ledger entry."
                })

        record["anomalies"] = anomalies
        record["is_fraud_suspect"] = len(anomalies) > 0
        if anomalies:
            fraud_alerts.append({
                "payment_id": pid,
                "anomalies": anomalies,
                "discrepancy": disc
            })

    return fraud_alerts
