import csv
import json
import unittest
from pathlib import Path

from engine.metrics import evaluate
from engine.reconciler import reconcile


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def by_payment(report):
    return {record["payment_id"]: record for record in report["records"]}


def pid(index: int) -> str:
    truth = json.loads((DATA / "ground_truth.json").read_text(encoding="utf-8"))
    return next(payment_id for payment_id, item in truth.items() if item["index"] == index)


class EngineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = reconcile(DATA)

    def test_counts_match_ground_truth_exactly(self):
        metrics = evaluate(self.report, DATA, write=False)
        self.assertEqual(metrics["false_match_count"], 0)
        self.assertEqual(metrics["false_non_match_count"], 0)
        self.assertEqual(self.report["matched"], metrics["true_matches"])
        self.assertEqual(self.report["total_records"], 60)
        self.assertEqual(self.report["exceptions"], 16)

    def test_exact_match(self):
        rec = by_payment(self.report)[pid(0)]
        self.assertEqual(rec["status"], "MATCHED")
        self.assertEqual(rec["method"], "deterministic")

    def test_amount_mismatch(self):
        rec = by_payment(self.report)[pid(9)]
        self.assertEqual(rec["status"], "UNABLE_TO_RESOLVE")
        self.assertEqual(rec["exception_type"], "AMOUNT_MISMATCH")
        self.assertAlmostEqual(rec["discrepancy"], 50.0)

    def test_missing_in_bank(self):
        rec = by_payment(self.report)[pid(5)]
        self.assertEqual(rec["exception_type"], "MISSING_IN_BANK")

    def test_duplicate_bank(self):
        rec = by_payment(self.report)[pid(14)]
        self.assertEqual(rec["status"], "UNABLE_TO_RESOLVE")
        self.assertEqual(rec["exception_type"], "DUPLICATE_BANK")
        dupes = [record for record in self.report["records"] if record["payment_id"] == pid(14) and record["exception_type"] == "DUPLICATE_BANK"]
        self.assertEqual(len(dupes), 1)

    def test_ghost_entry(self):
        ghosts = [record for record in self.report["records"] if record["exception_type"] == "GHOST_ENTRY"]
        self.assertEqual(len(ghosts), 2)

    def test_fuzzy_id_typo_ai_fallback(self):
        rec = by_payment(self.report)[pid(12)]
        self.assertEqual(rec["status"], "MATCHED")
        self.assertIn(rec["method"], {"ai", "fuzzy"})
        self.assertGreaterEqual(rec["confidence"], 0.85)

    def test_refund_dr(self):
        rec = by_payment(self.report)[pid(7)]
        self.assertEqual(rec["exception_type"], "REFUND_MISSING")

    def test_failed_payment(self):
        rec = by_payment(self.report)[pid(3)]
        self.assertEqual(rec["exception_type"], "FAILED")

    def test_unknown_record(self):
        self.assertIn("pay_ghost_58", by_payment(self.report))
        self.assertEqual(by_payment(self.report)["pay_ghost_58"]["exception_type"], "GHOST_ENTRY")

    def test_malformed_row_quarantined(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for filename in ["orders.csv", "razorpay_ledger.csv", "bank_settlement.csv", "ground_truth.json"]:
                (tmp_path / filename).write_text((DATA / filename).read_text(encoding="utf-8"), encoding="utf-8")
            with (tmp_path / "bank_settlement.csv").open("a", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                writer.writerow(["", "", "", "", "", "", ""])
            report = reconcile(tmp_path)
            self.assertTrue(any(record["exception_type"] == "PARSE_ERROR" for record in report["records"]))


if __name__ == "__main__":
    unittest.main()
