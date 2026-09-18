"""run-experiment adapter: // comment stripping, production.json mapping, batch boundary."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import experiment as experiment_module                        # noqa: E402
from pipeline.abaqus import load_runtime                                    # noqa: E402
from pipeline.build import load_simulation                                  # noqa: E402
from pipeline.common import PipelineError, read_json                        # noqa: E402

PRODUCTION = ROOT / "config" / "experiments" / "production.json"


def mutate_document(mutation=None):
    document = experiment_module.load_production(PRODUCTION)
    if mutation is not None:
        mutation(document)
    return document


class CommentStrippingTests(unittest.TestCase):
    def test_whole_line_comments_are_dropped_and_values_kept(self):
        text = '// header note\n{"url": "http://x//y", "n": 1}\n   // tail note\n'
        stripped = experiment_module.strip_line_comments(text)
        self.assertFalse(any(line.lstrip().startswith("//")
                             for line in stripped.splitlines()),
                         "no whole-line comment may survive")
        self.assertEqual(json.loads(stripped), {"url": "http://x//y", "n": 1})

    def test_trailing_comments_are_not_supported_and_fail_loudly(self):
        broken = '{"a": 1} // trailing note\n'
        with self.assertRaises(ValueError):
            json.loads(experiment_module.strip_line_comments(broken))

    def test_missing_config_file_is_a_config_error(self):
        with self.assertRaises(PipelineError) as caught:
            experiment_module.load_production(ROOT / "config" / "experiments" / "nope.json")
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")


class ProductionMappingTests(unittest.TestCase):
    """The shipped production.json must map onto the documents the pipeline consumes."""

    def setUp(self):
        self.inputs = experiment_module.build_inputs(mutate_document())

    def test_experiment_block_drives_the_batch_arguments(self):
        self.assertEqual(self.inputs["experiment_id"], "production_v1")
        self.assertEqual(self.inputs["cases_path"], ROOT / "config" / "cases.jsonl")
        self.assertTrue(self.inputs["cases_path"].is_file())
        self.assertEqual(self.inputs["batch_dir"], ROOT / "work" / "production_v1")
        self.assertEqual((self.inputs["workers"], self.inputs["retry_failed"],
                          self.inputs["max_retries"], self.inputs["force"]), (1, False, 0, False))

    def test_case_defaults_come_from_geometry_and_mesh(self):
        defaults = self.inputs["case_defaults"]
        self.assertEqual(defaults["iso_level"], 0.0)
        self.assertEqual(defaults["unit_cell_size_mm"], 10.0)
        mesh = defaults["mesh"]
        self.assertEqual(mesh["topology_sampling_intervals"], 100)
        self.assertEqual(mesh["boundary_target_spacing_mm"], 0.18)
        self.assertEqual(mesh["cgal"]["random_seed"], 20260911)
        self.assertEqual(sorted(mesh["tolerances"]),
                         sorted(["snap_mm", "topology_pair_mm", "boundary_mm",
                                 "feature_plane_mm", "feature_periodic_mm", "dedup_mm",
                                 "final_pair_mm", "area_mm2"]))
        self.assertEqual(mesh["meshcheck"]["thickness_mm"], 1.0)

    def test_simulation_document_passes_the_real_config_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "simulation.json"
            path.write_text(json.dumps(self.inputs["simulation"]), encoding="utf-8")
            simulation = load_simulation(path)
        self.assertEqual(simulation["solver"]["type"], "standard_dynamic_implicit")
        self.assertEqual(simulation["shell"]["thickness_mode"], "relative_density")
        self.assertEqual(simulation["material"]["plastic_table"][0], [8.0, 0.0])
        self.assertEqual([request["kind"] for request in simulation["output"]["requests"]],
                         ["energy", "node", "node", "node"])

    def test_runtime_document_passes_the_real_runtime_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "runtime.json"
            path.write_text(json.dumps(self.inputs["runtime"]), encoding="utf-8")
            runtime = load_runtime(path)
        self.assertIsNone(runtime["abaqus"]["launcher"])
        self.assertEqual(runtime["solve"]["cpus"], 4)
        self.assertEqual(runtime["solve"]["timeout_s"], 14400)

    def test_unknown_category_and_missing_cases_file_are_rejected(self):
        with self.assertRaises(PipelineError):
            experiment_module.build_inputs(mutate_document(
                lambda doc: doc.update(mystery={})))
        with self.assertRaises(PipelineError) as caught:
            experiment_module.build_inputs(mutate_document(
                lambda doc: doc["experiment"].update(cases_file="config/no_such_cases.jsonl")))
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_solver_switch_stays_inside_the_existing_renderer_contract(self):
        def switch(doc):
            doc["solver"]["type"] = "explicit_dynamic"
        inputs = experiment_module.build_inputs(mutate_document(switch))
        self.assertEqual(inputs["simulation"]["solver"]["type"], "explicit_dynamic")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "simulation.json"
            path.write_text(json.dumps(inputs["simulation"]), encoding="utf-8")
            self.assertEqual(load_simulation(path)["solver"]["type"], "explicit_dynamic")


class StartExperimentTests(unittest.TestCase):
    """start_experiment snapshots the effective config and calls the EXISTING run_batch."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        cases_file = self.root / "cases.jsonl"
        cases_file.write_text('{"case_id": "case_00001", "surface_expression": "0.1*X"}\n',
                              encoding="utf-8")
        text = experiment_module.strip_line_comments(PRODUCTION.read_text(encoding="utf-8-sig"))
        self.document = json.loads(text)
        self.document["experiment"].update(cases_file=str(cases_file), work_root="work")
        self.config = self.root / "production.json"
        self.config.write_text(json.dumps(self.document), encoding="utf-8")

    def _start(self):
        calls = []

        def fake_run_batch(**kwargs):
            calls.append(kwargs)
            return {"batch_dir": str(kwargs["work_root"])}

        result = experiment_module.start_experiment(self.config, root=self.root,
                                                    run_batch_fn=fake_run_batch,
                                                    log=lambda m: None)
        return result, calls

    def test_snapshots_are_written_and_existing_batch_is_called(self):
        result, calls = self._start()
        batch_dir = self.root / "work" / "production_v1"
        self.assertEqual(result["batch_dir"], str(batch_dir))
        self.assertEqual(len(calls), 1, "run-experiment must call run_batch exactly once")
        kwargs = calls[0]
        self.assertEqual(kwargs["cases_path"], self.root / "cases.jsonl")
        self.assertEqual(kwargs["work_root"], batch_dir)
        self.assertEqual((kwargs["workers"], kwargs["retry_failed"],
                          kwargs["max_retries"], kwargs["force"]), (1, False, 0, False))
        # The snapshots batch_config.json will point at must exist inside the batch dir.
        for name in ("simulation.json", "case_defaults.json", "runtime.json",
                     "production_used.json"):
            self.assertTrue((batch_dir / name).is_file(), name)
        self.assertEqual(read_json(batch_dir / "production_used.json"), self.document)
        self.assertEqual(read_json(batch_dir / "simulation.json")["solver"]["type"],
                         "standard_dynamic_implicit")

    def test_snapshots_are_preserved_when_resuming_the_same_config(self):
        self._start()
        self._start()
        batch_dir = self.root / "work" / "production_v1"
        self.assertEqual(read_json(batch_dir / "production_used.json"), self.document,
                         "resuming with the same config keeps the provenance snapshot")

    def test_reuse_with_a_changed_config_is_rejected(self):
        self._start()
        self.document["contact"]["friction"] = 0.1
        self.config.write_text(json.dumps(self.document), encoding="utf-8")
        with self.assertRaises(PipelineError) as caught:
            self._start()
        self.assertEqual(caught.exception.code, "EXPERIMENT_ID_REUSE")


if __name__ == "__main__":
    unittest.main()
