"""run-case orchestration: stage order, failure stops, resume and config invalidation.

Every stage function is replaced by a fake that records its call and writes exactly
the evidence file the resume logic looks for. No Abaqus, no mesh, no CGAL.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import run_case as run_case_module                        # noqa: E402
from pipeline.common import PipelineError, read_json, write_json        # noqa: E402
from pipeline.run_case import STAGES, run_case                          # noqa: E402
from sandbox import CASE, write_simulation                              # noqa: E402


class Recorder:
    """Fake stage functions that record calls and write minimal success evidence."""

    def __init__(self, fail=None, interrupt=None):
        self.calls = []
        self.fail = fail or set()
        self.interrupt = interrupt or set()

    def _note(self, stage, work_dir):
        self.calls.append(stage)
        if stage in self.interrupt:
            raise KeyboardInterrupt("user pressed Ctrl+C")
        if stage in self.fail:
            raise PipelineError("FAKE_" + stage.upper() + "_FAILED", stage + " failed on purpose")

    def mesh(self, case_path, mesh_dir, log, cgal_executable=None, case_document=None):
        self._note("mesh", mesh_dir)
        Path(mesh_dir).mkdir(parents=True, exist_ok=True)
        empty = Path(mesh_dir) / "synthetic"
        empty.mkdir(parents=True, exist_ok=True)
        for name in ("shell.npz", "shell_report.json", "periodic_pairs.csv"):
            (empty / name).write_text("{}", encoding="utf-8")
        write_json(Path(mesh_dir) / "mesh_result.json",
                   {"case_id": "fig1", "npz": str(empty / "shell.npz"),
                    "report": str(empty / "shell_report.json"),
                    "pairs_csv": str(empty / "periodic_pairs.csv")})

    def mesh_datacheck(self, mesh_result, **kwargs):
        self._note("mesh_datacheck", None)
        write_json(Path(mesh_result["npz"]).parent.parent / "meshcheck_report.json",
                   {"status": "PASSED"})

    def build(self, npz, report, pairs, simulation, deck_dir):
        self._note("build", deck_dir)
        Path(deck_dir).mkdir(parents=True, exist_ok=True)
        write_json(Path(deck_dir) / "build_report.json",
                   {"status": "BUILT", "deck": {"files": {"physical.inp": "build-sha"}}})

    def datacheck(self, deck_dir, **kwargs):
        self._note("datacheck", deck_dir)
        write_json(Path(deck_dir) / "datacheck_report.json",
                   {"status": "DATACHECK_PASSED", "deck": {"files": {"physical.inp": "build-sha"}}})

    def solve(self, deck_dir, **kwargs):
        self._note("solve", deck_dir)
        (Path(deck_dir) / "job.odb").write_bytes(b"odb")
        write_json(Path(deck_dir) / "solve_report.json",
                   {"status": "SOLVE_COMPLETED", "deck": {"files": {"physical.inp": "build-sha"}},
                    "abaqus_output": {"odb": {"path": "job.odb"}}})

    def extract(self, deck_dir, results_dir, **kwargs):
        self._note("extract", results_dir)
        Path(results_dir).mkdir(parents=True, exist_ok=True)
        for name in ("history.csv", "stress_strain.csv"):
            (Path(results_dir) / name).write_text("a,b\n0,0\n", encoding="utf-8")
        write_json(Path(results_dir) / "summary.json", {"success": True, "points": 11})


class RunCaseTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.case = self.root / "case.json"
        self.case.write_text(json.dumps(json.loads(Path(CASE).read_text(encoding="utf-8"))),
                             encoding="utf-8")
        self.simulation = write_simulation(self.root, name="simulation.json")
        self.work_root = self.root / "work"
        self.runtime = self.root / "runtime.json"
        self.runtime.write_text(json.dumps(
            {"abaqus": {"launcher": None, "release_required": "2026"},
             "cgal": {"executable": None},
             "datacheck": {"cpus": 1, "timeout_s": 60},
             "solve": {"cpus": 2, "timeout_s": 60}}), encoding="utf-8")

    def run_with(self, recorder, **kwargs):
        patches = [mock.patch.object(run_case_module, "run_mesh", recorder.mesh),
                   mock.patch.object(run_case_module, "run_mesh_datacheck",
                                     recorder.mesh_datacheck),
                   mock.patch.object(run_case_module, "build", recorder.build),
                   mock.patch.object(run_case_module, "run_datacheck", recorder.datacheck),
                   mock.patch.object(run_case_module, "run_solve", recorder.solve),
                   mock.patch.object(run_case_module, "extract", recorder.extract)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return run_case(self.case, self.simulation, work_root=self.work_root,
                        runtime_path=self.runtime, log=lambda message: None, **kwargs)

    def status(self):
        return read_json(self.work_root / "fig1" / "status.json")

    def test_stages_run_in_order_and_the_case_finishes(self):
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertEqual(recorder.calls, list(STAGES))
        self.assertEqual(status["status"], "DONE")
        self.assertEqual(status["case_id"], "fig1")
        self.assertEqual(status["solver"], "standard_dynamic_implicit")
        self.assertEqual({name: entry["status"] for name, entry in status["stages"].items()},
                         {name: "DONE" for name in STAGES})
        self.assertTrue((self.work_root / "fig1" / "run.log").is_file())

    def test_each_stage_failure_stops_the_pipeline_and_is_recorded(self):
        for stage in STAGES:
            with self.subTest(stage=stage):
                if self.work_root.exists():
                    shutil.rmtree(self.work_root)
                recorder = Recorder(fail={stage})
                with self.assertRaises(PipelineError):
                    self.run_with(recorder)
                self.assertEqual(recorder.calls[-1], stage)
                self.assertEqual(recorder.calls, list(STAGES[:STAGES.index(stage) + 1]))
                status = self.status()
                self.assertEqual(status["stage"], stage)
                self.assertEqual(status["status"], "FAKE_" + stage.upper() + "_FAILED")
                self.assertTrue(status["message"])

    def test_resume_skips_finished_stages(self):
        self.run_with(Recorder())
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertEqual(recorder.calls, [], "a finished case must not redo any stage")
        self.assertEqual(status["status"], "DONE")

    def test_resume_reruns_from_the_first_incomplete_stage(self):
        recorder = Recorder(fail={"solve"})
        with self.assertRaises(PipelineError):
            self.run_with(recorder)
        self.assertEqual(recorder.calls, list(STAGES[:5]))
        # Without the solve report the solve (and extraction) must run again; the
        # earlier stages are kept.
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertEqual(recorder.calls, ["solve", "extract"])
        self.assertEqual(status["status"], "DONE")

    def test_a_changed_simulation_config_invalidates_build_onwards(self):
        self.run_with(Recorder())
        changed = write_simulation(self.root, name="simulation_changed.json",
                                   mutate=lambda doc: doc["contact"].update(friction=0.3))
        recorder = Recorder()
        patches = [mock.patch.object(run_case_module, "run_mesh", recorder.mesh),
                   mock.patch.object(run_case_module, "run_mesh_datacheck",
                                     recorder.mesh_datacheck),
                   mock.patch.object(run_case_module, "build", recorder.build),
                   mock.patch.object(run_case_module, "run_datacheck", recorder.datacheck),
                   mock.patch.object(run_case_module, "run_solve", recorder.solve),
                   mock.patch.object(run_case_module, "extract", recorder.extract)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        status = run_case(self.case, changed, work_root=self.work_root,
                          runtime_path=self.runtime, log=lambda message: None)
        self.assertEqual(recorder.calls, ["build", "datacheck", "solve", "extract"])
        self.assertEqual(status["status"], "DONE")
        self.assertTrue(list((self.work_root / "fig1").glob("abaqus.previous_*")),
                        "the superseded deck must be kept, not overwritten")

    def test_a_changed_case_config_invalidates_every_stage(self):
        self.run_with(Recorder())
        case = json.loads(self.case.read_text(encoding="utf-8"))
        case["iso_level"] = 0.05
        self.case.write_text(json.dumps(case), encoding="utf-8")
        recorder = Recorder()
        self.run_with(recorder)
        self.assertEqual(recorder.calls, list(STAGES))

    def test_the_case_config_sha_is_content_based_not_file_based(self):
        """The same case as a file or as a merged batch record is the same case."""
        self.run_with(Recorder())
        status = self.status()
        document = read_json(self.work_root / "fig1" / "case_used.json")
        # Re-formatting the file must not look like a configuration change.
        pretty = self.root / "case_pretty.json"
        pretty.write_text(json.dumps(document, indent=4, sort_keys=True), encoding="utf-8")
        recorder = Recorder()
        run_case(pretty, self.simulation, work_root=self.work_root,
                 runtime_path=self.runtime, log=lambda message: None)
        self.assertEqual(recorder.calls, [])
        self.assertEqual(read_json(self.work_root / "fig1" / "status.json")["status"], "DONE")
        self.assertEqual(status["case_config_sha256"],
                         self.status()["case_config_sha256"])

    def test_force_reruns_everything(self):
        self.run_with(Recorder())
        recorder = Recorder()
        self.run_with(recorder, force=True)
        self.assertEqual(recorder.calls, list(STAGES))

    def test_a_stale_running_status_resumes_instead_of_sticking(self):
        recorder = Recorder(interrupt={"solve"})
        with self.assertRaises(KeyboardInterrupt):
            self.run_with(recorder)
        status = self.status()
        self.assertEqual(status["status"], "RUNNING")
        self.assertEqual(status["stage"], "solve")
        # The next start treats it as interrupted and resumes from the solve stage.
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertEqual(recorder.calls, ["solve", "extract"])
        self.assertEqual(status["status"], "DONE")
        self.assertEqual(status["recovered_from"], "INTERRUPTED")

    def test_a_stale_running_status_with_complete_results_is_done(self):
        self.run_with(Recorder())
        status_path = self.work_root / "fig1" / "status.json"
        document = read_json(status_path)
        document["status"] = "RUNNING"
        document["stage"] = "extract"
        write_json(status_path, document)
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertEqual(recorder.calls, [], "complete results must be accepted, not recomputed")
        self.assertEqual(status["status"], "DONE")
        self.assertEqual(status["recovered_from"], "INTERRUPTED")

    def test_an_interrupted_mesh_engine_is_moved_aside(self):
        recorder = Recorder(interrupt={"mesh"})
        with self.assertRaises(KeyboardInterrupt):
            self.run_with(recorder)
        engine = self.work_root / "fig1" / "mesh" / "engine"
        engine.mkdir(parents=True, exist_ok=True)
        (engine / "half_written.txt").write_text("partial", encoding="utf-8")
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertIn("mesh", recorder.calls)
        self.assertEqual(status["status"], "DONE")
        self.assertFalse(engine.exists())
        leftovers = list((self.work_root / "fig1" / "mesh").glob("engine.previous_interrupted*"))
        self.assertEqual(len(leftovers), 1, "the partial engine is kept as evidence")

    def test_an_interrupted_build_is_retried_without_a_stuck_directory(self):
        recorder = Recorder(fail={"build"})
        with self.assertRaises(PipelineError):
            self.run_with(recorder)
        deck_dir = self.work_root / "fig1" / "abaqus"
        deck_dir.mkdir(parents=True, exist_ok=True)
        (deck_dir / "half_written.inc").write_text("partial", encoding="utf-8")
        recorder = Recorder()
        status = self.run_with(recorder)
        self.assertIn("build", recorder.calls)
        self.assertEqual(status["status"], "DONE")
        self.assertTrue((deck_dir / "build_report.json").is_file())
        leftovers = list((self.work_root / "fig1").glob("abaqus.previous_incomplete*"))
        self.assertEqual(len(leftovers), 1, "the partial deck is kept as evidence")
        self.assertTrue((leftovers[0] / "half_written.inc").is_file())

    def test_per_case_config_snapshots_are_written(self):
        self.run_with(Recorder())
        work_dir = self.work_root / "fig1"
        case_used = read_json(work_dir / "case_used.json")
        simulation_used = read_json(work_dir / "simulation_used.json")
        self.assertEqual(case_used["case_id"], "fig1")
        self.assertEqual(case_used["unit_cell_size_mm"], 10.0)
        self.assertEqual(simulation_used["solver"]["type"], "standard_dynamic_implicit")

    def test_stage_seconds_are_recorded(self):
        self.run_with(Recorder())
        stages = self.status()["stages"]
        self.assertEqual(sorted(stages), sorted(STAGES))
        for stage, entry in stages.items():
            self.assertEqual(entry["status"], "DONE")
            self.assertIn("seconds", entry)
            self.assertGreaterEqual(entry["seconds"], 0.0)

    def test_a_new_deck_invalidates_old_stage_reports(self):
        self.run_with(Recorder())
        work_dir = self.work_root / "fig1"
        # A datacheck report that belongs to an older deck must not count as done: the
        # stage reports are chained by the deck SHA256 they ran.
        build_path = work_dir / "abaqus" / "build_report.json"
        document = read_json(build_path)
        document["deck"]["files"]["physical.inp"] = "a-new-deck-sha"
        write_json(build_path, document)
        self.assertFalse(run_case_module._stage_done("datacheck", work_dir))


class OdbRetentionTests(unittest.TestCase):
    """runtime.results.keep_odb: drop the ODB only after a successful extraction."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.case = self.root / "case.json"
        self.case.write_text(json.dumps(json.loads(Path(CASE).read_text(encoding="utf-8"))),
                             encoding="utf-8")
        self.simulation = write_simulation(self.root, name="simulation.json")
        self.work_root = self.root / "work"
        self.runtime = self.root / "runtime.json"

    def status(self):
        return read_json(self.work_root / "fig1" / "status.json")

    def set_keep_odb(self, keep):
        self.runtime.write_text(json.dumps(
            {"abaqus": {"launcher": None, "release_required": "2026"},
             "cgal": {"executable": None},
             "results": {"keep_odb": keep},
             "datacheck": {"cpus": 1, "timeout_s": 60},
             "solve": {"cpus": 2, "timeout_s": 60}}), encoding="utf-8")

    def run_case_with(self, recorder):
        patches = [mock.patch.object(run_case_module, "run_mesh", recorder.mesh),
                   mock.patch.object(run_case_module, "run_mesh_datacheck",
                                     recorder.mesh_datacheck),
                   mock.patch.object(run_case_module, "build", recorder.build),
                   mock.patch.object(run_case_module, "run_datacheck", recorder.datacheck),
                   mock.patch.object(run_case_module, "run_solve", recorder.solve),
                   mock.patch.object(run_case_module, "extract", recorder.extract)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return run_case(self.case, self.simulation, work_root=self.work_root,
                        runtime_path=self.runtime, log=lambda message: None)

    def test_keep_odb_true_keeps_everything(self):
        self.set_keep_odb(True)
        self.run_case_with(Recorder())
        self.assertTrue((self.work_root / "fig1" / "abaqus" / "job.odb").is_file())
        self.assertNotIn("odb_removed", self.status())

    def test_keep_odb_false_removes_the_odb_after_extraction(self):
        self.set_keep_odb(False)
        self.run_case_with(Recorder())
        self.assertFalse((self.work_root / "fig1" / "abaqus" / "job.odb").exists())
        self.assertTrue((self.work_root / "fig1" / "abaqus" / "solve_report.json").is_file(),
                        "only the ODB is removed; reports and logs stay")
        self.assertTrue((self.work_root / "fig1" / "results" / "summary.json").is_file())
        self.assertEqual(self.status()["odb_removed"][0][0], "job.odb")

    def test_a_failed_case_keeps_its_odb(self):
        self.set_keep_odb(False)
        with self.assertRaises(PipelineError):
            self.run_case_with(Recorder(fail={"extract"}))
        self.assertTrue((self.work_root / "fig1" / "abaqus" / "job.odb").is_file(),
                        "a case that never extracted must keep its ODB")


if __name__ == "__main__":
    unittest.main()
