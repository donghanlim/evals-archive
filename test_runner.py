#!/usr/bin/env python3
"""runner.py의 stdlib 단위 검증."""
import unittest
import runner


class RunnerTests(unittest.TestCase):
    def test_normalize_ssonda_preserves_native_case_without_edit(self):
        raw = [{
            "id": "x-1", "category": "edge", "note": "fixture",
            "input": {"deposit": {}}, "expected": {"match": "p1"},
        }]
        normalized = runner.normalize_ssonda(raw, __import__("pathlib").Path("fixture.jsonl"))
        self.assertEqual(normalized[0]["id"], "x-1")
        self.assertEqual(normalized[0]["failure_type"], "edge")
        self.assertEqual(normalized[0]["expected"], {"match": "p1"})
        runner.validate_common(normalized)

    def test_grade_counts_match_and_no_match(self):
        cases = [
            {"id": "a", "project": "p", "input": {}, "expected": {"match": "p1"}, "failure_type": "happy", "source": "fixture"},
            {"id": "b", "project": "p", "input": {}, "expected": {"match": None}, "failure_type": "negative", "source": "fixture"},
            {"id": "c", "project": "p", "input": {}, "expected": {"match": "p2"}, "failure_type": "edge", "source": "fixture"},
        ]
        report = runner.grade_match_cases(cases, {"a": "p1", "b": None, "c": None})
        self.assertEqual(report["metrics"]["correct"], 2)
        self.assertEqual(report["confusion_matrix"], {"tp": 1, "fp": 0, "fn": 1, "tn": 1})
        self.assertEqual(report["failure_types"]["edge"]["fail_ids"], ["c"])

    def test_common_schema_rejects_duplicate_id(self):
        cases = [
            {"id": "same", "project": "p", "input": {}, "expected": {}, "failure_type": "x", "source": "s"},
            {"id": "same", "project": "p", "input": {}, "expected": {}, "failure_type": "x", "source": "s"},
        ]
        with self.assertRaisesRegex(ValueError, "중복"):
            runner.validate_common(cases)


if __name__ == "__main__":
    unittest.main(verbosity=2)
