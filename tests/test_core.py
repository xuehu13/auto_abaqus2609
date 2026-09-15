"""Synthetic fixtures test logic only; none is a Fig.1 FE validation result."""
import json
import csv
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import numpy as np

from pipeline import physical_datacheck as pdc
from pipeline import physical_solve as pds
from pipeline.common import PipelineError, atomic_json, file_hash, tree_hash
from pipeline.curve_qa import assess, TARGETS
from pipeline.diagnostics import classify_messages, completion_evidence, stagnation
from pipeline.mesh_contract import load_bundle
from pipeline.mesher_adapter import prepare
from pipeline.pbc import relations, render_include
from pipeline.physical_builder import (_load_numerics, _parse_includes,
                                       _platen_plan, _render_boundary_conditions,
                                       _render_contact, _render_material_section,
                                       _render_outputs, _render_step_and_loading,
                                       _render_step_end, _run_static_stage,
                                       _validate_static_model, build as build_physical)
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


class _BuilderFixtureMixin:
    """Shared synthetic bundle + config fixture; the cube is schema-only."""

    def _shared_fake_launcher(self):
        """A dummy .bat launcher so tests never touch the real Abaqus install."""
        launcher = Path(self.td.name) / "fake_abaqus.bat"
        if not launcher.exists():
            launcher.write_text("@echo off\r\n", encoding="ascii")
        return str(launcher)

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.addCleanup(self.td.cleanup)
        self.npz, self.report, self.pairs_csv = self._write_bundle("bundle", 1.0)
        # Builder fixture physics: the platen width must be an exact integer
        # multiple of mesh_size for the L=1 cube (2.0 / 0.5 -> 4 intervals). The
        # example file itself (1.8/1.0) is used by the L=10 scale fixture and by
        # the non-divisible-mesh case.
        physics = json.loads((ROOT / "config/physics.example.json").read_text())
        physics["platens"]["width_factor"] = 2.0
        physics["platens"]["mesh_size_mm"] = 0.5
        self.physics = Path(self.td.name) / "physics_fixture.json"
        atomic_json(self.physics, physics)
        self.material = ROOT / "config/materials/demo_surrogate.json"
        self.numerics = ROOT / "config/numerics.example.json"
        self.outputs = ROOT / "config/outputs.example.json"

    def _write_bundle(self, name, scale):
        """Cube mesh scaled by `scale`; schema fixture only, never a Fig.1 result."""
        td = Path(self.td.name) / name
        td.mkdir()
        nodes = np.array([[x * scale, y * scale, z * scale]
                          for z in (0., 1.) for y in (0., 1.) for x in (0., 1.)])
        triangles = np.array([[0,1,3],[0,3,2],[4,7,5],[4,6,7],
                              [0,4,5],[0,5,1],[2,3,7],[2,7,6],
                              [0,2,6],[0,6,4],[1,5,7],[1,7,3]])
        pairs = {"x_pairs": np.array([[0,1],[2,3],[4,5],[6,7]]),
                 "y_pairs": np.array([[0,2],[1,3],[4,6],[5,7]]),
                 "z_pairs": np.array([[0,4],[1,5],[2,6],[3,7]])}
        npz = td / "mesh.npz"
        np.savez(npz, nodes=nodes, triangles=triangles, **pairs)
        report = td / "report.json"
        atomic_json(report, {"pass": True, "test_fixture_only": True, "nodes": 8,
                             "triangles": 12, "cell_size_mm": scale,
                             "surface_area_mm2": 6.0 * scale ** 2})
        csv_path = td / "pairs.csv"
        with csv_path.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["axis", "low_node", "high_node", "dx", "dy", "dz"])
            for axis, key in zip("XYZ", ("x_pairs", "y_pairs", "z_pairs")):
                for low, high in pairs[key]:
                    writer.writerow([axis, low + 1, high + 1, *(nodes[high] - nodes[low])])
        return npz, report, csv_path

    def build(self, name="build", numerics=None):
        return build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                              self.material, numerics or self.numerics, self.outputs,
                              Path(self.td.name) / name)

class PhysicalBuilderTests(_BuilderFixtureMixin, unittest.TestCase):
    def test_output_exists_rejected(self):
        self.build()
        with self.assertRaises(PipelineError) as caught:
            self.build()
        self.assertEqual(caught.exception.code, "OUTPUT_EXISTS")

    def test_missing_input_fails_before_attempt_creation(self):
        out = Path(self.td.name) / "never_created"
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                           self.material, Path(self.td.name) / "absent_numerics.json",
                           self.outputs, out)
        self.assertEqual(caught.exception.code, "INPUT_MISSING")
        self.assertFalse(out.exists())

    def test_unsupported_valid_numerics_is_not_config_invalid(self):
        bad = json.loads(self.numerics.read_text())
        bad["procedure"] = "static"
        bad_path = Path(self.td.name) / "unsupported.json"
        atomic_json(bad_path, bad)
        with self.assertRaises(PipelineError) as caught:
            self.build(name="unsupported", numerics=bad_path)
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")
        self.assertFalse((Path(self.td.name) / "unsupported").exists())

    def test_invalid_numerics_fails_before_attempt_creation(self):
        bad = json.loads(self.numerics.read_text())
        bad["maximum_increment_s"] = 1e-9
        bad_path = Path(self.td.name) / "invalid.json"
        atomic_json(bad_path, bad)
        out = Path(self.td.name) / "invalid_attempt"
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                           self.material, bad_path, self.outputs, out)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        self.assertFalse(out.exists())

    def test_numerics_reaches_manifest(self):
        manifest = self.build()
        self.assertEqual(manifest["numerics"], json.loads(self.numerics.read_text()))
        self.assertEqual(manifest["numerics_sha256"], file_hash(self.numerics))

    def test_ingredients_are_not_recomputed(self):
        manifest = self.build()
        model_inputs = json.loads((Path(self.td.name) / "build/ingredients/model_inputs.json").read_text())
        self.assertEqual(manifest["identity"]["model_key"], model_inputs["model_key"])
        self.assertEqual(manifest["mesh_source_hashes"], model_inputs["mesh_files"])
        for key in ("L_mm", "A0_mm2", "surface_area_mm2", "thickness_mm", "target_displacement_mm",
                    "shell_nodes", "shell_elements", "equation_count", "labels"):
            self.assertEqual(manifest[key], model_inputs[key])

    def test_static_build_completes_without_abaqus_claims(self):
        out = Path(self.td.name) / "build"
        manifest = self.build()
        self.assertEqual(manifest["status"], "PHYSICAL_INP_STATIC_VALIDATED")
        self.assertIs(manifest["dataset_eligible"], False)
        self.assertIs(manifest["blocks"]["material_section"]["allow_production_dataset"], False)
        missing = " ".join(manifest["missing_stages"])
        for stage in ("physical datacheck", "solve", "ODB QA"):
            self.assertIn(stage, missing)
        for stage in ("physical.inp assembly", "static model validation"):
            self.assertNotIn(stage, missing)
        self.assertTrue((out / "physical.inp").is_file())
        self.assertTrue((out / "build_report.json").is_file())
        report = json.loads((out / "build_report.json").read_text())
        self.assertEqual(report["abaqus_datacheck"], "NOT_RUN")
        self.assertIs(report["dataset_eligible"], False)
        self.assertTrue((out / "blocks/boundary_conditions.inc").is_file())

    def test_material_block_matches_config(self):
        self.build()
        block = (Path(self.td.name) / "build/blocks/material_section.inc").read_text()
        material = json.loads(self.material.read_text())
        self.assertIn("*Material, name=MAT_SHELL", block)
        self.assertIn(" " + repr(float(material["density_tonne_mm3"])) + ",", block)
        self.assertIn(repr(float(material["E_MPa"])) + ", " + repr(float(material["nu"])), block)
        plastic = block.split("*Plastic\n", 1)[1].split("*Shell Section", 1)[0].strip().splitlines()
        self.assertEqual([tuple(map(float, row.split(", "))) for row in plastic],
                         [tuple(map(float, row)) for row in material["plastic_table_MPa_strain"]])
        self.assertNotIn("allow_production_dataset", block)

    def test_section_thickness_not_recomputed(self):
        self.build()
        model_inputs = json.loads((Path(self.td.name) / "build/ingredients/model_inputs.json").read_text())
        block = (Path(self.td.name) / "build/blocks/material_section.inc").read_text()
        section = block.split("material=MAT_SHELL\n", 1)[1].splitlines()[0]
        self.assertTrue(section.startswith(repr(model_inputs["thickness_mm"]) + ", 5"))

    def test_block_deterministic_across_attempts(self):
        one = self.build("one")
        two = self.build("two")
        self.assertEqual(one["blocks"]["material_section"]["sha256"],
                         two["blocks"]["material_section"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_parameter_change_changes_block(self):
        base = self.build("base")
        changed = json.loads(self.material.read_text())
        changed["E_MPa"] = changed["E_MPa"] + 100.0
        changed_path = Path(self.td.name) / "material_changed.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               changed_path, self.numerics, self.outputs,
                               Path(self.td.name) / "changed")
        self.assertNotEqual(base["blocks"]["material_section"]["sha256"],
                            other["blocks"]["material_section"]["sha256"])
        self.assertNotEqual(base["build_key"], other["build_key"])

    def test_unsupported_material_type_is_not_config_invalid(self):
        with self.assertRaises(PipelineError) as caught:
            _render_material_section({"type": "hyperelastic"}, {"thickness_mm": 1.0})
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")

    def test_invalid_material_structure_is_config_invalid(self):
        with self.assertRaises(PipelineError) as caught:
            _render_material_section({"type": "elastic_plastic_table", "density_tonne_mm3": "not-a-number"},
                                     {"thickness_mm": 1.0})
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def _labels(self):
        return {"rp_x": 9, "rp_y": 10, "rp_bottom": 11, "rp_top": 12,
                "first_plate_node": 13, "first_plate_element": 13}

    def _parse_inc(self, block):
        nodes, elements, section = {}, {}, None
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("**"):
                continue
            if stripped.startswith("*"):
                keyword = stripped.split(",")[0].strip().lower()
                section = {"*node": "nodes", "*element": "elements"}.get(keyword)
                continue
            parts = [p.strip() for p in stripped.split(",")]
            if section == "nodes" and len(parts) == 4:
                nodes[int(parts[0])] = tuple(map(float, parts[1:]))
            elif section == "elements" and len(parts) == 5:
                elements[int(parts[0])] = tuple(map(int, parts[1:]))
        return nodes, elements

    def test_platen_fig1_scale_geometry(self):
        npz, report, pairs_csv = self._write_bundle("l10", 10.0)
        manifest = build_physical(npz, report, pairs_csv, ROOT / "config/physics.example.json",
                                  self.material, self.numerics, self.outputs,
                                  Path(self.td.name) / "l10build")
        rp = manifest["blocks"]["rigid_platens"]
        labels = manifest["labels"]
        self.assertEqual(rp["width_mm"], 18.0)
        self.assertEqual(rp["intervals_per_side"], 18)
        self.assertEqual(rp["nodes_per_platen"], 361)
        self.assertEqual(rp["elements_per_platen"], 324)
        self.assertEqual(rp["bottom_z_mm"], 0.0)
        self.assertEqual(rp["top_z_mm"], 10.0)
        self.assertEqual(rp["xy_extent_mm"], {"x_min_mm": -4.0, "x_max_mm": 14.0,
                                              "y_min_mm": -4.0, "y_max_mm": 14.0})
        self.assertEqual(rp["rp_labels"],
                         {key: labels[key] for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")})
        self.assertEqual(rp["node_ranges"]["bottom"],
                         [labels["first_plate_node"], labels["first_plate_node"] + 360])
        self.assertEqual(rp["node_ranges"]["top"],
                         [labels["first_plate_node"] + 361, labels["first_plate_node"] + 721])
        self.assertEqual(rp["element_ranges"]["bottom"],
                         [labels["first_plate_element"], labels["first_plate_element"] + 323])
        self.assertEqual(rp["element_ranges"]["top"],
                         [labels["first_plate_element"] + 324, labels["first_plate_element"] + 647])
        self.assertEqual(rp["normal_policy"], "baseline_shared_connectivity_plus_z_both")

    def test_platen_rp_coordinates_and_roles(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/rigid_platens.inc").read_text()
        labels, L = manifest["labels"], manifest["L_mm"]
        nodes, _ = self._parse_inc(block)
        self.assertEqual(nodes[labels["rp_bottom"]], (L / 2, L / 2, 0.0))
        self.assertEqual(nodes[labels["rp_top"]], (L / 2, L / 2, L))
        self.assertEqual(nodes[labels["rp_x"]], (1.5 * L, L / 2, L / 2))
        self.assertEqual(nodes[labels["rp_y"]], (L / 2, 1.5 * L, L / 2))
        rigid_lines = [line for line in block.splitlines() if line.startswith("*Rigid Body")]
        self.assertEqual(len(rigid_lines), 2)
        joined = "\n".join(rigid_lines)
        self.assertIn("ref node=%d, elset=PLATE_BOTTOM" % labels["rp_bottom"], joined)
        self.assertIn("ref node=%d, elset=PLATE_TOP" % labels["rp_top"], joined)
        self.assertNotIn(str(labels["rp_x"]), joined)
        self.assertNotIn(str(labels["rp_y"]), joined)
        for nset in ("RP_X_CTRL", "RP_Y_CTRL", "RP_BOTTOM", "RP_TOP"):
            self.assertIn("*Nset, nset=" + nset, block)

    def test_platen_label_ranges_no_collision(self):
        manifest = self.build()
        rp = manifest["blocks"]["rigid_platens"]
        labels = manifest["labels"]
        bn, tn = rp["node_ranges"]["bottom"], rp["node_ranges"]["top"]
        be, te = rp["element_ranges"]["bottom"], rp["element_ranges"]["top"]
        self.assertEqual(bn[0], labels["first_plate_node"])
        self.assertEqual(be[0], labels["first_plate_element"])
        self.assertGreater(bn[0], manifest["shell_nodes"])
        self.assertGreater(bn[0], max(labels[key] for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")))
        self.assertGreater(tn[0], bn[1])
        self.assertGreater(be[0], manifest["shell_elements"])
        self.assertGreater(te[0], be[1])
        self.assertEqual(tn[1] - tn[0], bn[1] - bn[0])
        self.assertEqual(te[1] - te[0], be[1] - be[0])

    def test_platen_normals_and_shared_connectivity(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/rigid_platens.inc").read_text()
        nodes, elements = self._parse_inc(block)
        labels = manifest["labels"]
        per_platen = manifest["blocks"]["rigid_platens"]["elements_per_platen"]
        bottom_conn = elements[labels["first_plate_element"]]
        top_conn = elements[labels["first_plate_element"] + per_platen]

        def normal_z(connection):
            pts = [np.array(nodes[label]) for label in connection]
            return float(np.cross(pts[1] - pts[0], pts[2] - pts[0])[2])

        self.assertGreater(normal_z(bottom_conn), 0.0)
        self.assertGreater(normal_z(top_conn), 0.0)
        self.assertEqual(normal_z(top_conn), normal_z(bottom_conn))
        first_node = labels["first_plate_node"]
        offset = manifest["blocks"]["rigid_platens"]["nodes_per_platen"]
        self.assertEqual([label - first_node for label in bottom_conn],
                         [label - first_node - offset for label in top_conn])

    def test_rigid_block_deterministic(self):
        one = self.build("rigid_one")
        two = self.build("rigid_two")
        self.assertEqual(one["blocks"]["rigid_platens"]["sha256"],
                         two["blocks"]["rigid_platens"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_width_change_changes_rigid_block_only(self):
        base = self.build("wbase")
        changed = json.loads(self.physics.read_text())
        changed["platens"]["width_factor"] = 3.0
        changed_path = Path(self.td.name) / "physics_w3.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "wchanged")
        self.assertNotEqual(base["blocks"]["rigid_platens"]["sha256"],
                            other["blocks"]["rigid_platens"]["sha256"])
        self.assertEqual(base["blocks"]["material_section"]["sha256"],
                         other["blocks"]["material_section"]["sha256"])
        self.assertEqual(base["blocks"]["boundary_conditions"]["sha256"],
                         other["blocks"]["boundary_conditions"]["sha256"])
        self.assertEqual(base["blocks"]["contact"]["sha256"],
                         other["blocks"]["contact"]["sha256"])
        self.assertEqual(base["blocks"]["outputs"]["sha256"],
                         other["blocks"]["outputs"]["sha256"])
        self.assertNotEqual(base["build_key"], other["build_key"])

    def test_unsupported_platen_type(self):
        physics = json.loads(self.physics.read_text())
        physics["platens"]["type"] = "R3D8"
        manifest = {"L_mm": 1.0, "shell_nodes": 8, "shell_elements": 12, "labels": self._labels()}
        with self.assertRaises(PipelineError) as caught:
            _platen_plan(physics, manifest)
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")

    def test_invalid_platen_geometry(self):
        manifest = {"L_mm": 1.0, "shell_nodes": 8, "shell_elements": 12, "labels": self._labels()}
        for key, value in (("width_factor", 0.0), ("mesh_size_mm", -1.0)):
            physics = json.loads(self.physics.read_text())
            physics["platens"][key] = value
            with self.assertRaises(PipelineError) as caught:
                _platen_plan(physics, manifest)
            self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_non_divisible_mesh_not_rounded(self):
        physics = json.loads((ROOT / "config/physics.example.json").read_text())
        manifest = {"L_mm": 1.0, "shell_nodes": 8, "shell_elements": 12, "labels": self._labels()}
        with self.assertRaises(PipelineError) as caught:
            _platen_plan(physics, manifest)
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")
        self.assertIn("exact integer multiple", str(caught.exception))

    def test_boundary_block_content(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/boundary_conditions.inc").read_text()
        sections, current = [], None
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("**"):
                continue
            if stripped.startswith("*"):
                current = [] if stripped == "*Boundary" else None
                if current is not None:
                    sections.append(current)
                continue
            if current is not None:
                current.append([p.strip() for p in stripped.split(",")])
        self.assertEqual(len(sections), 2)
        bottom, top = sections
        self.assertEqual([row[0] for row in bottom], ["RP_BOTTOM"] * 6)
        self.assertEqual([(row[1], row[2]) for row in bottom],
                         [("1", "1"), ("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6")])
        self.assertEqual([row[0] for row in top], ["RP_TOP"] * 5)
        self.assertEqual(sorted((row[1], row[2]) for row in top),
                         [("1", "1"), ("2", "2"), ("4", "4"), ("5", "5"), ("6", "6")])
        self.assertTrue(all(len(row) == 3 for row in bottom + top))

    def test_boundary_macro_nodes_absent(self):
        self.build()
        block = (Path(self.td.name) / "build/blocks/boundary_conditions.inc").read_text()
        self.assertNotIn("RP_X_CTRL", block)
        self.assertNotIn("RP_Y_CTRL", block)

    def test_boundary_scope_guard(self):
        self.build()
        block = (Path(self.td.name) / "build/blocks/boundary_conditions.inc").read_text().lower()
        for token in ("amplitude", "amp_compression", "*step", "*dynamic", "*contact",
                      "*surface", "*output", "op=", "type="):
            self.assertNotIn(token, block)

    def test_boundary_deterministic(self):
        one = self.build("bc_one")
        two = self.build("bc_two")
        self.assertEqual(one["blocks"]["boundary_conditions"]["sha256"],
                         two["blocks"]["boundary_conditions"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_boundary_independent_of_loading(self):
        base = self.build("lbase")
        changed = json.loads(self.physics.read_text())
        changed["target_compression_strain"] = 0.2
        changed_path = Path(self.td.name) / "physics_strain20.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "lchanged")
        self.assertEqual(base["blocks"]["boundary_conditions"]["sha256"],
                         other["blocks"]["boundary_conditions"]["sha256"])
        self.assertEqual(base["blocks"]["contact"]["sha256"],
                         other["blocks"]["contact"]["sha256"])
        self.assertEqual(
            (Path(self.td.name) / "lbase/blocks/boundary_conditions.inc").read_bytes(),
            (Path(self.td.name) / "lchanged/blocks/boundary_conditions.inc").read_bytes())

    def test_unsupported_boundary_mode(self):
        with self.assertRaises(PipelineError) as caught:
            _render_boundary_conditions({"boundary_mode": "free_all"}, {"labels": self._labels()})
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")

    def test_boundary_broken_label_contract(self):
        broken = self._labels()
        del broken["rp_bottom"]
        with self.assertRaises(PipelineError) as caught:
            _render_boundary_conditions({"boundary_mode": "lateral_xy_platens"}, {"labels": broken})
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        duplicated = self._labels()
        duplicated["rp_top"] = duplicated["rp_bottom"]
        with self.assertRaises(PipelineError) as caught:
            _render_boundary_conditions({"boundary_mode": "lateral_xy_platens"}, {"labels": duplicated})
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_contact_block_content(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/contact.inc").read_text()
        self.assertIn("*Surface Interaction, name=ContactProp", block)
        self.assertIn("*Friction, slip tolerance=0.005", block)
        self.assertIn("0.6,", block)
        self.assertIn("*Surface Behavior, pressure-overclosure=HARD", block)
        self.assertIn("*Contact\n", block)
        self.assertIn("*Contact Inclusions, ALL EXTERIOR", block)
        self.assertIn("*Contact Property Assignment", block)
        self.assertIn(", , ContactProp", block)
        lines = block.splitlines()
        idx = lines.index("*Surface Interaction, name=ContactProp")
        followers = [l for l in lines[idx + 1:] if l.strip() and not l.startswith("**")]
        self.assertTrue(followers[0].startswith("*Friction"))

    def test_contact_scope_guard(self):
        self.build()
        block = (Path(self.td.name) / "build/blocks/contact.inc").read_text().lower()
        for token in ("*boundary", "*step", "*dynamic", "*amplitude", "*output", "*restart",
                      "*contact initialization", "*contact controls", "*surface,", "spos", "sneg"):
            self.assertNotIn(token, block)

    def test_contact_deterministic(self):
        one = self.build("c_one")
        two = self.build("c_two")
        self.assertEqual(one["blocks"]["contact"]["sha256"], two["blocks"]["contact"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_contact_slip_tolerance_sensitivity(self):
        base = self.build("sbase")
        changed = json.loads(self.physics.read_text())
        changed["contact"]["slip_tolerance"] = 0.01
        changed_path = Path(self.td.name) / "physics_slip01.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "schanged")
        self.assertNotEqual(base["blocks"]["contact"]["sha256"],
                            other["blocks"]["contact"]["sha256"])
        self.assertNotIn("slip tolerance=0.005",
                         (Path(self.td.name) / "schanged/blocks/contact.inc").read_text())
        self.assertEqual(base["blocks"]["material_section"]["sha256"],
                         other["blocks"]["material_section"]["sha256"])
        self.assertEqual(base["blocks"]["rigid_platens"]["sha256"],
                         other["blocks"]["rigid_platens"]["sha256"])
        self.assertEqual(base["blocks"]["boundary_conditions"]["sha256"],
                         other["blocks"]["boundary_conditions"]["sha256"])
        self.assertNotEqual(base["build_key"], other["build_key"])

    def test_contact_friction_sensitivity(self):
        base = self.build("fbase")
        changed = json.loads(self.physics.read_text())
        changed["contact"]["friction"] = 0.3
        changed_path = Path(self.td.name) / "physics_f03.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "fchanged")
        self.assertNotEqual(base["blocks"]["contact"]["sha256"],
                            other["blocks"]["contact"]["sha256"])
        self.assertEqual(base["blocks"]["material_section"]["sha256"],
                         other["blocks"]["material_section"]["sha256"])
        self.assertEqual(base["blocks"]["rigid_platens"]["sha256"],
                         other["blocks"]["rigid_platens"]["sha256"])
        self.assertEqual(base["blocks"]["boundary_conditions"]["sha256"],
                         other["blocks"]["boundary_conditions"]["sha256"])
        self.assertEqual(base["blocks"]["outputs"]["sha256"],
                         other["blocks"]["outputs"]["sha256"])

    def test_contact_supported_policy(self):
        manifest = {"labels": self._labels()}
        for key, value in (("normal", "rough"), ("allow_separation", False),
                           ("tangential", "lagrange"), ("shell_self_contact", False)):
            variant = json.loads(self.physics.read_text())
            variant["contact"][key] = value
            with self.assertRaises(PipelineError) as caught:
                _render_contact(variant, manifest)
            self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED", key)

    def test_contact_invalid_config(self):
        manifest = {"labels": self._labels()}
        good = json.loads(self.physics.read_text())
        mutations = (
            {"contact": {k: v for k, v in good["contact"].items() if k != "friction"}},
            {"contact": {**good["contact"], "friction": "x"}},
            {"contact": {**good["contact"], "friction": -0.1}},
            {"contact": {**good["contact"], "slip_tolerance": 0.0}},
            {"contact": {**good["contact"], "slip_tolerance": "x"}},
            {"contact": {**good["contact"], "allow_separation": "yes"}},
            {"contact": {**good["contact"], "shell_self_contact": 1}},
        )
        for mutation in mutations:
            with self.assertRaises(PipelineError) as caught:
                _render_contact(mutation, manifest)
            self.assertEqual(caught.exception.code, "CONFIG_INVALID", mutation)
        nan_physics = json.loads(self.physics.read_text())
        nan_physics["contact"]["friction"] = float("nan")
        with self.assertRaises(PipelineError) as caught:
            _render_contact(nan_physics, manifest)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def _parse_step_sections(self, block):
        sections, current = [], None
        for line in block.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("**"):
                continue
            if stripped.startswith("*"):
                current = {"keyword": stripped, "data": []}
                sections.append(current)
                continue
            if current is not None:
                current["data"].append([p.strip() for p in stripped.split(",")])
        return sections

    def test_step_loading_content(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/step_loading.inc").read_text()
        lines = block.splitlines()
        sections = self._parse_step_sections(block)
        self.assertEqual([s["keyword"] for s in sections],
                         ["*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP",
                          "*Step, name=Compression, nlgeom=YES, inc=10000",
                          "*Dynamic, application=MODERATE DISSIPATION, initial=NO",
                          "*Boundary, amplitude=AMP_COMPRESSION"])
        amplitude, step, dynamic, boundary = sections
        self.assertEqual(amplitude["data"], [["0.0", "0.0", "1.0", "1.0"]])
        step_idx = lines.index("*Step, name=Compression, nlgeom=YES, inc=10000")
        subheading = lines[step_idx + 1]
        self.assertEqual(len(step["data"]), 1)
        self.assertEqual(step["data"][0][0], "Compression: eps=0.3")
        self.assertFalse(subheading.startswith("**"))
        self.assertNotIn("quasi-static", subheading.lower())
        self.assertIn("eps=0.3", subheading)
        self.assertIn("U3=-0.3", subheading)
        self.assertIn("T=1", subheading)
        self.assertEqual(dynamic["data"], [["0.001", "1.0", "1e-08", "0.02"]])
        self.assertEqual(boundary["data"], [["RP_TOP", "3", "3", "-0.3"]])
        self.assertEqual(manifest["blocks"]["step_loading"]["target_displacement_mm"], -0.3)
        self.assertIs(manifest["blocks"]["step_loading"]["step_reapplies_guide_dofs"], False)

    def test_step_end_block(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/step_end.inc").read_text()
        self.assertEqual(block, "*End Step\n")
        self.assertEqual(manifest["blocks"]["step_end"]["keyword"], "*End Step")
        self.assertEqual(manifest["blocks"]["step_end"]["sha256"],
                         file_hash(Path(self.td.name) / "build/blocks/step_end.inc"))

    def test_step_scope_guard(self):
        self.build()
        loading = (Path(self.td.name) / "build/blocks/step_loading.inc").read_text().lower()
        for token in ("*restart", "*output", "*end step", "*contact", "*surface",
                      "*cload", "*dload", "*dsload"):
            self.assertNotIn(token, loading)
        end = (Path(self.td.name) / "build/blocks/step_end.inc").read_text().lower()
        self.assertEqual(end.strip(), "*end step")

    def test_step_deterministic(self):
        one = self.build("st_one")
        two = self.build("st_two")
        self.assertEqual(one["blocks"]["step_loading"]["sha256"],
                         two["blocks"]["step_loading"]["sha256"])
        self.assertEqual(one["blocks"]["step_end"]["sha256"], two["blocks"]["step_end"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_step_target_strain_sensitivity(self):
        base = self.build("tbase")
        changed = json.loads(self.physics.read_text())
        changed["target_compression_strain"] = 0.2
        changed_path = Path(self.td.name) / "physics_t02.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "tchanged")
        self.assertNotEqual(base["blocks"]["step_loading"]["sha256"],
                            other["blocks"]["step_loading"]["sha256"])
        self.assertEqual(other["blocks"]["step_loading"]["target_displacement_mm"], -0.2)
        self.assertIn("RP_TOP, 3, 3, -0.2",
                      (Path(self.td.name) / "tchanged/blocks/step_loading.inc").read_text())
        self.assertEqual(base["blocks"]["outputs"]["sha256"], other["blocks"]["outputs"]["sha256"])
        self.assertEqual(base["blocks"]["step_end"]["sha256"], other["blocks"]["step_end"]["sha256"])
        for key in ("material_section", "rigid_platens", "boundary_conditions", "contact"):
            self.assertEqual(base["blocks"][key]["sha256"], other["blocks"][key]["sha256"], key)

    def test_step_time_period_scales(self):
        base = self.build("t5base")
        changed = json.loads(self.physics.read_text())
        changed["time_period_s"] = 5.0
        changed_path = Path(self.td.name) / "physics_t5.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "t5build")
        block = (Path(self.td.name) / "t5build/blocks/step_loading.inc").read_text()
        self.assertIn("0.0, 0.0, 5.0, 1.0", block)
        dynamic = [s for s in self._parse_step_sections(block) if s["keyword"].startswith("*Dynamic")][0]
        self.assertEqual(dynamic["data"][0][1], "5.0")
        self.assertNotEqual(base["blocks"]["step_loading"]["sha256"],
                            other["blocks"]["step_loading"]["sha256"])
        for key in ("material_section", "rigid_platens", "boundary_conditions", "contact", "step_end"):
            self.assertEqual(base["blocks"][key]["sha256"], other["blocks"][key]["sha256"], key)

    def test_step_increment_sensitivity(self):
        for key, value in (("initial_increment_s", 0.002), ("minimum_increment_s", 1e-07),
                           ("maximum_increment_s", 0.01), ("maximum_increments", 5000)):
            base = self.build("inc_base_" + key)
            changed = json.loads(self.numerics.read_text())
            changed[key] = value
            changed_path = Path(self.td.name) / ("numerics_" + key + ".json")
            atomic_json(changed_path, changed)
            other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                                   self.material, changed_path, self.outputs,
                                   Path(self.td.name) / ("inc_" + key))
            self.assertNotEqual(base["blocks"]["step_loading"]["sha256"],
                                other["blocks"]["step_loading"]["sha256"], key)
            for other_key in ("material_section", "rigid_platens", "boundary_conditions", "contact"):
                self.assertEqual(base["blocks"][other_key]["sha256"],
                                 other["blocks"][other_key]["sha256"], key)
            if key == "maximum_increments":
                self.assertIn("inc=5000",
                              (Path(self.td.name) / "inc_maximum_increments/blocks/step_loading.inc").read_text())

    def test_step_independent_of_contact_and_platen_params(self):
        base = self.build("ib")
        changed = json.loads(self.physics.read_text())
        changed["contact"]["friction"] = 0.4
        changed["platens"]["width_factor"] = 3.0
        changed_path = Path(self.td.name) / "physics_ic.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                               self.material, self.numerics, self.outputs,
                               Path(self.td.name) / "ic")
        self.assertEqual(base["blocks"]["step_loading"]["sha256"],
                         other["blocks"]["step_loading"]["sha256"])
        self.assertNotEqual(base["blocks"]["contact"]["sha256"], other["blocks"]["contact"]["sha256"])
        self.assertNotEqual(base["blocks"]["rigid_platens"]["sha256"],
                            other["blocks"]["rigid_platens"]["sha256"])

    def test_step_automatic_stabilization_not_implemented(self):
        changed = json.loads(self.numerics.read_text())
        changed["automatic_stabilization"] = True
        changed_path = Path(self.td.name) / "numerics_stab.json"
        atomic_json(changed_path, changed)
        out = Path(self.td.name) / "stab_attempt"
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                           self.material, changed_path, self.outputs, out)
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")
        self.assertFalse(out.exists())

    def test_step_initial_acceleration_policy(self):
        base = json.loads(self.numerics.read_text())
        missing = {k: v for k, v in base.items() if k != "initial_acceleration_policy"}
        non_string = dict(base, initial_acceleration_policy=1)
        calculate = dict(base, initial_acceleration_policy="calculate")
        for index, (data, code) in enumerate(((missing, "CONFIG_INVALID"),
                                              (non_string, "CONFIG_INVALID"),
                                              (calculate, "NOT_IMPLEMENTED"))):
            path = Path(self.td.name) / ("num_%d.json" % index)
            atomic_json(path, data)
            with self.assertRaises(PipelineError) as caught:
                _load_numerics(path)
            self.assertEqual(caught.exception.code, code, index)
        bypass = Path(self.td.name) / "num_bypass.json"
        atomic_json(bypass, base)
        self.assertEqual(_load_numerics(bypass)["initial_acceleration_policy"], "bypass")

    def test_step_amplitude_policy(self):
        changed = json.loads(self.physics.read_text())
        changed["amplitude"] = "ramp"
        changed_path = Path(self.td.name) / "physics_ramp.json"
        atomic_json(changed_path, changed)
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, changed_path,
                           self.material, self.numerics, self.outputs,
                           Path(self.td.name) / "ramp_attempt")
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")

    def test_outputs_block_content(self):
        manifest = self.build()
        block = (Path(self.td.name) / "build/blocks/outputs.inc").read_text()
        sections = self._parse_step_sections(block)
        self.assertEqual([s["keyword"] for s in sections],
                         ["*Restart, write, frequency=0",
                          "*Output, field, variable=PRESELECT, frequency=50",
                          "*Output, history, frequency=1",
                          "*Energy Output",
                          "*Node Output, nset=RP_TOP",
                          "*Node Output, nset=RP_X_CTRL",
                          "*Node Output, nset=RP_Y_CTRL",
                          "*Output, history, variable=PRESELECT, frequency=10"])
        self.assertEqual(sections[3]["data"],
                         [["ALLAE", "ALLIE", "ALLKE", "ALLPD", "ALLWK", "ETOTAL"]])
        self.assertEqual(sections[4]["data"], [["RF3", "U3"]])
        self.assertEqual(sections[5]["data"], [["U1"]])
        self.assertEqual(sections[6]["data"], [["U2"]])
        self.assertEqual(manifest["blocks"]["outputs"]["required_regions"],
                         ["RP_TOP", "RP_X_CTRL", "RP_Y_CTRL"])
        self.assertEqual(manifest["outputs_config_sha256"], file_hash(self.outputs))

    def test_outputs_scope_guard(self):
        self.build()
        block = (Path(self.td.name) / "build/blocks/outputs.inc").read_text().lower()
        for token in ("*boundary", "*step", "*dynamic", "*amplitude", "*contact", "*surface",
                      "*cload", "*dload", "*dsload", "*end step"):
            self.assertNotIn(token, block)

    def test_outputs_deterministic(self):
        one = self.build("o_one")
        two = self.build("o_two")
        self.assertEqual(one["blocks"]["outputs"]["sha256"], two["blocks"]["outputs"]["sha256"])
        self.assertEqual(one["build_key"], two["build_key"])

    def test_outputs_schedule_sensitivity(self):
        for name, mutation in (("field", {"field_groups": [
                                   {"schedule": {"type": "every_n_increments", "n": 25},
                                    "mode": "preselect"}]}),
                               ("group1", {"history_groups": [
                                   {"schedule": {"type": "every_n_increments", "n": 2},
                                    "requests": json.loads(
                                        self.outputs.read_text())["history_groups"][0]["requests"]},
                                   {"schedule": {"type": "every_n_increments", "n": 10},
                                    "mode": "preselect"}]}),
                               ("group2", {"history_groups": [
                                   json.loads(self.outputs.read_text())["history_groups"][0],
                                   {"schedule": {"type": "every_n_increments", "n": 5},
                                    "mode": "preselect"}]})):
            base = self.build("sched_base_" + name)
            changed = json.loads(self.outputs.read_text())
            changed.update(mutation)
            changed_path = Path(self.td.name) / ("outputs_" + name + ".json")
            atomic_json(changed_path, changed)
            other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                                   self.material, self.numerics, changed_path,
                                   Path(self.td.name) / ("sched_" + name))
            self.assertNotEqual(base["blocks"]["outputs"]["sha256"],
                                other["blocks"]["outputs"]["sha256"], name)
            self.assertNotEqual(base["build_key"], other["build_key"], name)
            for key in ("material_section", "rigid_platens", "boundary_conditions",
                        "contact", "step_loading", "step_end"):
                self.assertEqual(base["blocks"][key]["sha256"],
                                 other["blocks"][key]["sha256"], name + ":" + key)

    def test_outputs_variable_change(self):
        base = self.build("vbase")
        changed = json.loads(self.outputs.read_text())
        changed["history_groups"][0]["requests"][1]["variables"] = ["RF3"]
        changed_path = Path(self.td.name) / "outputs_var.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, changed_path,
                               Path(self.td.name) / "vchanged")
        self.assertNotEqual(base["blocks"]["outputs"]["sha256"], other["blocks"]["outputs"]["sha256"])
        self.assertNotIn("U3", (Path(self.td.name) / "vchanged/blocks/outputs.inc").read_text())
        for key in ("material_section", "rigid_platens", "boundary_conditions",
                    "contact", "step_loading", "step_end"):
            self.assertEqual(base["blocks"][key]["sha256"], other["blocks"][key]["sha256"], key)

    def test_outputs_renderer_defers_region_existence_to_m1_7(self):
        # Renderer-level contract: an undefined node set is rendered and collected
        # by the renderer; existence checking is M1-7's final-build job.
        config = json.loads(self.outputs.read_text())
        config["history_groups"][0]["requests"][1]["region"]["name"] = "TEST_SET"
        self.assertIn("*Node Output, nset=TEST_SET", _render_outputs(config))

    def test_outputs_profile_id_is_metadata_only(self):
        base = self.build("pid_base")
        changed = json.loads(self.outputs.read_text())
        changed["profile_id"] = "renamed_profile"
        changed_path = Path(self.td.name) / "outputs_pid.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, changed_path,
                               Path(self.td.name) / "pid_changed")
        self.assertEqual(other["blocks"]["outputs"]["profile_id"], "renamed_profile")
        self.assertEqual(base["blocks"]["outputs"]["sha256"], other["blocks"]["outputs"]["sha256"])
        self.assertEqual(base["build_key"], other["build_key"])
        self.assertNotEqual(base["outputs_config_sha256"], other["outputs_config_sha256"])

    def test_outputs_preflight_errors(self):
        good = json.loads(self.outputs.read_text())
        out = Path(self.td.name) / "never_created"
        cases = (
            ("schema2", dict(good, schema_version=2), "NOT_IMPLEMENTED"),
            ("schema_str", dict(good, schema_version="1"), "CONFIG_INVALID"),
            ("profile_empty", dict(good, profile_id=""), "CONFIG_INVALID"),
            ("restart_on", dict(good, restart={"policy": "every_n_increments"}), "NOT_IMPLEMENTED"),
            ("n_zero", dict(good, field_groups=[
                {"schedule": {"type": "every_n_increments", "n": 0}, "mode": "preselect"}]), "CONFIG_INVALID"),
            ("n_bool", dict(good, field_groups=[
                {"schedule": {"type": "every_n_increments", "n": True}, "mode": "preselect"}]), "CONFIG_INVALID"),
            ("sched_interval", dict(good, field_groups=[
                {"schedule": {"type": "number_intervals"}, "mode": "preselect"}]), "NOT_IMPLEMENTED"),
            ("field_explicit", dict(good, field_groups=[
                {"schedule": {"type": "every_n_increments", "n": 5}, "mode": "explicit",
                 "requests": [{"kind": "node", "region": {"type": "node_set", "name": "RP_TOP"},
                               "mode": "explicit", "variables": ["U1"]}]}]), "NOT_IMPLEMENTED"),
            ("unknown_kind", dict(good, history_groups=[
                {"schedule": {"type": "every_n_increments", "n": 1}, "requests": [
                    {"kind": "contact", "region": {"type": "whole_model"}, "mode": "explicit",
                     "variables": ["CPRESS"]}]}]), "NOT_IMPLEMENTED"),
            ("preselect_with_requests", dict(good, history_groups=[
                {"schedule": {"type": "every_n_increments", "n": 1}, "mode": "preselect",
                 "requests": good["history_groups"][0]["requests"]}, good["history_groups"][1]]),
             "CONFIG_INVALID"),
            ("requests_empty", dict(good, history_groups=[
                {"schedule": {"type": "every_n_increments", "n": 1}, "requests": []},
                good["history_groups"][1]]), "CONFIG_INVALID"),
            ("bad_variable", dict(good, history_groups=[
                {"schedule": {"type": "every_n_increments", "n": 1}, "requests": [
                    {"kind": "node", "region": {"type": "node_set", "name": "RP_TOP"},
                     "mode": "explicit", "variables": ["RF3, U3"]}]}]), "CONFIG_INVALID"),
        )
        for index, (name, payload, code) in enumerate(cases):
            outputs_path = Path(self.td.name) / ("outputs_case_%d.json" % index)
            atomic_json(outputs_path, payload)
            with self.assertRaises(PipelineError, msg=name) as caught:
                build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, outputs_path, out)
            self.assertEqual(caught.exception.code, code, name)
        self.assertFalse(out.exists())

    def test_outputs_missing_file_input_missing(self):
        out = Path(self.td.name) / "missing_attempt"
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                           self.material, self.numerics,
                           Path(self.td.name) / "absent_outputs.json", out)
        self.assertEqual(caught.exception.code, "INPUT_MISSING")
        self.assertFalse(out.exists())

    def test_outputs_empty_groups_not_implemented(self):
        base_config = json.loads(self.outputs.read_text())
        out = Path(self.td.name) / "empty_attempt"
        for name, mutation in (("field", dict(base_config, field_groups=[])),
                               ("history", dict(base_config, history_groups=[]))):
            path = Path(self.td.name) / ("outputs_empty_%s.json" % name)
            atomic_json(path, mutation)
            with self.assertRaises(PipelineError, msg=name) as caught:
                build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, path, out)
            self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED", name)
        self.assertFalse(out.exists())

    def test_outputs_unknown_variable_allowed(self):
        changed = json.loads(self.outputs.read_text())
        changed["history_groups"][0]["requests"][1]["variables"] = ["RF3", "U3", "SDV_7"]
        changed_path = Path(self.td.name) / "outputs_sdv.json"
        atomic_json(changed_path, changed)
        other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, changed_path,
                               Path(self.td.name) / "sdv")
        self.assertIn("SDV_7", (Path(self.td.name) / "sdv/blocks/outputs.inc").read_text())
        self.assertIn("SDV_7", other["blocks"]["outputs"]["requested_variables"][1]["variables"])

    def test_outputs_provenance_whitespace(self):
        base = self.build("wbase")
        reformatted = Path(self.td.name) / "outputs_reformatted.json"
        config = json.loads(self.outputs.read_text())
        reformatted.write_text(json.dumps(config, indent=4) + "\n", encoding="utf-8")
        other = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                               self.material, self.numerics, reformatted,
                               Path(self.td.name) / "reformatted")
        self.assertNotEqual(base["outputs_config_sha256"], other["outputs_config_sha256"])
        self.assertEqual(base["blocks"]["outputs"]["sha256"], other["blocks"]["outputs"]["sha256"])
        self.assertEqual(base["build_key"], other["build_key"])


class PhysicalInpAssemblyTests(_BuilderFixtureMixin, unittest.TestCase):
    """M1-7 regression: physical.inp assembly and repository static validation.

    PASS here means repository-level internal self-consistency only; nothing in
    this class claims Abaqus acceptance.
    """

    def _attempt(self, name):
        folder = Path(self.td.name) / name
        manifest = build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                                  self.material, self.numerics, self.outputs, folder)
        return folder, manifest

    def _failed_stage(self, name, manifest):
        """Re-run the M1-7 stage on a prepared attempt and return the failing report."""
        with self.assertRaises(PipelineError) as caught:
            _run_static_stage(Path(self.td.name) / name, manifest)
        self.assertEqual(caught.exception.code, "STATIC_VALIDATION_FAILED")
        report = json.loads((Path(self.td.name) / name / "build_report.json").read_text())
        self.assertEqual(report["status"], "STATIC_VALIDATION_FAILED")
        self.assertEqual(report["static_validation"], "FAILED")
        return report

    def _failed_checks(self, name, manifest):
        """Validate a deliberately tampered attempt (physical.inp is not republished here)."""
        checks = _validate_static_model(Path(self.td.name) / name, manifest)
        failed = sorted(key for key, check in checks.items() if check["status"] != "PASS")
        self.assertTrue(failed, "expected at least one failed check")
        return failed

    def test_physical_inp_deterministic(self):
        one, one_manifest = self._attempt("det_one")
        two, two_manifest = self._attempt("det_two")
        for rel in ("physical.inp", "build_report.json", "model_manifest.json"):
            self.assertEqual((one / rel).read_bytes(), (two / rel).read_bytes(), rel)
        self.assertEqual(one_manifest["build_key"], two_manifest["build_key"])

    def test_exact_include_order(self):
        folder, _manifest = self._attempt("order")
        includes = _parse_includes((folder / "physical.inp").read_text())
        self.assertEqual(includes, [
            "ingredients/shell_mesh.inc", "blocks/material_section.inc",
            "blocks/rigid_platens.inc", "ingredients/lateral_pbc.inc",
            "blocks/boundary_conditions.inc", "blocks/contact.inc",
            "blocks/step_loading.inc", "blocks/outputs.inc", "blocks/step_end.inc"])
        text = (folder / "physical.inp").read_text()
        for target in includes:
            self.assertNotIn(":", target)
            self.assertNotIn("..", target)
            self.assertNotIn("\\", target)
        self.assertIn("*Include, input=blocks/step_end.inc", text)

    def test_missing_include_artifact_fails(self):
        folder, manifest = self._attempt("missing_inc")
        (folder / "blocks/contact.inc").unlink()
        report = self._failed_stage("missing_inc", manifest)
        self.assertIn("artifact_integrity", report["failed_checks"])

    def test_tampered_block_sha_fails(self):
        folder, manifest = self._attempt("tampered")
        with (folder / "blocks/material_section.inc").open("a", encoding="utf-8") as stream:
            stream.write("** tampered\n")
        report = self._failed_stage("tampered", manifest)
        self.assertIn("artifact_integrity", report["failed_checks"])
        self.assertTrue(any("sha256 mismatch" in detail
                            for detail in report["static_checks"]["artifact_integrity"]["details"]))

    def test_duplicate_node_label_fails(self):
        folder, manifest = self._attempt("dup_node")
        with (folder / "ingredients/shell_mesh.inc").open("a", encoding="utf-8") as stream:
            stream.write("*Node\n1, 0.0, 0.0, 0.0\n")
        report = self._failed_stage("dup_node", manifest)
        self.assertIn("label_uniqueness", report["failed_checks"])

    def test_duplicate_element_label_fails(self):
        folder, manifest = self._attempt("dup_elem")
        with (folder / "ingredients/shell_mesh.inc").open("a", encoding="utf-8") as stream:
            stream.write("*Element, type=S3R, elset=SHELL_ALL\n1, 2, 3, 4\n")
        report = self._failed_stage("dup_elem", manifest)
        self.assertIn("label_uniqueness", report["failed_checks"])

    def test_undefined_node_in_nset_fails(self):
        folder, manifest = self._attempt("bad_nset")
        with (folder / "blocks/rigid_platens.inc").open("a", encoding="utf-8") as stream:
            stream.write("*Nset, nset=BOGUS_SET\n999999,\n")
        report = self._failed_stage("bad_nset", manifest)
        self.assertIn("node_reference_integrity", report["failed_checks"])

    def test_undefined_node_in_element_connectivity_fails(self):
        folder, manifest = self._attempt("bad_elem")
        with (folder / "ingredients/shell_mesh.inc").open("a", encoding="utf-8") as stream:
            stream.write("*Element, type=S3R, elset=SHELL_ALL\n99, 1, 2, 999999\n")
        report = self._failed_stage("bad_elem", manifest)
        self.assertIn("element_reference_integrity", report["failed_checks"])

    def test_nonexistent_output_region_fails_final_build(self):
        changed = json.loads(self.outputs.read_text())
        changed["history_groups"][0]["requests"][1]["region"]["name"] = "TEST_SET"
        outputs_path = Path(self.td.name) / "outputs_testset.json"
        atomic_json(outputs_path, changed)
        out = Path(self.td.name) / "testset_attempt"
        with self.assertRaises(PipelineError) as caught:
            build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                           self.material, self.numerics, outputs_path, out)
        self.assertEqual(caught.exception.code, "STATIC_VALIDATION_FAILED")
        # Failure evidence is retained; nothing is marked successful.
        self.assertTrue((out / "physical.inp").is_file())
        report = json.loads((out / "build_report.json").read_text())
        for check in ("output_region_integrity", "region_integrity"):
            self.assertIn(check, report["failed_checks"])
        failed_manifest = json.loads((out / "model_manifest.json").read_text())
        self.assertEqual(failed_manifest["status"], "PHYSICAL_INP_STATIC_VALIDATION_FAILED")
        self.assertIs(failed_manifest["dataset_eligible"], False)

    def test_missing_end_step_fails(self):
        folder, manifest = self._attempt("no_end")
        (folder / "blocks/step_end.inc").write_text("** end step removed\n", encoding="utf-8")
        report = self._failed_stage("no_end", manifest)
        self.assertIn("step_pairing", report["failed_checks"])

    def test_duplicated_step_fails(self):
        folder, manifest = self._attempt("dup_step")
        text = (folder / "physical.inp").read_text()
        (folder / "physical.inp").write_text(
            text.replace("*Include, input=blocks/step_end.inc",
                         "*Include, input=blocks/step_loading.inc"), encoding="utf-8")
        failed = self._failed_checks("dup_step", manifest)
        self.assertIn("step_pairing", failed)
        self.assertIn("include_graph", failed)

    def test_wrong_step_output_order_fails(self):
        folder, manifest = self._attempt("swap_order")
        lines = (folder / "physical.inp").read_text().splitlines()
        i = lines.index("*Include, input=blocks/step_loading.inc")
        j = lines.index("*Include, input=blocks/outputs.inc")
        lines[i], lines[j] = lines[j], lines[i]
        (folder / "physical.inp").write_text("\n".join(lines) + "\n", encoding="utf-8")
        failed = self._failed_checks("swap_order", manifest)
        self.assertIn("step_order", failed)
        self.assertIn("include_graph", failed)

    def test_target_displacement_mismatch_fails(self):
        folder, manifest = self._attempt("target")
        bad = dict(manifest, target_displacement_mm=manifest["target_displacement_mm"] * 2)
        report = self._failed_stage("target", bad)
        self.assertIn("target_consistency", report["failed_checks"])

    def test_rp_x_ctrl_constrained_fails(self):
        folder, manifest = self._attempt("rpx")
        block = folder / "blocks/boundary_conditions.inc"
        block.write_text(block.read_text(encoding="utf-8").replace(
            "RP_BOTTOM, 1, 1", "RP_X_CTRL, 1, 1"), encoding="utf-8")
        report = self._failed_stage("rpx", manifest)
        self.assertIn("boundary_contract", report["failed_checks"])

    def test_rp_y_ctrl_constrained_fails(self):
        folder, manifest = self._attempt("rpy")
        block = folder / "blocks/boundary_conditions.inc"
        block.write_text(block.read_text(encoding="utf-8").replace(
            "RP_BOTTOM, 2, 2", "RP_Y_CTRL, 2, 2"), encoding="utf-8")
        report = self._failed_stage("rpy", manifest)
        self.assertIn("boundary_contract", report["failed_checks"])

    def test_rp_top_u3_model_level_fixed_fails(self):
        folder, manifest = self._attempt("top_u3")
        with (folder / "blocks/boundary_conditions.inc").open("a", encoding="utf-8") as stream:
            stream.write("RP_TOP, 3, 3\n")
        report = self._failed_stage("top_u3", manifest)
        self.assertIn("boundary_contract", report["failed_checks"])

    def test_missing_step_u3_loading_fails(self):
        folder, manifest = self._attempt("no_u3")
        block = folder / "blocks/step_loading.inc"
        kept = [line for line in block.read_text(encoding="utf-8").splitlines()
                if not line.startswith("RP_TOP, 3, 3")]
        block.write_text("\n".join(kept) + "\n", encoding="utf-8")
        report = self._failed_stage("no_u3", manifest)
        self.assertIn("boundary_contract", report["failed_checks"])

    def test_time_amplitude_mismatch_fails(self):
        folder, manifest = self._attempt("time")
        bad = dict(manifest, physics=dict(manifest["physics"], time_period_s=2.0))
        report = self._failed_stage("time", bad)
        self.assertIn("time_amplitude_consistency", report["failed_checks"])

    def test_final_manifest_stays_dataset_ineligible(self):
        folder, manifest = self._attempt("eligible")
        self.assertIs(manifest["dataset_eligible"], False)
        disk = json.loads((folder / "model_manifest.json").read_text())
        self.assertIs(disk["dataset_eligible"], False)
        report = json.loads((folder / "build_report.json").read_text())
        self.assertIs(report["dataset_eligible"], False)

    def test_successful_static_build_writes_build_report(self):
        folder, manifest = self._attempt("report")
        path = folder / "build_report.json"
        self.assertTrue(path.is_file())
        report = json.loads(path.read_text())
        self.assertEqual(report["status"], "STATIC_VALIDATION_PASSED")
        self.assertEqual(report["static_validation"], "PASS")
        for stage in ("abaqus_datacheck", "solve", "odb_qa"):
            self.assertEqual(report[stage], "NOT_RUN", stage)
        self.assertEqual(report["model_key"], manifest["identity"]["model_key"])
        self.assertEqual(report["scaffold_key"], manifest["scaffold_key"])
        self.assertEqual(report["build_key"], manifest["build_key"])
        self.assertEqual(report["builder"], manifest["builder"])
        expected_checks = {"artifact_integrity", "include_graph", "label_uniqueness",
                           "node_reference_integrity", "element_reference_integrity",
                           "region_integrity", "pbc_reference_integrity", "boundary_contract",
                           "step_pairing", "step_order", "target_consistency",
                           "time_amplitude_consistency", "output_region_integrity"}
        self.assertEqual(set(report["static_checks"]), expected_checks)
        for name, check in report["static_checks"].items():
            self.assertEqual(check["status"], "PASS", name)
        self.assertEqual(manifest["build_report"]["sha256"], file_hash(path))

    def test_successful_static_build_writes_physical_inp(self):
        folder, manifest = self._attempt("inp")
        path = folder / "physical.inp"
        self.assertTrue(path.is_file())
        self.assertEqual(manifest["physical_inp"]["path"], "physical.inp")
        self.assertEqual(manifest["physical_inp"]["sha256"], file_hash(path))
        self.assertEqual(manifest["status"], "PHYSICAL_INP_STATIC_VALIDATED")
        text = path.read_text()
        self.assertTrue(text.startswith("**"))
        self.assertIn("*Include, input=ingredients/shell_mesh.inc", text)
        for rel in ("ingredients/shell_mesh.inc", "ingredients/lateral_pbc.inc",
                    "blocks/step_end.inc"):
            self.assertTrue((folder / rel).is_file(), rel)


class PhysicalDataCheckTests(_BuilderFixtureMixin, unittest.TestCase):
    """M2 regression: staging, launcher resolution and datacheck judgement.

    No test here invokes a real Abaqus; subprocess and release queries are
    mocked, and diagnostics come from small fixture files.
    """

    JOB = "fig1_m2_datacheck"

    def _source(self, name="m2_source"):
        # Prefix keeps source and datacheck-attempt directories distinct.
        folder = Path(self.td.name) / ("src_" + name)
        build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                       self.material, self.numerics, self.outputs, folder)
        return folder

    def _fake_launcher(self):
        return self._shared_fake_launcher()

    def _fake_process(self, dat=None, msg=None, log=None, returncode=0):
        calls = []

        def fake(argv, cwd, timeout_s):
            cwd = Path(cwd)
            if dat is not None:
                (cwd / (self.JOB + ".dat")).write_text(dat, encoding="utf-8")
            if msg is not None:
                (cwd / (self.JOB + ".msg")).write_text(msg, encoding="utf-8")
            if log is not None:
                (cwd / (self.JOB + ".log")).write_text(log, encoding="utf-8")
            (cwd / (self.JOB + ".odb")).write_bytes(b"fake datacheck odb")
            calls.append([str(part) for part in argv])
            return returncode, "fake stdout", ""

        return fake, calls

    def _run_m2(self, source, out, dat, log, msg=None, returncode=0, **kwargs):
        fake, calls = self._fake_process(dat, msg, log, returncode)
        # Point the policy file at a nonexistent temp path so tests are machine-
        # independent and hit the safe default unless a test overrides it.
        kwargs.setdefault("policy_path", Path(self.td.name) / "no_policy_file.json")
        with mock.patch("pipeline.physical_datacheck._run_process", fake), \
                mock.patch("pipeline.physical_datacheck.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pdc.run_datacheck(source, out, abaqus_command=self._fake_launcher(), **kwargs)
        return report, calls

    def test_source_status_not_validated_fails(self):
        source = self._source("bad_status")
        manifest_path = source / "model_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["status"] = "PHYSICAL_BUILD_PARTIAL"
        atomic_json(manifest_path, manifest)
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, Path(self.td.name) / "no_attempt",
                              abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_BUILD_INVALID")

    def test_source_static_validation_not_pass_fails(self):
        source = self._source("bad_static")
        report_path = source / "build_report.json"
        report = json.loads(report_path.read_text())
        report["static_validation"] = "FAILED"
        atomic_json(report_path, report)
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, Path(self.td.name) / "no_attempt",
                              abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_BUILD_INVALID")

    def test_physical_inp_sha_mismatch_fails(self):
        source = self._source("bad_sha")
        with (source / "physical.inp").open("a", encoding="utf-8") as stream:
            stream.write("** tampered\n")
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, Path(self.td.name) / "no_attempt",
                              abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_BUILD_INVALID")

    def test_staging_preserves_input_sha_and_source(self):
        source = self._source("staging")
        deck_sha_before = file_hash(source / "physical.inp")
        out = Path(self.td.name) / "staged"
        report, _calls = self._run_m2(source, out, "ANALYSIS DATACHECK COMPLETE",
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        for entry in report["staged_files"]:
            self.assertEqual(entry["sha256"], file_hash(out / entry["path"]), entry["path"])
        self.assertEqual(file_hash(source / "physical.inp"), deck_sha_before)
        self.assertTrue((out / "source_model_manifest.json").is_file())
        self.assertTrue((out / "source_build_report.json").is_file())

    def test_launcher_not_found_fails(self):
        with self.assertRaises(PipelineError) as caught:
            pdc.resolve_launcher("no_such_launcher_anywhere_xyz")
        self.assertEqual(caught.exception.code, "ABAQUS_LAUNCHER_NOT_FOUND")
        source = self._source("launcher_source")
        out = Path(self.td.name) / "never_started"
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, out, abaqus_command="no_such_launcher_anywhere_xyz")
        self.assertEqual(caught.exception.code, "ABAQUS_LAUNCHER_NOT_FOUND")
        self.assertFalse(out.exists())

    def test_command_contains_datacheck(self):
        source = self._source("cmd")
        report, calls = self._run_m2(source, Path(self.td.name) / "cmd",
                                     "ANALYSIS DATACHECK COMPLETE",
                                     "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(len(calls), 1)
        self.assertIn("datacheck", calls[0])
        self.assertIn("job=fig1_m2_datacheck", calls[0])
        self.assertIn("input=physical.inp", calls[0])
        command = json.loads((Path(self.td.name) / "cmd/command.json").read_text())
        self.assertTrue(command["datacheck_flag_present"])
        self.assertEqual(command["job_name"], "fig1_m2_datacheck")
        self.assertEqual(report["abaqus"]["release"]["release"], "Abaqus 2026 TEST")

    # Execution policy: safe default, overrides and validation.
    def test_safe_default_execution_policy(self):
        source = self._source("policy_default")
        report, calls = self._run_m2(source, Path(self.td.name) / "policy_default",
                                     "ANALYSIS DATACHECK COMPLETE",
                                     "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertIn("cpus=1", calls[0])
        self.assertIn("standard_parallel=solver", calls[0])
        self.assertEqual(report["execution_policy"],
                         {"cpus": 1, "standard_parallel": "solver", "source": "safe_default"})
        self.assertEqual(report["claims"]["physical_datacheck"], "PASS")

    def test_local_policy_file_override(self):
        source = self._source("policy_local")
        policy = Path(self.td.name) / "policy_local.json"
        atomic_json(policy, {"schema_version": 1, "cpus": 2, "standard_parallel": "all"})
        report, calls = self._run_m2(source, Path(self.td.name) / "policy_local",
                                     "ANALYSIS DATACHECK COMPLETE",
                                     "Abaqus JOB fig1_m2_datacheck COMPLETED",
                                     policy_path=policy)
        self.assertIn("cpus=2", calls[0])
        self.assertIn("standard_parallel=all", calls[0])
        self.assertEqual(report["execution_policy"]["source"], "local_environment")
        self.assertEqual(report["execution_policy"]["cpus"], 2)

    def test_cli_override_beats_local_policy_file(self):
        source = self._source("policy_cli")
        policy = Path(self.td.name) / "policy_cli.json"
        atomic_json(policy, {"schema_version": 1, "cpus": 2, "standard_parallel": "all"})
        report, calls = self._run_m2(source, Path(self.td.name) / "policy_cli",
                                     "ANALYSIS DATACHECK COMPLETE",
                                     "Abaqus JOB fig1_m2_datacheck COMPLETED",
                                     policy_path=policy, cpus=3, standard_parallel="solver")
        self.assertIn("cpus=3", calls[0])
        self.assertIn("standard_parallel=solver", calls[0])
        self.assertEqual(report["execution_policy"]["source"], "cli")

    def test_invalid_execution_policy_rejected(self):
        source = self._source("policy_bad")
        for kwargs in ({"cpus": 0}, {"cpus": -1}, {"cpus": "two"}, {"cpus": True},
                       {"standard_parallel": "threads"}, {"standard_parallel": 1}):
            with self.assertRaises(PipelineError, msg=repr(kwargs)) as caught:
                pdc.run_datacheck(source, Path(self.td.name) / ("bad_policy_%s" % id(kwargs)),
                                  abaqus_command=self._fake_launcher(),
                                  policy_path=Path(self.td.name) / "no_policy_file.json",
                                  **kwargs)
            self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        bad_file = Path(self.td.name) / "policy_bad.json"
        atomic_json(bad_file, {"schema_version": 1, "cpus": 1, "standard_parallel": "threads"})
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, Path(self.td.name) / "bad_policy_file",
                              abaqus_command=self._fake_launcher(), policy_path=bad_file)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        atomic_json(bad_file, {"schema_version": 2, "cpus": 1, "standard_parallel": "solver",
                               "extra": True})
        with self.assertRaises(PipelineError) as caught:
            pdc.run_datacheck(source, Path(self.td.name) / "bad_policy_file2",
                              abaqus_command=self._fake_launcher(), policy_path=bad_file)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_command_never_analysis_or_continue(self):
        source = self._source("cmdsafe")
        _report, calls = self._run_m2(source, Path(self.td.name) / "cmdsafe",
                                      "ANALYSIS DATACHECK COMPLETE",
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        for forbidden in ("analysis", "continue", "interactive=continue"):
            self.assertNotIn(forbidden, calls[0])
        command = json.loads((Path(self.td.name) / "cmdsafe/command.json").read_text())
        self.assertIs(command["analysis_flag_present"], False)

    def test_nonzero_returncode_fails(self):
        source = self._source("rc")
        report, _calls = self._run_m2(source, Path(self.td.name) / "rc",
                                      "ANALYSIS DATACHECK COMPLETE",
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED", returncode=1)
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertEqual(report["claims"]["physical_datacheck"], "FAIL")
        self.assertTrue(any(reason.startswith("return_code=1")
                            for reason in report["failure_reasons"]))

    def test_error_in_dat_fails(self):
        source = self._source("err")
        dat = ("***ERROR: keyword is misplaced\n"
               "line=bad_region\n"
               "ANALYSIS DATACHECK COMPLETE\n")
        report, _calls = self._run_m2(source, Path(self.td.name) / "err", dat,
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertEqual(report["diagnostics"]["error_count"], 1)
        error = report["diagnostics"]["errors"][0]
        self.assertEqual(error["source_file"], "fig1_m2_datacheck.dat")
        self.assertEqual(error["line_number"], 1)
        self.assertIn("line=bad_region", error["message"])

    def test_missing_completion_marker_fails(self):
        # A clean-looking run without 'ANALYSIS DATACHECK COMPLETE' is not an
        # accepted datacheck (M3.1 hardening of the completion gate).
        source = Path(self.td.name) / "src_marker"
        build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                       self.material, self.numerics, self.outputs, source)
        marker = "ANALYSIS DATACHECK COMPLETE"
        dat_without_marker = ("***WARNING: the general contact domain has double-sided facets\n"
                              "DATA CHECK ENDED\n")
        out = Path(self.td.name) / "no_marker"
        fake, _calls = self._fake_process(dat=dat_without_marker,
                                          log="Abaqus JOB fig1_m2_datacheck COMPLETED")
        with mock.patch("pipeline.physical_datacheck._run_process", fake), \
                mock.patch("pipeline.physical_datacheck.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pdc.run_datacheck(source, out, abaqus_command=self._fake_launcher(),
                                       policy_path=Path(self.td.name) / "no_policy.json")
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertIn("datacheck completion marker missing", report["failure_reasons"])
        self.assertIs(report["diagnostics"]["datacheck_complete_evidence"], False)

    def test_warning_only_is_completed_with_warnings(self):
        source = self._source("warn")
        dat = ("***WARNING: overclosure is adjusted during strainfree initialization\n"
               "surface=PLATE_BOTTOM\n"
               "ANALYSIS DATACHECK COMPLETE\n")
        report, _calls = self._run_m2(source, Path(self.td.name) / "warn", dat,
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(report["status"], "DATACHECK_COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["claims"]["physical_datacheck"], "COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["diagnostics"]["error_count"], 0)
        self.assertEqual(report["diagnostics"]["warning_count"], 1)
        warning = report["diagnostics"]["warnings"][0]
        self.assertIn("overclosure", warning["message"])
        self.assertIn(warning["category"], ("CONTACT", "STRAINFREE"))

    def test_clean_output_passes(self):
        source = self._source("clean")
        report, _calls = self._run_m2(
            source, Path(self.td.name) / "clean",
            "ANALYSIS DATACHECK COMPLETE\n",
            "Abaqus JOB fig1_m2_datacheck COMPLETED\n")
        self.assertEqual(report["status"], "DATACHECK_PASSED")
        self.assertEqual(report["claims"]["physical_datacheck"], "PASS")
        self.assertEqual(report["diagnostics"]["error_count"], 0)
        self.assertEqual(report["diagnostics"]["warning_count"], 0)
        self.assertTrue(report["diagnostics"]["datacheck_complete_evidence"])
        self.assertTrue(report["diagnostics"]["job_completed_evidence"])
        self.assertEqual(report["diagnostics"]["abort_evidence"], [])
        self.assertTrue((Path(self.td.name) / "clean/datacheck_report.json").is_file())

    def test_missing_required_artifact_fails(self):
        source = self._source("nodat")
        report, _calls = self._run_m2(source, Path(self.td.name) / "nodat", dat=None,
                                      log="Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertIn("missing required artifacts: dat", report["failure_reasons"])

    def test_missing_odb_fails(self):
        # .odb is required; a completed-looking run without it must not pass.
        source = self._source("noodb")

        def fake_no_odb(argv, cwd, timeout_s):
            cwd = Path(cwd)
            (cwd / (self.JOB + ".dat")).write_text("ANALYSIS DATACHECK COMPLETE", encoding="utf-8")
            (cwd / (self.JOB + ".log")).write_text(
                "Abaqus JOB fig1_m2_datacheck COMPLETED", encoding="utf-8")
            return 0, "fake stdout", ""

        with mock.patch("pipeline.physical_datacheck._run_process", fake_no_odb), \
                mock.patch("pipeline.physical_datacheck.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pdc.run_datacheck(source, Path(self.td.name) / "noodb",
                                       abaqus_command=self._fake_launcher(),
                                       policy_path=Path(self.td.name) / "no_policy_file.json")
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertIn("missing required artifacts: odb", report["failure_reasons"])

    def test_missing_log_alone_does_not_fail(self):
        # Abaqus 2026 datacheck interactive runs complete without writing a .log.
        source = self._source("nolog")
        report, _calls = self._run_m2(source, Path(self.td.name) / "nolog",
                                      dat="ANALYSIS DATACHECK COMPLETE", log=None)
        self.assertEqual(report["status"], "DATACHECK_PASSED")
        self.assertNotIn("log", [f["kind"] for f in report["artifacts"]["generated_files"]])

    def test_report_claims_solve_and_odb_qa_not_run(self):
        source = self._source("claims")
        report, _calls = self._run_m2(source, Path(self.td.name) / "claims",
                                      "ANALYSIS DATACHECK COMPLETE",
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(report["claims"]["solve"], "NOT_RUN")
        self.assertEqual(report["claims"]["odb_results_qa"], "NOT_RUN")
        self.assertTrue((Path(self.td.name) / "claims/command.json").is_file())
        self.assertTrue((Path(self.td.name) / "claims/stdout.txt").is_file())
        self.assertTrue((Path(self.td.name) / "claims/stderr.txt").is_file())

    def test_report_dataset_eligible_false(self):
        source = self._source("eligible")
        report, _calls = self._run_m2(source, Path(self.td.name) / "eligible",
                                      "ANALYSIS DATACHECK COMPLETE",
                                      "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertIs(report["claims"]["dataset_eligible"], False)

    def test_existing_attempt_not_overwritten(self):
        source = self._source("existing")
        out = Path(self.td.name) / "existing_attempt"
        out.mkdir()
        (out / "sentinel.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(PipelineError) as caught:
            self._run_m2(source, out, "ANALYSIS DATACHECK COMPLETE",
                         "Abaqus JOB fig1_m2_datacheck COMPLETED")
        self.assertEqual(caught.exception.code, "OUTPUT_EXISTS")
        self.assertEqual((out / "sentinel.txt").read_text(), "keep")


class PhysicalSolveTests(_BuilderFixtureMixin, unittest.TestCase):
    """M3 regression: accepted-deck staging, runtime policy and solve judgement.

    No test invokes a real Abaqus; the analysis subprocess and release query are
    mocked, and completion evidence comes from small fixture files.
    """

    JOB = "fig1_m3_solve"
    _STA_OK = ("   1     1   1     0     1     1     1   0.000E+00   2.500E-02\n"
               "   1    40   1     0     2     2     2   9.999E-01   1.000E+00\n"
               " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
    _DC_DAT = ("***WARNING: the general contact domain has double-sided facets\n"
               "ANALYSIS DATACHECK COMPLETE\n")
    _DC_LOG = "Abaqus JOB fig1_m2_datacheck COMPLETED\n"

    def _fake_launcher(self):
        return self._shared_fake_launcher()

    def _run_datacheck(self, source, out):
        def fake_dc(argv, cwd, timeout_s):
            cwd = Path(cwd)
            (cwd / "fig1_m2_datacheck.dat").write_text(self._DC_DAT, encoding="utf-8")
            (cwd / "fig1_m2_datacheck.odb").write_bytes(b"fake dc odb")
            return 0, self._DC_LOG, ""

        with mock.patch("pipeline.physical_datacheck._run_process", fake_dc), \
                mock.patch("pipeline.physical_datacheck.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            return pdc.run_datacheck(source, out, abaqus_command=self._fake_launcher(),
                                     policy_path=Path(self.td.name) / "no_policy.json")

    def _make_accepted(self, name):
        source = Path(self.td.name) / ("src_" + name)
        build_physical(self.npz, self.report, self.pairs_csv, self.physics,
                       self.material, self.numerics, self.outputs, source)
        dc_dir = Path(self.td.name) / ("dc_" + name)
        self._run_datacheck(source, dc_dir)
        return dc_dir

    def _run_solve(self, dc, out, dat="", msg="", sta=_STA_OK, returncode=0,
                   stdout_completed=True, **kwargs):
        def fake_solve(argv, cwd, timeout_s, stdout_path, stderr_path):
            cwd = Path(cwd)
            (cwd / (self.JOB + ".dat")).write_text(dat, encoding="utf-8")
            (cwd / (self.JOB + ".msg")).write_text(msg, encoding="utf-8")
            if sta is not None:
                (cwd / (self.JOB + ".sta")).write_text(sta, encoding="utf-8")
            (cwd / (self.JOB + ".odb")).write_bytes(b"fake complete odb")
            text = ("Abaqus JOB " + self.JOB + " COMPLETED\n" if stdout_completed
                    else "Abaqus JOB " + self.JOB + " aborted\n")
            Path(stdout_path).write_text(text, encoding="utf-8")
            Path(stderr_path).write_text("", encoding="utf-8")
            return returncode

        kwargs.setdefault("policy_path", Path(self.td.name) / "no_policy.json")
        with mock.patch("pipeline.physical_solve._run_process_to_files", fake_solve), \
                mock.patch("pipeline.physical_solve.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            return pds.run_solve(dc, out, abaqus_command=self._fake_launcher(), **kwargs)

    # Source datacheck preconditions (1-3).
    def test_non_accepted_datacheck_status_rejected(self):
        dc = self._make_accepted("bad_status")
        report_path = dc / "datacheck_report.json"
        report = json.loads(report_path.read_text())
        report["status"] = "DATACHECK_FAILED"
        atomic_json(report_path, report)
        with self.assertRaises(PipelineError) as caught:
            pds.run_solve(dc, Path(self.td.name) / "never",
                          abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_INVALID")

    def test_datacheck_with_errors_rejected(self):
        dc = self._make_accepted("dc_errors")
        report_path = dc / "datacheck_report.json"
        report = json.loads(report_path.read_text())
        report["diagnostics"]["error_count"] = 1
        atomic_json(report_path, report)
        with self.assertRaises(PipelineError) as caught:
            pds.run_solve(dc, Path(self.td.name) / "never",
                          abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_INVALID")

    def test_physical_inp_sha_mismatch_rejected(self):
        dc = self._make_accepted("sha_mismatch")
        with (dc / "physical.inp").open("a", encoding="utf-8") as stream:
            stream.write("** tampered\n")
        with self.assertRaises(PipelineError) as caught:
            pds.run_solve(dc, Path(self.td.name) / "never",
                          abaqus_command=self._fake_launcher())
        self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_INVALID")

    # Staging (4).
    def test_staging_preserves_sha_and_provenance(self):
        dc = self._make_accepted("staging")
        out = Path(self.td.name) / "staged"
        report = self._run_solve(dc, out)
        for entry in report["staged_files"]:
            self.assertEqual(entry["sha256"], file_hash(out / entry["path"]), entry["path"])
        self.assertTrue((out / "source_datacheck_report.json").is_file())
        self.assertTrue((out / "source_model_manifest.json").is_file())
        self.assertTrue((out / "source_build_report.json").is_file())

    # Runtime policy (5-9).
    def test_safe_default_policy(self):
        dc = self._make_accepted("pol_default")
        report = self._run_solve(dc, Path(self.td.name) / "pol_default")
        self.assertEqual(report["execution"]["cpus"], 1)
        self.assertEqual(report["execution"]["standard_parallel"], "solver")
        self.assertEqual(report["execution"]["policy_source"], "safe_default")

    def test_local_policy_override(self):
        dc = self._make_accepted("pol_local")
        policy = Path(self.td.name) / "policy_local.json"
        atomic_json(policy, {"schema_version": 1, "cpus": 4, "standard_parallel": "solver"})
        report = self._run_solve(dc, Path(self.td.name) / "pol_local", policy_path=policy)
        self.assertEqual(report["execution"]["cpus"], 4)
        self.assertEqual(report["execution"]["policy_source"], "local_environment")

    def test_cli_policy_beats_local_file(self):
        dc = self._make_accepted("pol_cli")
        policy = Path(self.td.name) / "policy_cli.json"
        atomic_json(policy, {"schema_version": 1, "cpus": 4, "standard_parallel": "solver"})
        report = self._run_solve(dc, Path(self.td.name) / "pol_cli", policy_path=policy,
                                 cpus=2, standard_parallel="all")
        self.assertEqual(report["execution"]["cpus"], 2)
        self.assertEqual(report["execution"]["standard_parallel"], "all")
        self.assertEqual(report["execution"]["policy_source"], "cli")

    def test_invalid_policy_rejected(self):
        dc = self._make_accepted("pol_bad")
        for kwargs in ({"cpus": 0}, {"cpus": "two"}, {"cpus": True},
                       {"standard_parallel": "threads"}, {"standard_parallel": 8}):
            with self.assertRaises(PipelineError, msg=repr(kwargs)) as caught:
                pds.run_solve(dc, Path(self.td.name) / ("bad_%s" % id(kwargs)),
                              abaqus_command=self._fake_launcher(),
                              policy_path=Path(self.td.name) / "no_policy.json", **kwargs)
            self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        bad_file = Path(self.td.name) / "policy_bad.json"
        atomic_json(bad_file, {"schema_version": 2, "cpus": 1})
        with self.assertRaises(PipelineError) as caught:
            pds.run_solve(dc, Path(self.td.name) / "bad_file",
                          abaqus_command=self._fake_launcher(), policy_path=bad_file)
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    # Command contract (10-11).
    def test_command_contains_analysis(self):
        dc = self._make_accepted("cmd")
        report = self._run_solve(dc, Path(self.td.name) / "cmd")
        self.assertIn("analysis", report["execution"]["command"])
        command = json.loads((Path(self.td.name) / "cmd/command.json").read_text())
        self.assertTrue(command["analysis_flag_present"])

    def test_command_has_no_datacheck_continue_recover(self):
        dc = self._make_accepted("cmdsafe")
        report = self._run_solve(dc, Path(self.td.name) / "cmdsafe")
        for token in ("datacheck", "continue", "recover"):
            self.assertNotIn(token, report["execution"]["command"])
        command = json.loads((Path(self.td.name) / "cmdsafe/command.json").read_text())
        self.assertIs(command["datacheck_flag_present"], False)
        self.assertIs(command["continue_flag_present"], False)

    # Failure evidence (12-17).
    def test_missing_sta_fails(self):
        dc = self._make_accepted("no_sta")
        report = self._run_solve(dc, Path(self.td.name) / "no_sta", sta=None)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn("missing required artifacts: sta", report["failure_reasons"])

    def test_missing_odb_fails(self):
        dc = self._make_accepted("no_odb")

        def fake_no_odb(argv, cwd, timeout_s, stdout_path, stderr_path):
            cwd = Path(cwd)
            (cwd / (self.JOB + ".dat")).write_text("ANALYSIS COMPLETE TEXT", encoding="utf-8")
            (cwd / (self.JOB + ".msg")).write_text("", encoding="utf-8")
            (cwd / (self.JOB + ".sta")).write_text(self._STA_OK, encoding="utf-8")
            Path(stdout_path).write_text("Abaqus JOB " + self.JOB + " COMPLETED\n", encoding="utf-8")
            Path(stderr_path).write_text("", encoding="utf-8")
            return 0

        with mock.patch("pipeline.physical_solve._run_process_to_files", fake_no_odb), \
                mock.patch("pipeline.physical_solve.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pds.run_solve(dc, Path(self.td.name) / "no_odb",
                                   abaqus_command=self._fake_launcher(),
                                   policy_path=Path(self.td.name) / "no_policy.json")
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn("missing required artifacts: odb", report["failure_reasons"])

    def test_missing_stdout_completion_fails(self):
        dc = self._make_accepted("no_stdout")
        report = self._run_solve(dc, Path(self.td.name) / "no_stdout", stdout_completed=False)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn("stdout completion token missing", report["failure_reasons"])

    def test_missing_sta_completion_marker_fails(self):
        dc = self._make_accepted("no_sta_marker")
        sta = self._STA_OK.replace(" THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n", "")
        report = self._run_solve(dc, Path(self.td.name) / "no_sta_marker", sta=sta)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn(".sta completion marker missing", report["failure_reasons"])

    def test_fatal_diagnostics_fail(self):
        dc = self._make_accepted("fatal")
        dat = ("***ERROR: excessive incremental rotation\n"
               "THE ANALYSIS HAS NOT BEEN COMPLETED\n")
        report = self._run_solve(dc, Path(self.td.name) / "fatal", dat=dat)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertTrue(any("THE ANALYSIS HAS NOT BEEN COMPLETED" in f["message"]
                            for f in report["diagnostics"]["fatal"]))

    def test_target_time_not_reached_fails(self):
        dc = self._make_accepted("short_time")
        sta = ("   1    30   1     0     2     2     2   6.500E-01   6.500E-01\n"
               " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
        report = self._run_solve(dc, Path(self.td.name) / "short_time", sta=sta)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertTrue(any(reason.startswith("target step time not reached")
                            for reason in report["failure_reasons"]))

    # Success states (18-19) and claims (20-22).
    def test_clean_complete(self):
        dc = self._make_accepted("clean")
        report = self._run_solve(dc, Path(self.td.name) / "clean")
        self.assertEqual(report["status"], "SOLVE_COMPLETED")
        self.assertEqual(report["claims"]["solve"], "COMPLETED")
        self.assertTrue(report["completion"]["stdout_completed"])
        self.assertTrue(report["completion"]["sta_completed"])
        self.assertTrue(report["completion"]["target_time_reached"])
        self.assertEqual(report["completion"]["target_step_time"], 1.0)
        self.assertTrue((Path(self.td.name) / "clean/solve_report.json").is_file())

    def test_warning_only_complete(self):
        dc = self._make_accepted("warn")
        dat = ("***WARNING: adjacent secondary nodes (72,71) are on the opposite "
               "sides of double-sided main surface\n"
               "ANALYSIS COMPLETE TEXT\n")
        report = self._run_solve(dc, Path(self.td.name) / "warn", dat=dat)
        self.assertEqual(report["status"], "SOLVE_COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["claims"]["solve"], "COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["diagnostics"]["error_count"], 0)
        self.assertEqual(report["diagnostics"]["warning_count"], 1)
        self.assertIn("opposite", report["diagnostics"]["warnings"][0]["message"])

    def test_odb_recorded_but_extraction_not_run(self):
        dc = self._make_accepted("odbclaim")
        report = self._run_solve(dc, Path(self.td.name) / "odbclaim")
        self.assertIs(report["claims"]["odb_exists"], True)
        self.assertEqual(report["claims"]["odb_results_qa"], "NOT_RUN")
        self.assertEqual(report["claims"]["mechanics_qa"], "NOT_RUN")
        self.assertIsNotNone(report["artifacts"]["odb"]["sha256"])

    def test_dataset_eligible_false(self):
        dc = self._make_accepted("eligible")
        report = self._run_solve(dc, Path(self.td.name) / "eligible")
        self.assertIs(report["claims"]["dataset_eligible"], False)

    def test_m2_warnings_inherited_in_provenance(self):
        dc = self._make_accepted("inherit")
        report = self._run_solve(dc, Path(self.td.name) / "inherit")
        self.assertEqual(report["source_datacheck"]["status"],
                         "DATACHECK_COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["source_datacheck"]["warning_count"], 1)
        self.assertIn("CONTACT", report["source_datacheck"]["warning_categories"])

    def test_sta_parser_handles_real_three_time_columns(self):
        # Regression: real .sta rows carry up to THREE time columns
        # (total/step/inc-of) after 6-7 integer fields, and cutback rows with
        # 'U' markers must be skipped.
        sta = (" STEP  INC ATT SEVERE EQUIL TOTAL TOTAL STEP INC OF DOF IF\n"
               "   1    18   1     1     1     3     4  0.230      0.230      0.02000\n"
               "   1    25   1U   10     0    10  0.350      0.350      0.005000\n"
               "   1    26   1     3     1     4  0.363      0.363      0.007500\n"
               "   1    59   1     2     9    11  1.00       1.00       0.009117\n"
               " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
        path = Path(self.td.name) / "real.sta"
        path.write_text(sta, encoding="utf-8")
        info = pds.parse_sta(path)
        self.assertTrue(info["sta_exists"])
        self.assertTrue(info["sta_completion"])
        self.assertEqual(info["increment_count"], 3)  # cutback row 25U skipped
        self.assertEqual(info["last_step"], 1)
        self.assertEqual(info["last_increment"], 59)
        self.assertEqual(info["last_step_time"], 1.0)

    def test_other_job_completion_token_is_not_evidence(self):
        # M3.1 hardening: the stdout COMPLETED token must name THIS job.
        dc = self._make_accepted("other_job")

        def fake_other_job(argv, cwd, timeout_s, stdout_path, stderr_path):
            cwd = Path(cwd)
            (cwd / (self.JOB + ".dat")).write_text("ANALYSIS COMPLETE TEXT", encoding="utf-8")
            (cwd / (self.JOB + ".msg")).write_text("", encoding="utf-8")
            (cwd / (self.JOB + ".sta")).write_text(self._STA_OK, encoding="utf-8")
            (cwd / (self.JOB + ".odb")).write_bytes(b"fake complete odb")
            Path(stdout_path).write_text("Abaqus JOB some_other_job COMPLETED\n", encoding="utf-8")
            Path(stderr_path).write_text("", encoding="utf-8")
            return 0

        with mock.patch("pipeline.physical_solve._run_process_to_files", fake_other_job), \
                mock.patch("pipeline.physical_solve.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pds.run_solve(dc, Path(self.td.name) / "other_job",
                                   abaqus_command=self._fake_launcher(),
                                   policy_path=Path(self.td.name) / "no_policy.json")
        self.assertIs(report["completion"]["stdout_completed"], False)
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn("stdout completion token missing", report["failure_reasons"])

    def test_zero_byte_odb_fails(self):
        # M3.1 hardening: an existing but empty ODB is not completion evidence.
        dc = self._make_accepted("zero_odb")

        def fake_zero_odb(argv, cwd, timeout_s, stdout_path, stderr_path):
            cwd = Path(cwd)
            (cwd / (self.JOB + ".dat")).write_text("ANALYSIS COMPLETE TEXT", encoding="utf-8")
            (cwd / (self.JOB + ".msg")).write_text("", encoding="utf-8")
            (cwd / (self.JOB + ".sta")).write_text(self._STA_OK, encoding="utf-8")
            (cwd / (self.JOB + ".odb")).write_bytes(b"")
            Path(stdout_path).write_text("Abaqus JOB " + self.JOB + " COMPLETED\n", encoding="utf-8")
            Path(stderr_path).write_text("", encoding="utf-8")
            return 0

        with mock.patch("pipeline.physical_solve._run_process_to_files", fake_zero_odb), \
                mock.patch("pipeline.physical_solve.query_release",
                           return_value={"release": "Abaqus 2026 TEST", "return_code": 0}):
            report = pds.run_solve(dc, Path(self.td.name) / "zero_odb",
                                   abaqus_command=self._fake_launcher(),
                                   policy_path=Path(self.td.name) / "no_policy.json")
        self.assertEqual(report["status"], "SOLVE_FAILED")
        self.assertIn("zero-byte odb", report["failure_reasons"])

    def test_wall_time_recorded(self):
        dc = self._make_accepted("walltime")
        report = self._run_solve(dc, Path(self.td.name) / "walltime")
        self.assertIsInstance(report["execution"]["wall_time_s"], (int, float))
        self.assertGreaterEqual(report["execution"]["wall_time_s"], 0)

    # Attempt protection (22).
    def test_existing_attempt_not_overwritten(self):
        dc = self._make_accepted("existing")
        out = Path(self.td.name) / "existing_attempt"
        out.mkdir()
        (out / "sentinel.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(PipelineError) as caught:
            self._run_solve(dc, out)
        self.assertEqual(caught.exception.code, "OUTPUT_EXISTS")
        self.assertEqual((out / "sentinel.txt").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
