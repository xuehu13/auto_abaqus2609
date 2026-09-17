"""Mesh side: case config, vendor payload, mesh contract and PBC equations."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.common import PipelineError                          # noqa: E402
from pipeline.mesh import (load_bundle, load_case, pbc_relations,   # noqa: E402
                           prepare_ingredients, render_pbc_include, vendor_case)
from sandbox import CASE, SIMULATION, synthetic_bundle, write_bundle  # noqa: E402

CASE_DOC = json.loads(CASE.read_text(encoding="utf-8"))


def _mutated(**changes):
    """A copy of the Fig.1 case config with a nested change applied."""
    document = json.loads(json.dumps(CASE_DOC))
    for key, value in changes.items():
        if key.startswith("mesh_"):
            document["mesh"][key[len("mesh_"):]] = value
        elif key.startswith("cgal_"):
            document["mesh"]["cgal"][key[len("cgal_"):]] = value
        else:
            document[key] = value
    return document


class CaseConfigTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def _write(self, document):
        path = Path(self.folder.name) / "case.json"
        path.write_text(json.dumps(document), encoding="utf-8")
        return path

    def test_fig1_case_loads(self):
        case = load_case(CASE)
        self.assertEqual(case["case_id"], "fig1")
        self.assertEqual(case["mesh"]["cgal"]["random_seed"], 20260911)
        self.assertEqual(case["mesh"]["meshcheck"]["material_E"], 1.0)

    def test_unknown_and_missing_keys_fail(self):
        for document, fragment in (({**CASE_DOC, "typo": 1}, "unknown keys"),
                                   ({k: v for k, v in CASE_DOC.items() if k != "mesh"},
                                    "missing keys")):
            with self.subTest(fragment=fragment):
                with self.assertRaises(PipelineError) as caught:
                    load_case(self._write(document))
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")
                self.assertIn(fragment, str(caught.exception))

    def test_nested_unknown_key_fails(self):
        with self.assertRaises(PipelineError) as caught:
            load_case(self._write(_mutated(cgal_edge_size_mm=0.2, cgal_extra=1)))
        self.assertIn("case.mesh.cgal", str(caught.exception))

    def test_invalid_numbers_fail(self):
        for document in (_mutated(unit_cell_size_mm=0.0),
                         _mutated(unit_cell_size_mm=float("nan")),
                         _mutated(mesh_topology_sampling_intervals=0),
                         _mutated(cgal_random_seed=20260911.5),
                         _mutated(mesh_boundary_target_spacing_mm=-1.0)):
            with self.subTest(document=list(document)):
                with self.assertRaises(PipelineError) as caught:
                    load_case(self._write(document))
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_vendor_payload_uses_the_frozen_vendor_keys(self):
        payload = vendor_case(load_case(CASE))
        self.assertEqual(sorted(payload), sorted(
            ["case_id", "cell_size_mm", "iso_level", "surface_expression",
             "topology_sampling_intervals", "boundary_target_spacing_mm", "cgal",
             "tolerances", "abaqus"]))
        self.assertEqual(payload["cell_size_mm"], CASE_DOC["unit_cell_size_mm"])
        self.assertEqual(payload["abaqus"], {"meshcheck_material_E": 1.0,
                                            "meshcheck_material_nu": 0.30,
                                            "meshcheck_thickness_mm": 1.0})
        # The fake element-type field is gone: the frozen stage 06 hardcodes S3R.
        self.assertNotIn("element_type", payload["abaqus"])


class MeshContractTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.paths = synthetic_bundle(Path(self.folder.name) / "bundle")

    def test_valid_bundle_loads(self):
        bundle = load_bundle(*self.paths)
        self.assertEqual(bundle["L_mm"], 1.0)
        self.assertAlmostEqual(bundle["area_mm2"], 2.0)
        self.assertEqual(len(bundle["nodes"]), 8)
        self.assertEqual(bundle["report"]["case_id"], "mini")

    def test_broken_variants_are_rejected(self):
        cases = {
            "report_not_passed": ({"report_overrides": {"pass": False}}, "MESH_QA_FAILED"),
            "wrong_node_count": ({"report_overrides": {"nodes": 9}}, "MESH_REPORT_MISMATCH"),
            "wrong_area": ({"report_overrides": {"surface_area_mm2": 2.5}},
                           "MESH_REPORT_MISMATCH"),
            "bad_cell_size": ({"report_overrides": {"cell_size_mm": 0.0}}, "CONFIG_INVALID"),
            "float_connectivity": ({"triangles": np.array([[0.0, 1.0, 2.0]])},
                                   "MESH_CONTRACT_INVALID"),
            "out_of_range_connectivity": ({"triangles": np.array([[0, 1, 9]])},
                                          "MESH_CONTRACT_INVALID"),
            "degenerate_triangle": ({"triangles": np.array([[0, 1, 1], [0, 2, 3]])},
                                    "MESH_CONTRACT_INVALID"),
            "pair_closed_periodicity": ({"x_pairs": np.array([[0, 2], [3, 1], [4, 5], [7, 6]])},
                                        "PBC_GEOMETRY_MISMATCH"),
            "pair_missing_boundary_node": ({"x_pairs": np.array([[0, 1], [3, 2], [4, 5]])},
                                           "PBC_COVERAGE_MISMATCH"),
            "csv_without_rows": ({"csv_rows": []}, "CSV_NPZ_MISMATCH"),
            "csv_wrong_vector": ({"csv_rows": [["X", 1, 2, 99.0, 0.0, 0.0]]},
                                 "CSV_NPZ_MISMATCH"),
        }
        for name, (changes, code) in cases.items():
            with self.subTest(case=name):
                folder = Path(self.folder.name) / name
                folder.mkdir()
                paths = write_bundle(folder / "m.npz", folder / "m.json", folder / "m.csv",
                                     **changes)
                with self.assertRaises(PipelineError) as caught:
                    load_bundle(*paths)
                self.assertEqual(caught.exception.code, code)


class PbcTests(unittest.TestCase):
    def test_class_reduction_and_equation_count(self):
        x_pairs = np.array([[0, 1], [3, 2]])
        y_pairs = np.array([[0, 3], [1, 2]])
        mapping = pbc_relations(x_pairs, y_pairs, rotations=True)
        self.assertEqual(mapping["classes"], 1)
        self.assertEqual(mapping["independent_relations"], 3)
        self.assertEqual(mapping["equation_count"], 18)
        dependent = [row["node"] for row in mapping["relations"]]
        self.assertEqual(len(set(dependent)), len(dependent), "a dependent node is reused")
        self.assertNotIn(mapping["relations"][0]["root"], dependent)
        self.assertEqual(pbc_relations(x_pairs, y_pairs, rotations=False)["equation_count"], 9)

    def test_shift_coefficients_follow_the_cell_jump(self):
        mapping = pbc_relations(np.array([[0, 1], [1, 2]]), np.empty((0, 2), dtype=int))
        shifts = sorted(tuple(row["shift"]) for row in mapping["relations"])
        self.assertEqual(shifts, [(1, 0), (2, 0)])

    def test_cycle_inconsistency_is_rejected(self):
        with self.assertRaises(PipelineError) as caught:
            pbc_relations(np.array([[0, 1]]), np.array([[0, 1]]))
        self.assertEqual(caught.exception.code, "PBC_CYCLE_INCONSISTENT")

    def test_include_renders_one_equation_per_dof_with_macro_terms(self):
        mapping = pbc_relations(np.array([[0, 1]]), np.empty((0, 2), dtype=int), rotations=False)
        text = render_pbc_include(mapping, rp_x=3, rp_y=4)
        rows = [line for line in text.splitlines() if not line.startswith("**")]
        self.assertEqual(len([row for row in rows if row.startswith("*Equation")]), 3)
        # DOF 1 of node 2 = DOF 1 of node 1 minus one x cell jump of RP_X (node 3).
        self.assertIn("2, 1, 1, 1, 1, -1, 3, 1, -1", rows)
        self.assertIn("2, 2, 1, 1, 2, -1", rows)

    def test_label_collision_is_rejected(self):
        mapping = pbc_relations(np.array([[0, 1]]), np.empty((0, 2), dtype=int))
        with self.assertRaises(PipelineError) as caught:
            render_pbc_include(mapping, rp_x=1, rp_y=4)
        self.assertEqual(caught.exception.code, "PBC_LABEL_COLLISION")


class IngredientTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.paths = synthetic_bundle(Path(self.folder.name) / "bundle")
        self.counter = 0

    def _prepare(self, mutate=None):
        self.counter += 1
        document = json.loads(SIMULATION.read_text(encoding="utf-8"))
        if mutate:
            mutate(document)
        return prepare_ingredients(*self.paths, document,
                                   Path(self.folder.name) / ("out_%d" % self.counter))

    def test_ingredients_are_written_with_derived_values(self):
        facts = self._prepare()
        out = Path(self.folder.name) / "out_1"
        self.assertEqual(sorted(path.name for path in out.iterdir()),
                         ["lateral_pbc.inc", "pbc_map.json", "shell_mesh.inc"])
        self.assertEqual(facts["shell_nodes"], 8)
        self.assertEqual(facts["shell_elements"], 4)
        self.assertEqual(facts["labels"]["rp_x"], 9)
        self.assertAlmostEqual(facts["surface_area_mm2"], 2.0)
        # thickness = rho * L^3 / area and target = -strain * L for this tiny cell.
        self.assertAlmostEqual(facts["thickness_mm"], 0.1 / 2.0)
        self.assertAlmostEqual(facts["target_displacement_mm"], -0.2)
        self.assertIn("*Element, type=S3R, elset=SHELL_ALL",
                      (out / "shell_mesh.inc").read_text(encoding="utf-8"))

    def test_rotational_pbc_switch_changes_the_equations(self):
        facts_off = self._prepare(lambda doc: doc["pbc"].update(include_rotational_dofs=False))
        facts_on = self._prepare(lambda doc: doc["pbc"].update(include_rotational_dofs=True))
        self.assertEqual(facts_off["equation_count"] * 2, facts_on["equation_count"])
        self.assertFalse(json.loads(
            (Path(self.folder.name) / "out_1/pbc_map.json").read_text())["rotations"])
        self.assertTrue(json.loads(
            (Path(self.folder.name) / "out_2/pbc_map.json").read_text())["rotations"])

    def test_impossible_physics_is_rejected(self):
        cases = {
            "poisson": lambda doc: doc["material"].update(poisson_ratio=0.6),
            "relative_density": lambda doc: doc["shell"].update(target_relative_density=1.0),
            "strain": lambda doc: doc["loading"].update(target_compression_strain=0.0),
            "plastic_monotonic": lambda doc: doc["material"].update(
                plastic_table=[[1.0, 0.0], [2.0, 0.0]]),
            "plastic_start": lambda doc: doc["material"].update(
                plastic_table=[[1.0, 0.1], [2.0, 0.2]]),
        }
        for name, mutate in cases.items():
            with self.subTest(case=name):
                with self.assertRaises(PipelineError) as caught:
                    self._prepare(mutate)
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")


if __name__ == "__main__":
    unittest.main()
