from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MATCH_CLASSES = {"matched", "fuzzy_match"}


def evaluate(report: dict[str, Any], data_dir: str | Path, write: bool = True) -> dict[str, Any]:
    data_dir = Path(data_dir)
    truth = json.loads((data_dir / "ground_truth.json").read_text(encoding="utf-8"))
    records = report.get("records", [])
    by_pid = {record["payment_id"]: record for record in records}
    false_matches = []
    false_non_matches = []
    expected_unresolved = []
    unexpected_unresolved = []
    true_matches = 0
    ai_checked = 0
    ai_correct = 0

    for pid, expected in truth.items():
        expected_class = expected["expected_classification"]
        record = by_pid.get(pid)
        if record and record.get("method") == "ai":
            ai_checked += 1
        if expected_class in MATCH_CLASSES:
            if record and record.get("status") == "MATCHED":
                true_matches += 1
                if record.get("method") == "ai":
                    ai_correct += 1
            else:
                false_non_matches.append(pid)
        else:
            if record and record.get("status") == "MATCHED":
                false_matches.append(pid)
            else:
                expected_unresolved.append(pid)

    for record in records:
        pid = record["payment_id"]
        if pid not in truth and record.get("status") == "MATCHED":
            false_matches.append(pid)
        if pid not in truth and record.get("status") != "MATCHED":
            unexpected_unresolved.append(pid)

    total_expected_matches = sum(1 for item in truth.values() if item["expected_classification"] in MATCH_CLASSES)
    reported_matches = report.get("matched", 0)
    precision = true_matches / reported_matches if reported_matches else 0
    recall = true_matches / total_expected_matches if total_expected_matches else 0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0
    metrics = {
        "true_matches": true_matches,
        "false_matches": false_matches,
        "false_match_count": len(false_matches),
        "false_non_matches": false_non_matches,
        "false_non_match_count": len(false_non_matches),
        "expected_unresolved": expected_unresolved,
        "expected_unresolved_count": len(expected_unresolved),
        "unexpected_unresolved": unexpected_unresolved,
        "unexpected_unresolved_count": len(unexpected_unresolved),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "match_rate": round(report.get("match_rate", 0), 4),
        "exception_rate": round(report.get("exceptions", 0) / report.get("total_records", 1), 4),
        "auto_resolution_rate": round(
            sum(1 for record in records if record.get("status") == "MATCHED" and record.get("method") in {"deterministic", "fuzzy"})
            / max(len(records), 1),
            4,
        ),
        "ai_verify_accuracy": round(ai_correct / ai_checked, 4) if ai_checked else 1.0,
    }
    if write:
        (data_dir / "evaluation_report.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def print_metrics(metrics: dict[str, Any]) -> None:
    rows = [
        ("true_matches", metrics["true_matches"]),
        ("false_matches", metrics["false_match_count"]),
        ("false_non_matches", metrics["false_non_match_count"]),
        ("expected_unresolved", metrics["expected_unresolved_count"]),
        ("unexpected_unresolved", metrics["unexpected_unresolved_count"]),
        ("precision", f"{metrics['precision']:.2%}"),
        ("recall", f"{metrics['recall']:.2%}"),
        ("f1", f"{metrics['f1']:.2%}"),
        ("match_rate", f"{metrics['match_rate']:.2%}"),
        ("exception_rate", f"{metrics['exception_rate']:.2%}"),
        ("auto_resolution_rate", f"{metrics['auto_resolution_rate']:.2%}"),
        ("ai_verify_accuracy", f"{metrics['ai_verify_accuracy']:.2%}"),
    ]
    print("Evaluation metrics")
    print("metric                   value")
    print("------------------------ ----------------")
    for key, value in rows:
        print(f"{key:<24} {value}")

