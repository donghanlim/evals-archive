#!/usr/bin/env python3
"""공통 골든셋 최소 runner.

v1은 기존 쏜다 golden.jsonl을 수정하지 않고 ssonda adapter로 정규화해
실제 bridge를 실행하고 JSON report를 남긴다. 외부 Python 패키지는 쓰지 않는다.

사용법:
  python3 runner.py ssonda \
    --dataset /path/to/golden.jsonl \
    --bridge /path/to/bridge.mjs \
    --output evidence/report.json
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "golden-case/v1"
RUNNER_VERSION = "week01-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no} JSON 파싱 실패: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no} 케이스는 객체여야 합니다.")
        cases.append(value)
    if not cases:
        raise ValueError(f"{path}에 평가 케이스가 없습니다.")
    return cases


def normalize_ssonda(raw_cases: list[dict[str, Any]], dataset: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_cases, 1):
        for field in ("id", "category", "input", "expected"):
            if field not in raw:
                raise ValueError(f"{dataset}:{index}에 {field!r} 필드가 없습니다.")
        expected = raw["expected"]
        if not isinstance(expected, dict) or "match" not in expected:
            raise ValueError(f"{dataset}:{index} expected.match가 필요합니다.")
        match = expected["match"]
        if match is not None and not isinstance(match, str):
            raise ValueError(f"{dataset}:{index} expected.match는 문자열 또는 null이어야 합니다.")
        normalized.append({
            "id": raw["id"],
            "project": "ssonda",
            "input": raw["input"],
            "expected": {"match": match},
            "failure_type": raw["category"],
            "source": str(dataset),
            "group": "legacy-golden",
            "notes": raw.get("note", ""),
            "metadata": {"native_category": raw["category"], "native_line": index},
        })
    return normalized


def validate_common(cases: list[dict[str, Any]]) -> None:
    required = ("id", "project", "input", "expected", "failure_type", "source")
    ids: set[str] = set()
    for case in cases:
        missing = [key for key in required if key not in case]
        if missing:
            raise ValueError(f"공통 스키마 필수 필드 누락: {missing}")
        if not isinstance(case["id"], str) or not case["id"].strip():
            raise ValueError("공통 스키마 id는 비어 있지 않은 문자열이어야 합니다.")
        if case["id"] in ids:
            raise ValueError(f"공통 스키마 id 중복: {case['id']}")
        ids.add(case["id"])
        if not isinstance(case["input"], dict) or not isinstance(case["expected"], dict):
            raise ValueError(f"{case['id']}: input과 expected는 객체여야 합니다.")
        for key in ("project", "failure_type", "source"):
            if not isinstance(case[key], str) or not case[key].strip():
                raise ValueError(f"{case['id']}: {key}는 비어 있지 않은 문자열이어야 합니다.")


def run_ssonda_bridge(bridge: Path, dataset: Path) -> dict[str, Any]:
    result = subprocess.run(
        ["node", str(bridge), str(dataset)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(f"bridge 실행 실패 ({result.returncode}):\n{result.stderr.strip()}")
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"bridge 출력 JSON 파싱 실패: {exc.msg}") from exc
    if not isinstance(rows, list):
        raise RuntimeError("bridge 출력은 예측 행 배열이어야 합니다.")
    predictions: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict) or "id" not in row or "predicted" not in row:
            raise RuntimeError("bridge 출력 행에는 id와 predicted가 필요합니다.")
        if row["id"] in predictions:
            raise RuntimeError(f"bridge 출력 id 중복: {row['id']}")
        predictions[row["id"]] = row["predicted"]
    return predictions


def grade_match_cases(cases: list[dict[str, Any]], predictions: dict[str, Any]) -> dict[str, Any]:
    tp = fp = fn = tn = 0
    by_failure: dict[str, dict[str, Any]] = collections.defaultdict(
        lambda: {"n": 0, "pass": 0, "fail_ids": []}
    )
    unknown_prediction_ids = sorted(set(predictions) - {case["id"] for case in cases})
    if unknown_prediction_ids:
        raise RuntimeError(f"dataset에 없는 bridge 예측 id: {', '.join(unknown_prediction_ids)}")

    for case in cases:
        case_id = case["id"]
        if case_id not in predictions:
            raise RuntimeError(f"bridge가 {case_id} 예측을 반환하지 않았습니다.")
        expected = case["expected"]["match"]
        predicted = predictions[case_id]
        bucket = by_failure[case["failure_type"]]
        bucket["n"] += 1
        if predicted == expected:
            bucket["pass"] += 1
        else:
            bucket["fail_ids"].append(case_id)

        if expected is not None and predicted == expected:
            tp += 1
        elif expected is None and predicted is None:
            tn += 1
        else:
            if predicted is not None:
                fp += 1
            if expected is not None:
                fn += 1

    total = len(cases)
    correct = tp + tn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "case_count": total,
        "metrics": {
            "accuracy": correct / total if total else 0.0,
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "correct": correct,
        },
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "failure_types": dict(sorted(by_failure.items())),
    }


def run_ssonda(dataset: Path, bridge: Path) -> dict[str, Any]:
    raw_cases = read_jsonl(dataset)
    cases = normalize_ssonda(raw_cases, dataset)
    validate_common(cases)
    predictions = run_ssonda_bridge(bridge, dataset)
    report = grade_match_cases(cases, predictions)
    report.update({
        "schema_version": SCHEMA_VERSION,
        "runner_version": RUNNER_VERSION,
        "adapter": "ssonda-v1",
        "run_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "dataset": str(dataset),
        "dataset_sha256": sha256(dataset),
        "bridge": str(bridge),
        "bridge_sha256": sha256(bridge),
    })
    return report


def print_summary(report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    print(f"{report['adapter']} | {report['case_count']} cases")
    print(f"accuracy {metrics['accuracy']:.1%} ({metrics['correct']}/{report['case_count']})")
    print(f"precision {metrics['precision']:.1%} | recall {metrics['recall']:.1%} | F1 {metrics['f1']:.1%}")
    for name, item in report["failure_types"].items():
        print(f"{name}: {item['pass']}/{item['n']} pass")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="공통 골든셋 최소 runner")
    subparsers = parser.add_subparsers(dest="adapter", required=True)
    ssonda = subparsers.add_parser("ssonda", help="수정하지 않은 쏜다 golden.jsonl adapter")
    ssonda.add_argument("--dataset", type=Path, required=True)
    ssonda.add_argument("--bridge", type=Path, required=True)
    ssonda.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        report = run_ssonda(args.dataset.resolve(), args.bridge.resolve())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print_summary(report)
        print(f"report: {args.output}")
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"runner error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
