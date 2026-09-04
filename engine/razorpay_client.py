from __future__ import annotations

import os
from typing import Any
import requests


class RazorpayClient:
    """Client to connect to Razorpay REST API or fallback to mock data fetching."""

    def __init__(self, key_id: str | None = None, key_secret: str | None = None):
        self.key_id = key_id or os.getenv("RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.getenv("RAZORPAY_KEY_SECRET", "")
        self.base_url = "https://api.razorpay.com/v1"

    def fetch_payments(self, count: int = 10) -> list[dict[str, Any]]:
        """Fetch live captured payments from Razorpay API or return mock data."""
        if self.key_id and self.key_secret:
            try:
                res = requests.get(
                    f"{self.base_url}/payments",
                    auth=(self.key_id, self.key_secret),
                    params={"count": count},
                    timeout=8,
                )
                res.raise_for_status()
                data = res.json()
                items = data.get("items", [])
                return [
                    {
                        "payment_id": p.get("id"),
                        "order_id": p.get("order_id"),
                        "amount": p.get("amount", 0) / 100.0,
                        "status": p.get("status"),
                        "method": p.get("method"),
                        "captured_at": p.get("created_at"),
                    }
                    for p in items
                ]
            except Exception as exc:
                print(f"[RazorpayClient] API call failed: {exc}. Using mock data.")

        return self._mock_payments(count)

    def _mock_payments(self, count: int) -> list[dict[str, Any]]:
        mock_data = []
        for i in range(1, count + 1):
            mock_data.append(
                {
                    "payment_id": f"pay_live_api_{i:03d}",
                    "order_id": f"ord_live_api_{i:03d}",
                    "amount": float(1000 * i),
                    "status": "captured" if i % 5 != 0 else "failed",
                    "method": "upi" if i % 2 == 0 else "card",
                    "source": "Razorpay Live API (Simulated)",
                }
            )
        return mock_data
