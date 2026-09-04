from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from engine.metrics import evaluate, print_metrics
from engine.qa_agent import FinBot
from engine.reconciler import reconcile


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
STATIC = ROOT / "static"

app = Flask(__name__, static_folder=str(STATIC))
CORS(app)


def _run_reconciliation() -> tuple[dict, FinBot]:
    """Run reconciliation + evaluation and return (report, bot)."""
    report = reconcile(DATA)
    metrics = evaluate(report, DATA)
    report["metrics"] = metrics
    bot = FinBot(report)
    return report, bot


# ── Boot-time reconciliation ────────────────────────────────────────────────
try:
    REPORT, BOT = _run_reconciliation()
    print(
        f"Reconciliation complete: matched={REPORT['matched']} "
        f"exceptions={REPORT['exceptions']} "
        f"match_rate={REPORT['match_rate']:.2%}"
    )
    print_metrics(REPORT["metrics"])
except Exception as exc:
    print(f"[WARNING] Boot-time reconciliation failed: {exc}")
    print("Server is still starting — run /api/rerun once data files are ready.")
    REPORT = {
        "error": str(exc),
        "records": [],
        "audits": [],
        "matched": 0,
        "exceptions": 0,
        "match_rate": 0,
        "total_records": 0,
        "total_razorpay_net": 0,
        "total_bank_settled": 0,
        "total_discrepancy": 0,
        "exception_summary": {},
        "processing_time_ms": 0,
        "records_per_second": 0,
        "run_id": "boot-error",
        "run_at": "",
        "metrics": {},
    }
    BOT = FinBot(REPORT)


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/api/report")
def api_report():
    return jsonify(REPORT)


@app.get("/api/records")
def api_records():
    status = request.args.get("status", "").upper()
    exception_type = request.args.get("type", "").upper()
    records = REPORT["records"]
    if status:
        records = [r for r in records if r["status"].upper() == status]
    if exception_type:
        records = [r for r in records if (r.get("exception_type") or "").upper() == exception_type]
    return jsonify(records)


@app.get("/api/audit/<payment_id>")
def api_audit(payment_id: str):
    audits = [a for a in REPORT["audits"] if a["payment_id"] == payment_id]
    return jsonify({"payment_id": payment_id, "audits": audits})


@app.post("/api/ask")
def api_ask():
    body = request.get_json(silent=True) or {}
    return jsonify({"answer": BOT.answer(body.get("question", ""))})


@app.post("/api/rerun")
def api_rerun():
    """Re-run reconciliation on demand and refresh the in-memory report."""
    global REPORT, BOT  # noqa: PLW0603
    try:
        REPORT, BOT = _run_reconciliation()
        return jsonify(REPORT)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.get("/api/simulator/scenarios")
def api_scenarios():
    from engine.live_simulator import get_preset_scenarios
    return jsonify(get_preset_scenarios())


@app.post("/api/simulate-event")
def api_simulate_event():
    global REPORT, BOT
    from engine.live_simulator import build_simulated_event

    body = request.get_json(silent=True) or {}
    scenario_id = body.get("scenario_id", "clean_match")
    event = build_simulated_event(scenario_id)

    # Ingest event into in-memory records
    pid = event["payment_id"]
    disc = round(event["rzp_net"] - event["bank_settled"], 2)
    is_matched = abs(disc) <= 1.0 and event["bank_settled"] > 0

    exc_type = None
    if not is_matched:
        if event["bank_settled"] == 0:
            exc_type = "MISSING_IN_BANK"
        elif event.get("duplicate"):
            exc_type = "DUPLICATE_BANK"
        else:
            exc_type = "AMOUNT_MISMATCH"

    new_rec = {
        "payment_id": pid,
        "order_id": event["order_id"],
        "status": "MATCHED" if is_matched else "UNABLE_TO_RESOLVE",
        "exception_type": exc_type,
        "order_amount": event["amount"],
        "razorpay_net_amount": event["rzp_net"],
        "bank_settled_amount": event["bank_settled"],
        "discrepancy": disc,
        "method": "live_webhook",
        "confidence": 1.0 if is_matched else 0.9,
        "reason": "Live Webhook event auto-reconciled." if is_matched else f"Live Webhook flagged exception: {exc_type}",
        "evidence": event,
    }

    REPORT["records"].insert(0, new_rec)
    REPORT["total_records"] += 1
    if is_matched:
        REPORT["matched"] += 1
    else:
        REPORT["exceptions"] += 1
        if exc_type:
            REPORT["exception_summary"][exc_type] = REPORT["exception_summary"].get(exc_type, 0) + 1

    REPORT["match_rate"] = REPORT["matched"] / REPORT["total_records"] if REPORT["total_records"] else 0
    BOT = FinBot(REPORT)

    return jsonify({"status": "success", "event": event, "record": new_rec, "report": REPORT})


@app.post("/api/upload-bank")
def api_upload_bank():
    global REPORT, BOT
    import io
    import pandas as pd

    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    filename = file.filename or ""

    try:
        if filename.endswith(".csv"):
            df = pd.read_csv(io.StringIO(file.stream.read().decode("utf-8")), dtype=str)
        elif filename.endswith((".xls", ".xlsx")):
            df = pd.read_excel(io.BytesIO(file.stream.read()), dtype=str)
        else:
            return jsonify({"error": "Unsupported file format. Please upload CSV or Excel."}), 400

        REPORT = reconcile(DATA, bank_df=df)
        metrics = evaluate(REPORT, DATA)
        REPORT["metrics"] = metrics
        BOT = FinBot(REPORT)
        return jsonify(REPORT)
    except Exception as exc:
        return jsonify({"error": f"Failed to parse uploaded statement: {exc}"}), 500


@app.post("/api/razorpay-sync")
def api_razorpay_sync():
    global REPORT, BOT
    from engine.razorpay_client import RazorpayClient

    body = request.get_json(silent=True) or {}
    key_id = body.get("key_id", "")
    key_secret = body.get("key_secret", "")

    client = RazorpayClient(key_id, key_secret)
    payments = client.fetch_payments(count=10)

    return jsonify({"status": "success", "count": len(payments), "payments": payments})


@app.post("/api/actions/ticket")
def api_action_ticket():
    from engine.agent_actions import generate_razorpay_ticket
    body = request.get_json(silent=True) or {}
    pid = body.get("payment_id")
    rec = next((r for r in REPORT["records"] if r["payment_id"] == pid), {})
    return jsonify(generate_razorpay_ticket(pid, rec))


@app.post("/api/actions/alert")
def api_action_alert():
    from engine.agent_actions import generate_ops_alert
    body = request.get_json(silent=True) or {}
    pid = body.get("payment_id")
    rec = next((r for r in REPORT["records"] if r["payment_id"] == pid), {})
    return jsonify(generate_ops_alert(pid, rec))


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
