from __future__ import annotations

import os
from typing import Any

import requests


def format_inr(value: float | int | None) -> str:
    if value is None:
        return "₹0.00"
    negative = float(value) < 0
    value = abs(float(value))
    integer, decimal = f"{value:.2f}".split(".")
    if len(integer) > 3:
        last = integer[-3:]
        rest = integer[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        integer = ",".join(groups + [last])
    return f"{'-' if negative else ''}₹{integer}.{decimal}"


class FinBot:
    def __init__(self, report: dict[str, Any]):
        self.report = report

    def answer(self, question: str) -> str:
        question = (question or "").strip()
        if not question:
            return "Ask about a metric, exception, discrepancy, or payment_id from this run."

        deterministic = self._deterministic_answer(question)
        if deterministic:
            return deterministic

        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            return "I can only answer from the reconciliation report, and that detail is not present in the data."

        try:
            context = {
                "metrics": self.report.get("metrics", {}),
                "exception_summary": self.report.get("exception_summary", {}),
                "exceptions": [
                    record
                    for record in self.report.get("records", [])
                    if record.get("status") != "MATCHED"
                ],
            }
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 180,
                    "temperature": 0,
                    "system": (
                        "Answer only from the JSON reconciliation report. Under 150 words. "
                        "Cite payment_ids. If absent, say the answer is not in the data."
                    ),
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Report: {context}\nQuestion: {question}",
                        }
                    ],
                },
                timeout=8,
            )
            response.raise_for_status()
            text = response.json()["content"][0]["text"].strip()
            return " ".join(text.split()[:150])
        except Exception:
            return "I can only answer from the reconciliation report, and that detail is not present in the data."

    def _deterministic_answer(self, question: str) -> str | None:
        q = question.lower()
        records = self.report.get("records", [])
        metrics = self.report.get("metrics", {})
        ids = [record["payment_id"] for record in records if record["payment_id"].lower() in q]
        if ids:
            snippets = []
            for pid in ids[:3]:
                record = next(item for item in records if item["payment_id"] == pid)
                snippets.append(
                    f"{pid}: {record['status']} / {record.get('exception_type') or 'matched'}, "
                    f"discrepancy {format_inr(record.get('discrepancy', 0))}. {record['reason']}"
                )
            return " ".join(snippets)
        if "match rate" in q:
            return f"Match rate is {self.report.get('match_rate', 0):.2%} across {self.report.get('total_records', 0)} records."
        if "review first" in q or "prioritize" in q:
            exceptions = [record for record in records if record.get("status") != "MATCHED"]
            exceptions.sort(key=lambda record: abs(record.get("discrepancy") or 0), reverse=True)
            top = exceptions[:3]
            if not top:
                return "No exception records need review in this report."
            details = "; ".join(
                f"{record['payment_id']} ({record.get('exception_type')}, {format_inr(abs(record.get('discrepancy') or 0))})"
                for record in top
            )
            return f"Review the largest money-impact exceptions first: {details}."
        if "precision" in q or "accuracy" in q:
            return f"Precision is {metrics.get('precision', 0):.2%}, recall is {metrics.get('recall', 0):.2%}, and F1 is {metrics.get('f1', 0):.2%}."
        if "exception" in q or "unresolved" in q:
            summary = ", ".join(f"{k}: {v}" for k, v in self.report.get("exception_summary", {}).items())
            return f"Exceptions total {self.report.get('exceptions', 0)}. {summary}"
        if "risk" in q or "discrepancy" in q:
            return f"Amount at risk is {format_inr(abs(self.report.get('total_discrepancy', 0)))}."
        return None
