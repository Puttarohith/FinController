from __future__ import annotations

import random
import time
from typing import Any


SCENARIOS = {
    "missing_bank": {
        "name": "Simulate Missing Bank Settlement",
        "description": "Payment captured by Razorpay, but no settlement received from bank.",
        "payload": {
            "event": "payment.captured",
            "payment_id": "pay_sim_missing_001",
            "order_id": "ord_sim_missing_001",
            "amount": 4500.0,
            "rzp_net": 4410.0,
            "bank_settled": 0.0,
            "method": "upi",
            "status": "captured",
        },
    },
    "amount_mismatch": {
        "name": "Simulate Amount Mismatch",
        "description": "Bank credit received is ₹500 less than Razorpay net payout.",
        "payload": {
            "event": "settlement.processed",
            "payment_id": "pay_sim_mismatch_002",
            "order_id": "ord_sim_mismatch_002",
            "amount": 10000.0,
            "rzp_net": 9800.0,
            "bank_settled": 9300.0,
            "method": "card",
            "status": "settled",
        },
    },
    "clean_match": {
        "name": "Simulate Clean Match",
        "description": "Exact three-way match across order, Razorpay ledger, and bank settlement.",
        "payload": {
            "event": "settlement.processed",
            "payment_id": "pay_sim_clean_003",
            "order_id": "ord_sim_clean_003",
            "amount": 2500.0,
            "rzp_net": 2450.0,
            "bank_settled": 2450.0,
            "method": "netbanking",
            "status": "settled",
        },
    },
    "duplicate_credit": {
        "name": "Simulate Duplicate Bank Credit",
        "description": "Multiple bank settlement rows received for a single Payment ID.",
        "payload": {
            "event": "bank.duplicate_credit",
            "payment_id": "pay_sim_dup_004",
            "order_id": "ord_sim_dup_004",
            "amount": 1500.0,
            "rzp_net": 1470.0,
            "bank_settled": 1470.0,
            "duplicate": True,
            "method": "upi",
            "status": "settled",
        },
    },
}


def get_preset_scenarios() -> list[dict[str, Any]]:
    return [
        {"id": key, "name": val["name"], "description": val["description"]}
        for key, val in SCENARIOS.items()
    ]


def build_simulated_event(scenario_id: str) -> dict[str, Any]:
    scenario = SCENARIOS.get(scenario_id, SCENARIOS["clean_match"])
    payload = dict(scenario["payload"])
    suffix = str(random.randint(100, 999))
    payload["payment_id"] = f"{payload['payment_id']}_{suffix}"
    payload["order_id"] = f"{payload['order_id']}_{suffix}"
    payload["timestamp"] = int(time.time())
    return payload
