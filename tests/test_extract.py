"""Extraction: raw ODB history -> history.csv / stress_strain.csv / summary.json."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import extract as extract_module                          # noqa: E402
from pipeline.common import PipelineError, read_json, write_json         # noqa: E402
from pipeline.extract import build_results, write_results              # noqa: E402


def raw_history(*, displacement, reaction, energy=None, energy_times=None, missing=None):
    """Minimal raw worker document with the keys extraction actually reads."""
    axis = [0.1 * index for index in range(len(displacement))]
    document = {"status": "RAW_HISTORY_EXPORTED", "step": "Compression", "frames": 2,
                "nodes": {"RP_TOP": {"region": "Node PART-1-1.13",
                                     "series": {"U3": list(zip(axis, displacement)),
                                                "RF3": list(zip(axis, reaction))}}},
                "energy": {}, "missing": missing or {"nodes": [], "energy": []}}
    for name, values in (energy or {}).items():
        times = energy_times if energy_times is not None else axis
        document["energy"][name] = list(zip(times, values))
    return document


class ResultComputationTests(unittest.TestCase):
    def build(self, **kwargs):
        raw = raw_history(**kwargs)
        return build_results(raw, case_id="mini", solver="explicit_dynamic", height_mm=10.0,
                             area_mm2=100.0, target_strain=0.2, wall_time_s=12.5,
                             mass_scaling={"enabled": False})

    def test_strain_and_stress_are_compression_positive(self):
        columns, strain, stress, summary = self.build(
            displacement=[0.0, -1.0, -2.0], reaction=[0.0, -50.0, -100.0])
        self.assertAlmostEqual(strain[0], 0.0)
        self.assertAlmostEqual(strain[-1], 0.2)
        self.assertAlmostEqual(stress[-1], 1.0)
        self.assertGreater(stress[-1], 0.0, "compression stress must be reported positive")
        self.assertEqual(summary["sign_convention"],
                         "compression positive: strain = -U3/H0, stress = -RF3/A0")
        self.assertAlmostEqual(summary["final_strain"], 0.2)
        self.assertAlmostEqual(summary["max_stress_MPa"], 1.0)
        self.assertEqual(summary["points"], 3)
        self.assertEqual(summary["wall_time_s"], 12.5)
        self.assertEqual(list(columns["time_s"]), [0.0, 0.1, 0.2])

    def test_energy_variables_and_ke_ie_ratio(self):
        columns, _, _, summary = self.build(
            displacement=[0.0, -2.0], reaction=[0.0, -100.0],
            energy={"ALLIE": [0.0, 4.0], "ALLKE": [0.0, 1.0], "ALLAE": [0.0, 0.1]})
        self.assertEqual(summary["energy_variables"], ["ALLIE", "ALLKE", "ALLAE"])
        self.assertAlmostEqual(summary["max_ke_ie_ratio"], 0.25)
        self.assertFalse(summary["energy_interpolated"])
        self.assertIn("ALLKE", columns)

    def test_a_missing_energy_variable_is_reported_not_invented(self):
        columns, _, _, summary = self.build(
            displacement=[0.0, -2.0], reaction=[0.0, -100.0],
            energy={"ALLIE": [0.0, 4.0]}, missing={"nodes": [], "energy": ["ALLKE"]})
        self.assertNotIn("ALLKE", columns)
        self.assertIsNone(summary["max_ke_ie_ratio"])
        self.assertEqual(summary["missing"]["energy"], ["ALLKE"])

    def test_energy_on_a_different_time_axis_is_interpolated_and_flagged(self):
        columns, _, _, summary = self.build(
            displacement=[0.0, -1.0, -2.0], reaction=[0.0, -50.0, -100.0],
            energy={"ALLIE": [0.0, 4.0]}, energy_times=[0.0, 0.2])
        self.assertTrue(summary["energy_interpolated"])
        self.assertEqual(len(columns["ALLIE"]), 3)
        self.assertAlmostEqual(columns["ALLIE"][1], 2.0)

    def test_without_u3_or_rf3_extraction_refuses_to_guess(self):
        base = raw_history(displacement=[0.0, -2.0], reaction=[0.0, -100.0])
        del base["nodes"]["RP_TOP"]["series"]["U3"]
        with self.assertRaises(PipelineError) as caught:
            build_results(base, case_id="mini", solver="standard_dynamic_implicit",
                          height_mm=10.0, area_mm2=100.0, target_strain=0.2)
        self.assertEqual(caught.exception.code, "EXTRACT_INCOMPLETE")
        base = raw_history(displacement=[0.0, -2.0], reaction=[0.0, -100.0])
        del base["nodes"]["RP_TOP"]["series"]["RF3"]
        with self.assertRaises(PipelineError) as caught:
            build_results(base, case_id="mini", solver="standard_dynamic_implicit",
                          height_mm=10.0, area_mm2=100.0, target_strain=0.2)
        self.assertEqual(caught.exception.code, "EXTRACT_INCOMPLETE")

    def test_written_files_have_the_same_shape_for_both_solvers(self):
        for solver in ("standard_dynamic_implicit", "explicit_dynamic"):
            with self.subTest(solver=solver):
                folder = Path(tempfile.mkdtemp(prefix="results_"))
                raw = raw_history(displacement=[0.0, -2.0], reaction=[0.0, -100.0],
                                  energy={"ALLIE": [0.0, 4.0], "ALLKE": [0.0, 1.0]})
                columns, strain, stress, summary = build_results(
                    raw, case_id="mini", solver=solver, height_mm=10.0, area_mm2=100.0,
                    target_strain=0.2)
                write_results(folder, columns, strain, stress, summary)
                with (folder / "history.csv").open(encoding="utf-8", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(sorted(rows[0]),
                                 ["ALLIE", "ALLKE", "rf3_N", "time_s", "u3_mm"],
                                 "history.csv uses the canonical curve_qa column schema")
                self.assertEqual(len(rows), 2)
                with (folder / "stress_strain.csv").open(encoding="utf-8", newline="") as stream:
                    curve = list(csv.reader(stream))
                self.assertEqual(curve[0], ["engineering_strain", "engineering_stress_MPa"])
                self.assertEqual(len(curve), 3, "the full curve is kept, not a sampled subset")
                self.assertEqual(read_json(folder / "summary.json")["solver"], solver)


class WorkerInvocationTests(unittest.TestCase):
    def test_worker_runs_under_abaqus_python_with_the_build_labels(self):
        calls = []

        def fake_run(argv, **kwargs):
            calls.append(argv)

            class Completed:
                returncode = 0
                stdout = ""
                stderr = ""

            Path(argv[argv.index("--out") + 1]).write_text(
                json.dumps(raw_history(displacement=[0.0, -2.0], reaction=[0.0, -100.0])),
                encoding="utf-8")
            return Completed()

        folder = Path(tempfile.mkdtemp(prefix="worker_"))
        launcher = folder / "fake_abaqus.bat"
        launcher.write_text("@echo off\r\n", encoding="ascii")
        raw_path = folder / "raw.json"
        original = extract_module.subprocess.run
        extract_module.subprocess.run = fake_run
        try:
            raw = extract_module.export_raw(Path("job.odb"), raw_path, step="Compression",
                                            node_labels={"RP_TOP": 13, "RP_X_CTRL": 10,
                                                         "RP_Y_CTRL": 11},
                                            node_variables=("U3", "RF3"),
                                            energy_variables=("ALLIE",),
                                            abaqus_command=str(launcher))
        finally:
            extract_module.subprocess.run = original
        argv = calls[0]
        self.assertEqual(argv[0], str(launcher))
        self.assertEqual(argv[1], "python")
        self.assertTrue(argv[2].endswith("export_history.py"))
        self.assertIn("--odb", argv)
        self.assertIn("RP_TOP=13", argv)
        self.assertIn("U3,RF3", argv)
        self.assertEqual(raw["status"], "RAW_HISTORY_EXPORTED")

    def test_a_failing_worker_is_an_explicit_error(self):
        def fake_run(argv, **kwargs):
            class Completed:
                returncode = 1
                stdout = "traceback"
                stderr = "EXPORT FAILED"

            return Completed()

        folder = Path(tempfile.mkdtemp(prefix="worker_"))
        launcher = folder / "fake_abaqus.bat"
        launcher.write_text("@echo off\r\n", encoding="ascii")
        original = extract_module.subprocess.run
        extract_module.subprocess.run = fake_run
        try:
            with self.assertRaises(PipelineError) as caught:
                extract_module.export_raw(Path("job.odb"), Path("nowhere.json"),
                                          step="Compression", node_labels={},
                                          node_variables=("U3",),
                                          energy_variables=("ALLIE",),
                                          abaqus_command=str(launcher))
        finally:
            extract_module.subprocess.run = original
        self.assertEqual(caught.exception.code, "EXTRACT_FAILED")


class ExtractRerunTests(unittest.TestCase):
    """Re-running extraction in the same case directory must succeed.

    The Abaqus Python worker refuses an existing --out path, so extract() has to
    remove the stale raw_history.json intermediate itself. The fake worker below
    enforces the same guard the real worker has, so this test fails if the
    removal disappears again.
    """

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="rerun_"))
        self.addCleanup(lambda: shutil.rmtree(self.folder, ignore_errors=True))
        self.deck = self.folder / "abaqus"
        self.deck.mkdir()
        (self.deck / "job.odb").write_bytes(b"odb")
        write_json(self.deck / "build_report.json",
                   {"status": "BUILT", "case_id": "mini",
                    "deck": {"files": {"physical.inp": "deck-sha-1"}},
                    "model": {"labels": {"rp_top": 13, "rp_x": 10, "rp_y": 11},
                              "height_mm": 10.0, "reference_area_mm2": 100.0},
                    "simulation": {"solver": {"type": "standard_dynamic_implicit"},
                                   "loading": {"target_compression_strain": 0.2}}})
        write_json(self.deck / "solve_report.json",
                   {"status": "SOLVE_COMPLETED",
                    "abaqus_output": {"odb": {"path": "job.odb"}}})
        self.launcher = self.folder / "fake_abaqus.bat"
        self.launcher.write_text("@echo off\r\n", encoding="ascii")

    def extract_with_guarded_worker(self, results_dir, runs):
        """extract() with a fake worker that mimics the real existing-output guard."""

        def fake_run(argv, **kwargs):
            out = Path(argv[argv.index("--out") + 1])
            if out.exists():  # the real worker raises "Output already exists"
                class Failed:
                    returncode, stdout, stderr = 1, "", "Output already exists"
                return Failed()
            runs.append(out)
            out.write_text(json.dumps(raw_history(displacement=[0.0, -2.0],
                                                  reaction=[0.0, -100.0])),
                           encoding="utf-8")

            class Completed:
                returncode, stdout, stderr = 0, "", ""
            return Completed()

        original = extract_module.subprocess.run
        extract_module.subprocess.run = fake_run
        try:
            return extract_module.extract(self.deck, results_dir, case_id="mini",
                                          abaqus_command=str(self.launcher), log=lambda m: None)
        finally:
            extract_module.subprocess.run = original

    def test_second_extraction_overwrites_the_raw_intermediate(self):
        runs = []
        results = self.folder / "results"
        first = self.extract_with_guarded_worker(results, runs)
        second = self.extract_with_guarded_worker(results, runs)
        self.assertEqual(len(runs), 2, "the second extraction must re-export, not fail")
        self.assertEqual(second["points"], first["points"])
        self.assertEqual(second["final_strain"], first["final_strain"])

    def test_summary_records_the_deck_root_sha(self):
        summary = self.extract_with_guarded_worker(self.folder / "results", runs=[])
        self.assertEqual(summary["deck_root_sha256"], "deck-sha-1")
        self.assertEqual(read_json(self.folder / "results" / "summary.json")["deck_root_sha256"],
                         "deck-sha-1")


if __name__ == "__main__":
    unittest.main()
