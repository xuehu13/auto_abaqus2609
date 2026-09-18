"""Curve QA: policy validation (strain_targets, RB-011) and the extract.py wiring."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.common import PipelineError, read_json                     # noqa: E402
from pipeline.curve_qa import (assess, load_policy,                      # noqa: E402
                               read_history_csv, record_curve_qa, validate_policy)

EXAMPLE_POLICY = ROOT / "config" / "quality.example.json"


def base_policy(**overrides):
    policy = {"ke_ie_limit": 0.01, "ae_ie_limit": 0.05, "energy_floor_Nmm": 1e-8,
              "startup_ke_max_Nmm": 1e-10, "target_strain_tolerance": 1e-7,
              "strain_monotonic_tolerance": 1e-12, "stress_sign_tolerance_MPa": 1e-8,
              "duplicate_stress_tolerance_MPa": 1e-8,
              "strain_targets": [0.0, 0.2]}
    policy.update(overrides)
    return policy


def curve_columns(final_strain, height_mm=10.0, area_mm2=100.0, points=31):
    """A clean monotone compression curve in the canonical extract.py schema."""
    strain = [final_strain * index / (points - 1) for index in range(points)]
    stress = [0.3 + 0.5 * value for value in strain]
    internal = [1.0 + 10.0 * value for value in strain]
    columns = {"time_s": [0.001 * index for index in range(points)],
               "u3_mm": [-value * height_mm for value in strain],
               "rf3_N": [-value * area_mm2 for value in stress],
               "ALLIE": internal,
               "ALLKE": [0.001] * points,
               "ALLAE": [0.01 * value for value in internal]}
    return columns, strain


class PolicyValidationTests(unittest.TestCase):
    def test_the_example_policy_is_valid(self):
        policy = load_policy(EXAMPLE_POLICY)
        self.assertEqual(len(policy["strain_targets"]), 11)
        self.assertAlmostEqual(policy["strain_targets"][-1], 0.300)

    def test_strain_targets_are_required(self):
        policy = base_policy()
        del policy["strain_targets"]
        with self.assertRaises(PipelineError) as caught:
            validate_policy(policy)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_strain_targets_must_be_at_least_two_increasing_finite_numbers(self):
        for bad in ([0.2], [0.3, 0.2], [0.1, float("nan")], "0.2", []):
            with self.subTest(targets=bad):
                with self.assertRaises(PipelineError) as caught:
                    validate_policy(base_policy(strain_targets=bad))
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")


class AssessTests(unittest.TestCase):
    def test_a_full_paper_range_curve_passes_with_the_11_point_sampling(self):
        columns, _ = curve_columns(0.300)
        assessment = assess(columns, 10.0, 100.0, -1, load_policy(EXAMPLE_POLICY))
        self.assertEqual(assessment["status"], "CURVE_QA_PASS")
        self.assertEqual(len(assessment["stress_at_targets_MPa"]), 11)
        self.assertEqual(assessment["strain_targets"], load_policy(EXAMPLE_POLICY)["strain_targets"])
        self.assertFalse(assessment["dataset_eligible"])

    def test_a_20_percent_curve_fails_paper_targets_by_design(self):
        columns, _ = curve_columns(0.200)
        assessment = assess(columns, 10.0, 100.0, -1, load_policy(EXAMPLE_POLICY))
        self.assertEqual(assessment["status"], "CURVE_QA_FAILED")
        self.assertIn("TARGET_RANGE_NOT_REACHED", assessment["failures"])

    def test_targets_come_from_the_policy_not_the_code(self):
        columns, _ = curve_columns(0.200)
        assessment = assess(columns, 10.0, 100.0, -1, base_policy(strain_targets=[0.0, 0.2]))
        self.assertEqual(assessment["status"], "CURVE_QA_PASS")
        self.assertEqual(assessment["stress_at_targets_MPa"], [0.3, 0.4])


class WiringTests(unittest.TestCase):
    def test_read_history_csv_reads_the_extract_schema(self):
        folder = Path(tempfile.mkdtemp(prefix="qa_csv_"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        (folder / "history.csv").write_text(
            "time_s,u3_mm,rf3_N,ALLIE,ALLKE,ALLAE\n"
            "0.0,0.0,0.0,1.0,0.001,0.01\n"
            "1.0,-2.0,-40.0,3.0,0.001,0.03\n", encoding="utf-8")
        columns = read_history_csv(folder / "history.csv")
        self.assertEqual(sorted(columns), ["ALLAE", "ALLIE", "ALLKE", "rf3_N", "time_s", "u3_mm"])
        self.assertEqual(columns["u3_mm"], [0.0, -2.0])

    def test_record_curve_qa_writes_the_verdict_beside_the_results(self):
        folder = Path(tempfile.mkdtemp(prefix="qa_record_"))
        self.addCleanup(lambda: shutil.rmtree(folder, ignore_errors=True))
        columns, _ = curve_columns(0.200)
        header = ",".join(columns)
        rows = [",".join(repr(columns[name][index]) for name in columns)
                for index in range(len(columns["time_s"]))]
        (folder / "history.csv").write_text(
            header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
        policy_path = folder / "quality.json"
        policy_path.write_text(json.dumps(base_policy()), encoding="utf-8")
        messages = []
        assessment = record_curve_qa(folder, policy_path=policy_path, height_mm=10.0,
                                     area_mm2=100.0, log=messages.append)
        self.assertEqual(assessment["status"], "CURVE_QA_PASS")
        self.assertTrue(messages[0].startswith("curve qa CURVE_QA_PASS"))
        self.assertEqual(read_json(folder / "curve_qa.json")["status"], "CURVE_QA_PASS")


if __name__ == "__main__":
    unittest.main()
