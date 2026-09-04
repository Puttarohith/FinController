from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def generate_razorpay_ticket(payment_id: str, record: dict[str, Any]) -> dict[str, str]:
    """Generate a pre-formatted merchant support ticket for Razorpay support."""
    exc = record.get("exception_type") or "UNRESOLVED_PAYMENT"
    disc = record.get("discrepancy") or 0
    order_amt = record.get("order_amount") or 0
    rzp_net = record.get("razorpay_net_amount") or 0
    bank_amt = record.get("bank_settled_amount") or 0
    reason = record.get("reason") or "Discrepancy detected during 3-way reconciliation."

    subject = f"[Reconciliation Escalation] Payment ID {payment_id} - Issue: {exc}"

    body = (
        f"Dear Razorpay Merchant Support Team,\n\n"
        f"We are escalating an unresolved payment discrepancy detected by our automated reconciliation engine.\n\n"
        f"── TRANSACTION DETAILS ──\n"
        f"• Payment ID: {payment_id}\n"
        f"• Order ID: {record.get('order_id') or 'N/A'}\n"
        f"• Exception Type: {exc}\n"
        f"• Merchant Order Amount: ₹{order_amt:,.2f}\n"
        f"• Razorpay Ledger Net Amount: ₹{rzp_net:,.2f}\n"
        f"• Bank Settled Amount: ₹{bank_amt:,.2f}\n"
        f"• Discrepancy Amount: ₹{abs(disc):,.2f}\n\n"
        f"── ISSUE SUMMARY ──\n"
        f"{reason}\n\n"
        f"── REQUESTED ACTION ──\n"
        f"Please verify settlement status and Payout UTR for Payment ID {payment_id}. "
        f"If a settlement trace is available, kindly provide the bank reference/UTR number so our finance ops team can reconcile this item.\n\n"
        f"Best regards,\n"
        f"Finance Operations Team"
    )

    return {
        "payment_id": payment_id,
        "subject": subject,
        "body": body,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def generate_ops_alert(payment_id: str, record: dict[str, Any]) -> dict[str, str]:
    """Generate a formatted alert message suitable for Slack or Email team notifications."""
    exc = record.get("exception_type") or "UNRESOLVED_PAYMENT"
    disc = record.get("discrepancy") or 0
    reason = record.get("reason") or "Requires manual review."

    slack_msg = (
        f"🚨 *FINANCE ALERT: Unresolved Exception Detected*\n"
        f"*Payment ID:* `{payment_id}`\n"
        f"*Exception:* `{exc}`\n"
        f"*Amount at Risk:* ₹{abs(disc):,.2f}\n"
        f"*Reason:* {reason}\n"
        f"👉 _Action Required: Please review evidence in FinController dashboard._"
    )

    return {
        "payment_id": payment_id,
        "slack_message": slack_msg,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
