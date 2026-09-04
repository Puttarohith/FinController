import csv
import hashlib
import json
import random
from collections import Counter
from datetime import date, timedelta
from pathlib import Path


random.seed(42)

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

AMOUNTS = [199, 299, 499, 599, 799, 999, 1499, 1999, 2499, 4999]
MISSING_IN_BANK = {5, 18, 33}
AMOUNT_MISMATCH = {9, 27, 41}
DUPLICATE_IN_BANK = {14, 52}
FAILED = {3, 22, 38, 55}
REFUNDED = {7, 29}
MISSING_IN_RAZORPAY = {58, 59}
FUZZY_ID_TYPO = {12, 36}
VENDOR_NAME_VARIANT = {25}
DATE_SHIFT = {45}


def md5_id(value: int) -> str:
    return hashlib.md5(str(value).encode("utf-8")).hexdigest()[:14]


def payment_id(index: int) -> str:
    return f"pay_{md5_id(index)}"


def order_id(index: int) -> str:
    return f"ord_{md5_id(index + 100)}"


def transpose_two_chars(value: str) -> str:
    chars = list(value)
    left = 6
    chars[left], chars[left + 1] = chars[left + 1], chars[left]
    return "".join(chars)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_batch() -> None:
    orders = []
    ledger = []
    bank = []
    truth = {}
    base_date = date(2026, 8, 1)
    methods = ["card", "upi", "netbanking", "wallet"]
    merchants = ["Razorpay Commerce", "RZP Commerce", "Razorpay Marketplace"]

    for index in range(60):
        pid = payment_id(index)
        oid = order_id(index)
        amount = float(AMOUNTS[index % len(AMOUNTS)])
        created = base_date + timedelta(days=index % 20)
        method = methods[index % len(methods)]
        merchant = merchants[index % len(merchants)]
        status = "failed" if index in FAILED else "captured"
        fees = round(amount * 0.02, 2)
        tax = round(amount * 0.002, 2)
        net = round(amount - fees - tax, 2)

        orders.append(
            {
                "order_id": oid,
                "payment_id": pid,
                "merchant_id": f"merch_{1000 + index % 5}",
                "customer_email": f"customer{index:02d}@example.com",
                "amount": f"{amount:.2f}",
                "currency": "INR",
                "status": status,
                "method": method,
                "created_at": created.isoformat(),
                "description": f"{merchant} order {index:02d}",
            }
        )

        if index not in MISSING_IN_RAZORPAY:
            ledger.append(
                {
                    "payment_id": pid,
                    "order_id": oid,
                    "amount": f"{amount:.2f}",
                    "currency": "INR",
                    "status": status,
                    "method": method,
                    "captured_at": (created + timedelta(hours=2)).isoformat(),
                    "settlement_id": f"setl_{md5_id(index + 200)}",
                    "fees": f"{fees:.2f}",
                    "tax": f"{tax:.2f}",
                    "net_amount": f"{net:.2f}",
                }
            )

        if index in FAILED:
            expected = "failed"
            resolution = "Failed order is excluded from settlement."
        elif index in MISSING_IN_BANK:
            expected = "missing_in_bank"
            resolution = "Captured Razorpay payment has no bank settlement."
        elif index in AMOUNT_MISMATCH:
            expected = "amount_mismatch"
            resolution = "Bank settled amount is INR 50.00 below Razorpay net amount."
        elif index in DUPLICATE_IN_BANK:
            expected = "duplicate_bank"
            resolution = "Duplicate bank entries exist for one payment_id; first credit only is eligible."
        elif index in REFUNDED:
            expected = "refunded"
            resolution = "Bank contains refund debit for the payment."
        elif index in MISSING_IN_RAZORPAY:
            expected = "ghost"
            resolution = "Bank credit has no Razorpay ledger record."
        elif index in FUZZY_ID_TYPO:
            expected = "fuzzy_match"
            resolution = "Payment ID typo can be reconciled by fuzzy ID, amount, and date signals."
        else:
            expected = "matched"
            resolution = "Exact three-way payment match within INR 1.00 tolerance."

        truth_pid = f"pay_ghost_{index}" if index in MISSING_IN_RAZORPAY else pid
        truth[truth_pid] = {
            "order_id": oid,
            "index": index,
            "expected_classification": expected,
            "expected_resolution": resolution,
            "expected_match_payment_id": pid if expected in {"matched", "fuzzy_match"} else None,
        }

        if index in FAILED or index in MISSING_IN_BANK:
            continue

        bank_pid = pid
        settled = net
        credit_debit = "CR"
        narration_merchant = merchant
        settlement_date = created + timedelta(days=2)

        if index in MISSING_IN_RAZORPAY:
            bank_pid = f"pay_ghost_{index}"
        if index in AMOUNT_MISMATCH:
            settled = round(net - 50.0, 2)
        if index in REFUNDED:
            settled = -net
            credit_debit = "DR"
        if index in FUZZY_ID_TYPO:
            bank_pid = transpose_two_chars(pid)
        if index in VENDOR_NAME_VARIANT:
            narration_merchant = "Razor Pay Commerc"
        if index in DATE_SHIFT:
            settlement_date += timedelta(days=3)

        bank_row = {
            "bank_ref": f"UTR{index:06d}",
            "payment_id": bank_pid,
            "settled_amount": f"{settled:.2f}",
            "settlement_date": settlement_date.isoformat(),
            "bank": "HDFC",
            "narration": f"{narration_merchant} settlement {oid} {pid}",
            "credit_debit": credit_debit,
        }
        bank.append(bank_row)

        if index in DUPLICATE_IN_BANK:
            duplicate = dict(bank_row)
            duplicate["bank_ref"] = f"UTR{index:06d}D"
            bank.append(duplicate)

    write_csv(
        DATA / "orders.csv",
        orders,
        [
            "order_id",
            "payment_id",
            "merchant_id",
            "customer_email",
            "amount",
            "currency",
            "status",
            "method",
            "created_at",
            "description",
        ],
    )
    write_csv(
        DATA / "razorpay_ledger.csv",
        ledger,
        [
            "payment_id",
            "order_id",
            "amount",
            "currency",
            "status",
            "method",
            "captured_at",
            "settlement_id",
            "fees",
            "tax",
            "net_amount",
        ],
    )
    write_csv(
        DATA / "bank_settlement.csv",
        bank,
        [
            "bank_ref",
            "payment_id",
            "settled_amount",
            "settlement_date",
            "bank",
            "narration",
            "credit_debit",
        ],
    )
    (DATA / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")

    counts = Counter(item["expected_classification"] for item in truth.values())
    print("Seeded anomaly summary")
    print("classification       count")
    print("-------------------- -----")
    for key in sorted(counts):
        print(f"{key:<20} {counts[key]:>5}")


if __name__ == "__main__":
    build_batch()
