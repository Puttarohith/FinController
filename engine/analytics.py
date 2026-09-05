from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def calculate_dispute_analytics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculates SLA dispute aging matrix and payment method distribution."""
    now = datetime.now(timezone.utc)

    aging_matrix = {
        "fresh_0_7_days": {"count": 0, "amount": 0.0, "pids": []},
        "pending_8_14_days": {"count": 0, "amount": 0.0, "pids": []},
        "critical_15_plus_days": {"count": 0, "amount": 0.0, "pids": []},
    }

    method_distribution: dict[str, dict[str, Any]] = {
        "upi": {"matched": 0, "exceptions": 0, "total_amount": 0.0},
        "card": {"matched": 0, "exceptions": 0, "total_amount": 0.0},
        "netbanking": {"matched": 0, "exceptions": 0, "total_amount": 0.0},
        "wallet": {"matched": 0, "exceptions": 0, "total_amount": 0.0},
        "other": {"matched": 0, "exceptions": 0, "total_amount": 0.0},
    }

    for r in records:
        method = (r.get("method") or "other").lower()
        if method not in method_distribution:
            method = "other"

        amt = r.get("order_amount") or r.get("razorpay_net_amount") or r.get("bank_settled_amount") or 0.0
        if r["status"] == "MATCHED":
            method_distribution[method]["matched"] += 1
        else:
            method_distribution[method]["exceptions"] += 1
        method_distribution[method]["total_amount"] += amt

        # Aging computation for unresolved exceptions
        if r["status"] != "MATCHED":
            disc = abs(r.get("discrepancy") or 0)
            # Days simulated based on date delta evidence or default fallback
            days = 0
            ev = r.get("evidence") or {}
            rzp = r.get("source_razorpay") or {}
            if ev.get("late_settlement_days"):
                days = int(ev["late_settlement_days"])
            elif rzp.get("captured_at"):
                try:
                    d_str = rzp["captured_at"]
                    c_date = datetime.fromisoformat(d_str).replace(tzinfo=timezone.utc)
                    days = abs((now - c_date).days)
                except Exception:
                    days = 4  # Default fallback aging days

            if days <= 7:
                aging_matrix["fresh_0_7_days"]["count"] += 1
                aging_matrix["fresh_0_7_days"]["amount"] += disc
                aging_matrix["fresh_0_7_days"]["pids"].append(r["payment_id"])
            elif days <= 14:
                aging_matrix["pending_8_14_days"]["count"] += 1
                aging_matrix["pending_8_14_days"]["amount"] += disc
                aging_matrix["pending_8_14_days"]["pids"].append(r["payment_id"])
            else:
                aging_matrix["critical_15_plus_days"]["count"] += 1
                aging_matrix["critical_15_plus_days"]["amount"] += disc
                aging_matrix["critical_15_plus_days"]["pids"].append(r["payment_id"])

    return {
        "aging_matrix": aging_matrix,
        "method_distribution": method_distribution,
    }
