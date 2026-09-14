"""Synthetic fixtures test logic only; none is a Fig.1 FE validation result."""
import json
import csv
from pathlib import Path
import tempfile
import unittest

import numpy as np

from pipeline.common import PipelineError, atomic_json, tree_hash
from pipeline.curve_qa import assess, TARGETS
from pipeline.diagnostics import classify_messages, completion_evidence, stagnation
from pipeline.mesh_contract import load_bundle
from pipeline.mesher_adapter import prepare
from pipeline.pbc import relations, render_include
from pipeline.prepare_fe import prepare as prepare_fe
from pipeline.state import StateStore

ROOT = Path(__file__).resolve().parents[1]


class PBCTests(unittest.TestCase):
    def test_corner_class_and_all_original_relations(self):
        xp, yp = [(0, 1), (2, 3)], [(0, 2), (1, 3)]
        mapping = relations(xp, yp)
        self.assertEqual(mapping["independent_relations"], 3)
        self.assertEqual(mapping["removed_relations"], 1)
        self.assertEqual(mapping["equation_count"], 18)
        shift = {0: np.array([0, 0])}
        for row in mapping["relations"]:
            self.assertEqual(row["root"], 0)
            shift[row["node"]] = np.array(row["shift"])
        u = {node: np.array([.123, -.045]) + np.array([.41, -.17]) * s for node, s in shift.items()}
        for a, b in xp:
            np.testing.assert_allclose(u[b] - u[a], [.41, 0], atol=1e-15)
        for a, b in yp:
            np.testing.assert_allclose(u[b] - u[a], [0, -.17], atol=1e-15)
        dependent = {r["node"] for r in mapping["relations"]}
        self.assertFalse(dependent & {r["root"] for r in mapping["relations"]})
        self.assertEqual(render_include(mapping, 100, 101).count("*Equation"), 18)

    def test_inconsistent_periodic_loop_fails(self):
        with self.assertRaises(PipelineError):
            relations([(0, 1), (1, 2), (0, 2)], [])

    def test_reverse_sign_when_root_is_high_side(self):
        mapping = relations([(3, 0)], [])
        self.assertEqual(mapping["relations"][0]["shift"], [-1, 0])


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / "config/quality.example.json").read_text())
        e = np.linspace(0, .3, 101)
        self.data = {"time_s": np.linspace(0, 1, 101), "u3_mm": -10 * e,
                     "rf3_N": -200 * e, "ALLIE": e * 10,
                     "ALLKE": e * 1e-3, "ALLAE": e * 1e-3}

    def check(self):
        return assess(self.data, 10, 100, -1, self.policy)

    def test_manufactured_linear_curve(self):
        result = self.check()
        self.assertEqual(result["status"], "CURVE_QA_PASS")
        self.assertFalse(result["dataset_eligible"])
        np.testing.assert_allclose(result["stress_11_MPa"], 2 * np.array(TARGETS))

    def test_incomplete_curve_cannot_extrapolate(self):
        self.data = {k: v[:80] for k, v in self.data.items()}
        result = self.check()
        self.assertIn("TARGET_RANGE_NOT_REACHED", result["failures"])
        self.assertIsNone(result["stress_11_MPa"])

    def test_inertia_spike_is_not_averaged_away(self):
        self.data["ALLKE"][40] = 100
        self.assertIn("QUASISTATIC_FAIL", self.check()["failures"])

    def test_sign_error_not_hidden_by_absolute_value(self):
        self.data["rf3_N"] *= -1
        self.assertIn("REACTION_SIGN_ERROR", self.check()["failures"])

    def test_strain_reversal_not_silently_sorted(self):
        self.data["u3_mm"][50] = self.data["u3_mm"][10]
        self.assertIn("STRAIN_REVERSAL", self.check()["failures"])

    def test_startup_energy_checked(self):
        self.data["ALLKE"][0] = 1e-4
        self.assertIn("STARTUP_INERTIA", self.check()["failures"])


class RuntimeTests(unittest.TestCase):
    def test_contact_error_residual_is_not_fatal(self):
        result = classify_messages("MAX. CONTACT FORCE ERROR = 1.0e-15\nTHE CONTACT CONSTRAINTS HAVE CONVERGED")
        self.assertFalse(result["fatal"])
        self.assertFalse(completion_evidence(0, "", "case1", True, result))
        self.assertFalse(completion_evidence(0, "Abaqus JOB old_case COMPLETED", "case1", True, result))
        self.assertTrue(completion_evidence(0, "Abaqus JOB case1 COMPLETED", "case1", True, result))
        fatal = classify_messages("***ERROR: invalid keyword")
        self.assertFalse(completion_evidence(0, "Abaqus JOB case1 COMPLETED", "case1", True, fatal))

    def test_stagnation_successful_but_tiny_increments(self):
        samples = [{"step_id": 1, "step_time_s": .6083 + i * 2.682e-7, "wall_s": i * 4} for i in range(100)]
        self.assertTrue(stagnation(samples, 1))
        for sample in samples:
            sample["step_time_s"] = sample["wall_s"] / 400
        self.assertFalse(stagnation(samples, 1))

    def test_store_ownership_and_duplicate_claim(self):
        with tempfile.TemporaryDirectory() as td:
            store = StateStore(Path(td) / "state.db")
            try:
                store.register("hash", "fig1", {"physical": 1})
                a = store.claim("hash", "BUILD", "worker1")
                with self.assertRaises(PipelineError):
                    store.claim("hash", "BUILD", "worker2")
                with self.assertRaises(PipelineError):
                    store.finish("hash", "BUILD", a, "worker2", "PASS", {})
                store.finish("hash", "BUILD", a, "worker1", "BLOCKED", {"reason": "not implemented"})
                self.assertEqual(store.status()[0]["status"], "BLOCKED")
                with self.assertRaises(PipelineError):
                    store.register("hash", "fig1", {"physical": 2})
            finally:
                store.close()

    def test_mesher_config_isolation(self):
        vendor = ROOT / "vendor/periodic_surface_mesher_v1.0"
        before = tree_hash(vendor)
        with tempfile.TemporaryDirectory() as td:
            one = prepare(vendor, ROOT / "config/cases/fig1.json", ROOT / "config/environment.example.json", Path(td) / "a")
            case = json.loads((ROOT / "config/cases/fig1.json").read_text())
            case["case_id"] = "case2"
            case["surface_expression"] = "cos(X)+cos(Y)+cos(Z)"
            atomic_json(Path(td) / "case2.json", case)
            two = prepare(vendor, Path(td) / "case2.json", ROOT / "config/environment.example.json", Path(td) / "b")
            self.assertNotEqual(one["engine"], two["engine"])
            self.assertNotEqual(one["mesh_request_key"], two["mesh_request_key"])
            self.assertEqual(tree_hash(vendor), before)
            with self.assertRaises(PipelineError):
                prepare(vendor, ROOT / "config/cases/fig1.json", ROOT / "config/environment.example.json", Path(td) / "a")

    def test_mesh_contract_uses_zero_based_indices(self):
        # A cube surface is ONLY a schema fixture; it is not a physical periodic shell benchmark.
        nodes = np.array([[x, y, z] for z in (0., 1.) for y in (0., 1.) for x in (0., 1.)])
        triangles = np.array([[0,1,3],[0,3,2],[4,7,5],[4,6,7],
                              [0,4,5],[0,5,1],[2,3,7],[2,7,6],
                              [0,2,6],[0,6,4],[1,5,7],[1,7,3]])
        pairs = {"x_pairs": np.array([[0,1],[2,3],[4,5],[6,7]]),
                 "y_pairs": np.array([[0,2],[1,3],[4,6],[5,7]]),
                 "z_pairs": np.array([[0,4],[1,5],[2,6],[3,7]])}
        with tempfile.TemporaryDirectory() as td:
            mesh, report = Path(td) / "mesh.npz", Path(td) / "report.json"
            np.savez(mesh, nodes=nodes, triangles=triangles, **pairs)
            atomic_json(report, {"pass": True, "test_fixture_only": True, "nodes": 8,
                                 "triangles": 12, "cell_size_mm": 1., "surface_area_mm2": 6.})
            self.assertEqual(load_bundle(mesh, report)["area_mm2"], 6.)
            csv_path = Path(td) / "pairs.csv"
            with csv_path.open("w", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["axis", "low_node", "high_node", "dx", "dy", "dz"])
                for axis, key in zip("XYZ", ("x_pairs", "y_pairs", "z_pairs")):
                    for low, high in pairs[key]:
                        writer.writerow([axis, low + 1, high + 1, *(nodes[high] - nodes[low])])
            manifest = prepare_fe(mesh, report, csv_path, ROOT / "config/physics.example.json",
                                  ROOT / "config/materials/demo_surrogate.json", Path(td) / "fe")
            self.assertAlmostEqual(manifest["thickness_mm"], .1 / 6.)
            self.assertEqual(manifest["equation_count"], 36)
            self.assertFalse(manifest["dataset_eligible"])
            self.assertFalse((Path(td) / "fe/physical.inp").exists())
            np.savez(mesh, nodes=nodes, triangles=triangles + 1, **pairs)
            with self.assertRaises(PipelineError):
                load_bundle(mesh, report)


if __name__ == "__main__":
    unittest.main()
