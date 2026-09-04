import unittest
from pathlib import Path
from engine.agent_actions import generate_razorpay_ticket, generate_ops_alert
from engine.live_simulator import build_simulated_event, get_preset_scenarios
from engine.razorpay_client import RazorpayClient
from engine.reconciler import reconcile


class TestUpgrades(unittest.TestCase):
    def test_scenarios(self):
        scenarios = get_preset_scenarios()
        self.assertGreaterEqual(len(scenarios), 3)

    def test_simulated_event(self):
        event = build_simulated_event("missing_bank")
        self.assertTrue(event["payment_id"].startswith("pay_sim_missing_001"))
        self.assertEqual(event["bank_settled"], 0.0)

    def test_razorpay_client_mock(self):
        client = RazorpayClient()
        payments = client.fetch_payments(count=5)
        self.assertEqual(len(payments), 5)
        self.assertTrue(payments[0]["payment_id"].startswith("pay_live_api_"))

    def test_agent_actions(self):
        record = {
            "order_id": "ord_123",
            "exception_type": "MISSING_IN_BANK",
            "discrepancy": 4500.0,
            "order_amount": 4500.0,
            "razorpay_net_amount": 4410.0,
            "bank_settled_amount": 0.0,
            "reason": "Missing in bank statement.",
        }
        ticket = generate_razorpay_ticket("pay_123", record)
        self.assertIn("pay_123", ticket["subject"])
        self.assertIn("Razorpay Merchant Support", ticket["body"])

        alert = generate_ops_alert("pay_123", record)
        self.assertIn("pay_123", alert["slack_message"])
        self.assertIn("MISSING_IN_BANK", alert["slack_message"])


if __name__ == "__main__":
    unittest.main()
