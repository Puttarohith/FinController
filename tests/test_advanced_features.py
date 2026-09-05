import unittest
from engine.fraud_detector import detect_anomalies
from engine.analytics import calculate_dispute_analytics


class TestAdvancedFeatures(unittest.TestCase):
    def test_fraud_detector(self):
        records = [
            {
                "payment_id": "pay_fraud_001",
                "status": "UNABLE_TO_RESOLVE",
                "exception_type": "GHOST_ENTRY",
                "bank_settled_amount": 35000.0,
                "discrepancy": 35000.0,
                "source_bank": {"narration": "John Doe Unknown Payout"},
                "source_order": {"customer_name": "Alice Smith"},
            }
        ]
        alerts = detect_anomalies(records)
        self.assertGreaterEqual(len(alerts), 1)
        self.assertTrue(records[0]["is_fraud_suspect"])

    def test_dispute_analytics(self):
        records = [
            {
                "payment_id": "pay_001",
                "status": "MATCHED",
                "method": "upi",
                "order_amount": 1000.0,
            },
            {
                "payment_id": "pay_002",
                "status": "UNABLE_TO_RESOLVE",
                "method": "card",
                "discrepancy": 500.0,
                "evidence": {"late_settlement_days": 16},
            },
        ]
        res = calculate_dispute_analytics(records)
        self.assertEqual(res["aging_matrix"]["critical_15_plus_days"]["count"], 1)
        self.assertEqual(res["method_distribution"]["upi"]["matched"], 1)
        self.assertEqual(res["method_distribution"]["card"]["exceptions"], 1)


if __name__ == "__main__":
    unittest.main()
