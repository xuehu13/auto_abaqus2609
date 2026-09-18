"""Batch driver: case list -> run_case() per case, one batch directory.

run_case() is replaced by a fake that writes exactly the evidence files a real case
produces (status.json, results/summary.json), so the batch logic is exercised without
Abaqus, CGAL or meshes.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import batch as batch_module                              # noqa: E402
from pipeline.batch import (DONE, INTERRUPTED, PENDING, SUMMARY_COLUMNS,   # noqa: E402
                            case_state, load_cases, merge_case, rebuild_summary, run_batch)
from pipeline.common import PipelineError, read_json, write_json        # noqa: E402
from sandbox import write_simulation                                    # noqa: E402

DEFAULT_CASE = {"iso_level": 0.0, "unit_cell_size_mm": 10.0}
#: The batch sandbox uses the real config/case_defaults.json: the tests then also
#: prove that the shipped defaults pass case validation.
REAL_DEFAULTS = ROOT / "config" / "case_defaults.json"
MESH_BLOCK = json.loads(REAL_DEFAULTS.read_text(encoding="utf-8"))["mesh"]


class FakeRunCase:
    """Stand-in for run_case: writes the case's evidence files, per case behaviour."""

    def __init__(self, behaviour=None):
        self.behaviour = behaviour or {}
        self.calls = []
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def __call__(self, case_path, simulation_path, *, case_document=None, work_root=None,
                 **kwargs):
        case_id = case_document["case_id"]
        action = self.behaviour.get(case_id, "done")
        with self.lock:
            self.calls.append({"case_id": case_id, "document": case_document,
                               "work_root": str(work_root), "kwargs": kwargs})
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.02)
            work_dir = Path(work_root) / case_id
            work_dir.mkdir(parents=True, exist_ok=True)
            write_json(work_dir / "case_used.json", case_document)
            shutil.copy2(simulation_path, work_dir / "simulation_used.json")
            if action == "fail":
                return self._fail(work_dir, case_id, "mesh")
            if action.startswith("fail:"):
                return self._fail(work_dir, case_id, action.split(":")[1])
            if action == "running_incomplete":
                write_json(work_dir / "status.json",
                           {"case_id": case_id, "status": "RUNNING", "stage": "solve",
                            "solver": "standard_dynamic_implicit"})
                return {"status": "RUNNING"}
            if action == "interrupt":
                write_json(work_dir / "status.json",
                           {"case_id": case_id, "status": "RUNNING", "stage": "solve",
                            "solver": "standard_dynamic_implicit",
                            "stages": {"mesh": {"status": "DONE", "seconds": 1.0}}})
                raise KeyboardInterrupt("user pressed Ctrl+C")
            return self._done(work_dir, case_id)
        finally:
            with self.lock:
                self.active -= 1

    def _fail(self, work_dir, case_id, stage):
        write_json(work_dir / "status.json",
                   {"case_id": case_id, "status": stage.upper() + "_FAILED", "stage": stage,
                    "message": stage + " failed on purpose",
                    "solver": "standard_dynamic_implicit",
                    "stages": {"mesh": {"status": "DONE", "seconds": 1.0}}})
        raise PipelineError(stage.upper() + "_FAILED", stage + " failed on purpose")

    def _done(self, work_dir, case_id):
        write_json(work_dir / "status.json",
                   {"case_id": case_id, "status": "DONE", "stage": "done",
                    "solver": "standard_dynamic_implicit",
                    "stages": {stage: {"status": "DONE", "seconds": 2.0}
                               for stage in batch_module.STAGES}})
        results = work_dir / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "history.csv").write_text("time_s,u3_mm\n0,0\n", encoding="utf-8")
        (results / "stress_strain.csv").write_text(
            "engineering_strain,engineering_stress_MPa\n0,0\n", encoding="utf-8")
        write_json(results / "summary.json",
                   {"case_id": case_id, "solver": "standard_dynamic_implicit", "success": True,
                    "points": 11, "final_strain": 0.2, "max_stress_MPa": 0.31,
                    "max_ke_ie_ratio": None})
        return {"status": "DONE"}


class BatchSandbox(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.cases_path = self.root / "cases.jsonl"
        self.defaults_path = self.root / "case_defaults.json"
        write_json(self.defaults_path, dict(DEFAULT_CASE, mesh=dict(MESH_BLOCK)))
        self.simulation = write_simulation(self.root, name="simulation.json")
        self.work_root = self.root / "batch_001"

    def write_cases(self, records):
        with self.cases_path.open("w", encoding="utf-8", newline="\n") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")

    def run_batch(self, fake, **kwargs):
        with mock.patch.object(batch_module, "run_case", fake):
            return run_batch(self.cases_path, self.simulation, defaults_path=self.defaults_path,
                             work_root=self.work_root, log=lambda message: None, **kwargs)

    def summary_rows(self):
        with (self.work_root / "batch_summary.csv").open(encoding="utf-8", newline="") as stream:
            return list(csv.DictReader(stream))

    def jsonl(self, name):
        path = self.work_root / name
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class CaseLoadingTests(BatchSandbox):
    def test_jsonl_cases_are_read_and_merged_with_the_defaults(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X",
                           "overrides": {"unit_cell_size_mm": 12.0}}])
        cases = load_cases(self.cases_path, self.defaults_path)
        self.assertEqual([case["case_id"] for case in cases], ["case_A", "case_B"])
        self.assertEqual(cases[0]["document"]["mesh"], MESH_BLOCK)
        self.assertEqual(cases[0]["document"]["unit_cell_size_mm"], 10.0)
        self.assertEqual(cases[1]["document"]["unit_cell_size_mm"], 12.0)
        self.assertEqual(cases[1]["document"]["mesh"]["cgal"]["edge_size_mm"], 0.18)

    def test_a_case_can_override_a_nested_value_directly(self):
        self.write_cases([{"case_id": "case_C", "surface_expression": "0.1*X",
                           "mesh": {"boundary_target_spacing_mm": 0.25}}])
        cases = load_cases(self.cases_path, self.defaults_path)
        mesh = cases[0]["document"]["mesh"]
        self.assertEqual(mesh["boundary_target_spacing_mm"], 0.25)
        self.assertEqual(mesh["topology_sampling_intervals"], 100)
        self.assertEqual(mesh["cgal"]["edge_size_mm"], 0.18)

    def test_duplicate_case_id_stops_the_batch(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_A", "surface_expression": "0.2*X"}])
        with self.assertRaises(PipelineError) as caught:
            load_cases(self.cases_path, self.defaults_path)
        self.assertEqual(caught.exception.code, "CASES_FILE_INVALID")
        self.assertIn("Duplicate case_id", str(caught.exception))

    def test_unsafe_or_missing_fields_are_rejected(self):
        self.write_cases([{"case_id": "../evil", "surface_expression": "0.1*X"}])
        with self.assertRaises(PipelineError):
            load_cases(self.cases_path, self.defaults_path)
        self.write_cases([{"case_id": "case_A"}])
        with self.assertRaises(PipelineError) as caught:
            load_cases(self.cases_path, self.defaults_path)
        self.assertIn("missing", str(caught.exception))

    def test_broken_jsonl_stops_the_batch(self):
        self.cases_path.write_text('{"case_id": "case_A", \n', encoding="utf-8")
        with self.assertRaises(PipelineError) as caught:
            load_cases(self.cases_path, self.defaults_path)
        self.assertEqual(caught.exception.code, "CASES_FILE_INVALID")

    def test_broken_defaults_stop_the_batch(self):
        write_json(self.defaults_path, {"iso_level": 0.0})
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        with self.assertRaises(PipelineError):
            load_cases(self.cases_path, self.defaults_path)

    def test_comments_and_blank_lines_are_ignored(self):
        self.cases_path.write_text(
            "# a comment\n\n{\"case_id\": \"case_A\", \"surface_expression\": \"0.1*X\"}\n",
            encoding="utf-8")
        cases = load_cases(self.cases_path, self.defaults_path)
        self.assertEqual(len(cases), 1)


class BatchRunTests(BatchSandbox):
    def test_every_case_goes_through_run_case(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        fake = FakeRunCase()
        result = self.run_batch(fake)
        self.assertEqual([call["case_id"] for call in fake.calls], ["case_A", "case_B"])
        self.assertEqual(result["DONE"], 2)
        self.assertEqual(result["FAILED"], 0)
        # run_case receives the MERGED case document and the batch directory.
        document = fake.calls[0]["document"]
        self.assertEqual(document["mesh"]["topology_sampling_intervals"], 100)
        self.assertEqual(fake.calls[0]["work_root"], str(self.work_root))

    def test_one_failed_case_does_not_stop_the_others(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"},
                          {"case_id": "case_C", "surface_expression": "0.3*X"}])
        fake = FakeRunCase({"case_B": "fail:solve"})
        result = self.run_batch(fake)
        self.assertEqual([call["case_id"] for call in fake.calls],
                         ["case_A", "case_B", "case_C"])
        self.assertEqual((result["DONE"], result["FAILED"]), (2, 1))
        rows = {row["case_id"]: row for row in self.summary_rows()}
        self.assertEqual(rows["case_B"]["status"], "SOLVE_FAILED")
        self.assertEqual(rows["case_B"]["failed_stage"], "solve")
        self.assertEqual(rows["case_B"]["points"], "")
        self.assertEqual(rows["case_A"]["status"], DONE)

    def test_a_fatal_error_stops_the_batch_before_the_next_case(self):
        """A case whose Abaqus tree survived termination must stop the whole batch:
        no later case may start, and the summary still records what happened."""
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"},
                          {"case_id": "case_C", "surface_expression": "0.3*X"}])
        calls = []

        def fatal_case(case_path, simulation_path, *, case_document=None, work_root=None,
                       **kwargs):
            case_id = case_document["case_id"]
            calls.append(case_id)
            if case_id == "case_B":
                work_dir = Path(work_root) / case_id
                write_json(work_dir / "status.json",
                           {"case_id": case_id, "status": "ABAQUS_TREE_NOT_TERMINATED",
                            "stage": "solve", "solver": "standard_dynamic_implicit",
                            "message": "solver tree survived termination"})
                raise PipelineError("ABAQUS_TREE_NOT_TERMINATED",
                                    "solver tree survived termination", fatal=True)
            return None

        with mock.patch.object(batch_module, "run_case", fatal_case):
            with self.assertRaises(PipelineError) as caught:
                run_batch(self.cases_path, self.simulation, defaults_path=self.defaults_path,
                          work_root=self.work_root, log=lambda message: None)
        self.assertEqual(caught.exception.code, "ABAQUS_TREE_NOT_TERMINATED")
        self.assertTrue(caught.exception.fatal)
        self.assertEqual(calls, ["case_A", "case_B"],
                         "case_C must not start after a fatal tree failure")
        rows = {row["case_id"]: row for row in self.summary_rows()}
        self.assertEqual(rows["case_B"]["status"], "ABAQUS_TREE_NOT_TERMINATED")
        self.assertEqual(rows["case_C"]["status"], PENDING)

    def test_done_cases_are_skipped_on_the_next_run(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase())
        fake = FakeRunCase()
        result = self.run_batch(fake)
        self.assertEqual(fake.calls, [])
        self.assertEqual(result["DONE"], 2)
        self.assertEqual(len(self.summary_rows()), 2)

    def test_failed_cases_are_skipped_unless_retry_failed(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase({"case_B": "fail:mesh"}))
        fake = FakeRunCase()
        self.run_batch(fake)
        self.assertEqual(fake.calls, [], "a failed case is skipped by default")
        fake = FakeRunCase()
        result = self.run_batch(fake, retry_failed=True)
        self.assertEqual([call["case_id"] for call in fake.calls], ["case_B"])
        self.assertEqual(result["DONE"], 2)

    def test_an_interrupted_case_is_resumed(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        # A case interrupted mid-run: status RUNNING, no result files.
        self.run_batch(FakeRunCase({"case_B": "running_incomplete"}))
        fake = FakeRunCase()
        result = self.run_batch(fake)
        self.assertEqual([call["case_id"] for call in fake.calls], ["case_B"])
        self.assertEqual(result["DONE"], 2)

    def test_an_interrupted_case_with_complete_results_counts_as_done(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        self.run_batch(FakeRunCase())
        # Simulate a process killed right after writing results, before status.
        status_path = self.work_root / "case_A" / "status.json"
        document = read_json(status_path)
        document["status"] = "RUNNING"
        document["stage"] = "extract"
        write_json(status_path, document)
        self.assertEqual(case_state(self.work_root / "case_A")["status"], DONE)
        fake = FakeRunCase()
        self.run_batch(fake)
        self.assertEqual(fake.calls, [], "complete results must not be recomputed")
        # The stale RUNNING must not be left behind for the next reader.
        settled = read_json(status_path)
        self.assertEqual(settled["status"], DONE)
        self.assertEqual(settled["recovered_from"], INTERRUPTED)

    def test_max_retries_uses_the_identical_config(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        fake = FakeRunCase({"case_A": "fail:solve"})
        self.run_batch(fake, retry_failed=True, max_retries=2)
        self.assertEqual(len(fake.calls), 3, "one attempt plus two retries")
        self.assertEqual(len({json.dumps(call["document"], sort_keys=True)
                              for call in fake.calls}), 1, "retries must not change the config")
        for call in fake.calls:
            self.assertFalse(call["kwargs"].get("force"), "retry must resume, not restart")

    def test_force_reruns_selected_cases_with_force(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        self.run_batch(FakeRunCase())
        fake = FakeRunCase()
        self.run_batch(fake, force=True)
        self.assertEqual([call["case_id"] for call in fake.calls], ["case_A"])
        self.assertTrue(fake.calls[0]["kwargs"]["force"])

    def test_workers_run_cases_concurrently_but_keep_separate_directories(self):
        self.write_cases([{"case_id": "case_%d" % index, "surface_expression": "0.1*X"}
                          for index in range(4)])
        fake = FakeRunCase()
        result = self.run_batch(fake, workers=2)
        self.assertEqual(result["DONE"], 4)
        self.assertGreaterEqual(fake.max_active, 2, "workers=2 must overlap")
        self.assertLessEqual(fake.max_active, 2)
        self.assertEqual(len({call["work_root"] for call in fake.calls}), 1)
        for row in self.summary_rows():
            self.assertTrue(
                (self.work_root / row["case_id"] / "results" / "summary.json").is_file())


class BatchOutputTests(BatchSandbox):
    def test_summary_csv_columns_and_values(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase({"case_B": "fail:datacheck"}))
        with (self.work_root / "batch_summary.csv").open(encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            rows = list(reader)
        self.assertEqual(reader.fieldnames, list(SUMMARY_COLUMNS))
        good, bad = rows[0], rows[1]
        self.assertEqual(good["case_id"], "case_A")
        self.assertEqual(good["surface_expression"], "0.1*X")
        self.assertEqual(good["solver"], "standard_dynamic_implicit")
        self.assertEqual(good["points"], "11")
        self.assertEqual(good["final_strain"], "0.2")
        self.assertEqual(good["solve_wall_time_s"], "2.0")
        self.assertEqual(good["total_wall_time_s"], "12.0")
        self.assertTrue(good["result_path"].endswith("case_A\\results")
                        or good["result_path"].endswith("case_A/results"))
        self.assertEqual(bad["status"], "DATACHECK_FAILED")
        self.assertEqual(bad["failed_stage"], "datacheck")
        self.assertEqual(bad["points"], "", "unknown values stay empty")
        self.assertEqual(bad["result_path"], "")
        self.assertIn("failed on purpose", bad["message"])
        self.assertEqual(len(bad["message"].splitlines()), 1,
                         "a failure message must stay on one CSV line")

    def test_a_multi_line_failure_message_is_collapsed_for_the_summary(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        fake = FakeRunCase({"case_A": "fail:mesh"})
        self.run_batch(fake)
        # The full text stays in the case's status.json, the summary keeps one line.
        status = read_json(self.work_root / "case_A" / "status.json")
        self.assertEqual(status["message"], "mesh failed on purpose")
        row = self.summary_rows()[0]
        self.assertEqual(row["message"], "mesh failed on purpose")
        self.assertIn("status_json", self.jsonl("failed_cases.jsonl")[0])

    def test_results_index_has_successful_cases_only(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase({"case_B": "fail:mesh"}))
        rows = self.jsonl("results_index.jsonl")
        self.assertEqual([row["case_id"] for row in rows], ["case_A"])
        self.assertEqual(rows[0]["surface_expression"], "0.1*X")
        self.assertEqual(rows[0]["solver"], "standard_dynamic_implicit")
        self.assertTrue(rows[0]["stress_strain_csv"].endswith("stress_strain.csv"))
        self.assertTrue(rows[0]["history_csv"].endswith("history.csv"))
        self.assertTrue(rows[0]["summary_json"].endswith("summary.json"))
        self.assertIn("case_A", rows[0]["stress_strain_csv"])

    def test_failed_cases_jsonl_has_failures_only(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase({"case_B": "fail:solve"}))
        rows = self.jsonl("failed_cases.jsonl")
        self.assertEqual([row["case_id"] for row in rows], ["case_B"])
        self.assertEqual(rows[0]["stage"], "solve")
        self.assertEqual(rows[0]["status"], "SOLVE_FAILED")
        self.assertIn("failed on purpose", rows[0]["message"])

    def test_batch_config_and_log_are_written(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
        self.run_batch(FakeRunCase())
        config = read_json(self.work_root / "batch_config.json")
        self.assertEqual(config["total_cases"], 1)
        self.assertEqual(config["workers"], 1)
        self.assertTrue(config["simulation_file"].endswith("simulation.json"))
        log = (self.work_root / "batch.log").read_text(encoding="utf-8")
        self.assertIn("case_A status=DONE", log)

    def test_worker_results_are_published_by_the_main_process_only(self):
        self.write_cases([{"case_id": "case_%d" % index, "surface_expression": "0.1*X"}
                          for index in range(3)])
        fake = FakeRunCase()
        self.run_batch(fake, workers=2)
        rows = self.summary_rows()
        self.assertEqual([row["case_id"] for row in rows],
                         ["case_0", "case_1", "case_2"], "rows stay in case order")
        self.assertEqual(len(self.jsonl("results_index.jsonl")), 3)

    def test_summary_can_be_rebuilt_from_the_case_directories(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"}])
        self.run_batch(FakeRunCase({"case_B": "fail:build"}))
        (self.work_root / "batch_summary.csv").unlink()
        (self.work_root / "results_index.jsonl").unlink()
        result = rebuild_summary(self.work_root, log=lambda message: None)
        self.assertEqual(result["DONE"], 1)
        rows = {row["case_id"]: row for row in self.summary_rows()}
        self.assertEqual(rows["case_A"]["status"], DONE)
        self.assertEqual(rows["case_B"]["status"], "BUILD_FAILED")
        self.assertEqual([row["case_id"] for row in self.jsonl("results_index.jsonl")],
                         ["case_A"])

    def test_case_state_reports_pending_for_an_untouched_case(self):
        state = case_state(self.root / "nothing_here")
        self.assertEqual(state["status"], PENDING)
        self.assertIsNone(state["result_path"])


class BatchInterruptTests(BatchSandbox):
    def test_ctrl_c_keeps_finished_cases_and_stops_starting_new_ones(self):
        self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"},
                          {"case_id": "case_B", "surface_expression": "0.2*X"},
                          {"case_id": "case_C", "surface_expression": "0.3*X"}])
        fake = FakeRunCase({"case_B": "interrupt"})
        result = self.run_batch(fake, workers=1)
        self.assertTrue(result["interrupted"])
        # The finished case keeps its results, the interrupted one stays resumable.
        self.assertEqual(read_json(self.work_root / "case_A" / "status.json")["status"], DONE)
        self.assertEqual(read_json(self.work_root / "case_B" / "status.json")["status"], "RUNNING")
        rows = {row["case_id"]: row["status"] for row in self.summary_rows()}
        self.assertEqual(rows["case_A"], DONE)
        self.assertEqual(rows["case_B"], INTERRUPTED)
        # The next run resumes exactly the interrupted case.
        fake = FakeRunCase()
        result = self.run_batch(fake)
        self.assertEqual([call["case_id"] for call in fake.calls], ["case_B"])
        self.assertEqual(result["DONE"], 3)

    def test_the_solver_of_the_simulation_config_is_reported(self):
        for solver in ("standard_dynamic_implicit", "explicit_dynamic"):
            with self.subTest(solver=solver):
                shutil.rmtree(self.work_root, ignore_errors=True)
                self.simulation = write_simulation(
                    self.root, name="simulation_%s.json" % solver,
                    mutate=lambda doc, name=solver: doc["solver"].update(type=name))
                self.write_cases([{"case_id": "case_A", "surface_expression": "0.1*X"}])
                fake = FakeRunCase()
                self.run_batch(fake)
                self.assertEqual(fake.calls[0]["kwargs"].get("force"), False)
                # The batch passes the simulation through untouched and reports its solver.
                self.assertEqual(read_json(self.work_root / "case_A" / "simulation_used.json")
                                 ["solver"]["type"], solver)
