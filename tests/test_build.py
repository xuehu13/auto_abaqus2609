"""Build side: config-driven keyword rendering, config validation, static checks."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.build import (DECK_ROOT, INCLUDE_ORDER, build, include_paths,  # noqa: E402
                            static_checks)
from pipeline.common import PipelineError, file_hash                            # noqa: E402
from sandbox import write_synthetic_simulation, synthetic_bundle                # noqa: E402


class BuildSandbox(unittest.TestCase):
    """A built synthetic attempt that individual tests may mutate."""

    counter = 0

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.paths = synthetic_bundle(Path(self.folder.name) / "mesh")

    def build_attempt(self, mutate=None, name=None):
        BuildSandbox.counter += 1
        name = name or ("attempt_%d" % BuildSandbox.counter)
        simulation = write_synthetic_simulation(
            self.folder.name, mutate=mutate, name=("sim_%s.json" % name))
        out = Path(self.folder.name) / name
        document = build(*self.paths, simulation, out)
        return out, document

    def block(self, attempt, rel):
        return (Path(attempt) / rel).read_text(encoding="utf-8")


class ConfigValidationTests(BuildSandbox):
    def _reject(self, mutate, code="CONFIG_INVALID", fragment=None):
        with self.assertRaises(PipelineError) as caught:
            self.build_attempt(mutate)
        self.assertEqual(caught.exception.code, code)
        if fragment:
            self.assertIn(fragment, str(caught.exception))

    def test_unknown_keys_are_rejected(self):
        self._reject(lambda doc: doc.update(mystery=1), fragment="unknown keys")
        self._reject(lambda doc: doc["contact"].update(typo=1), fragment="simulation.contact")
        self._reject(lambda doc: doc["solver"].update(extra=1), fragment="simulation.solver")
        self._reject(lambda doc: doc["solver"]["standard_dynamic_implicit"].update(extra=1),
                     fragment="solver.standard_dynamic_implicit")
        self._reject(lambda doc: doc["solver"]["explicit_dynamic"].update(extra=1),
                     fragment="solver.explicit_dynamic")

    def test_missing_keys_are_rejected(self):
        self._reject(lambda doc: doc.pop("output"), fragment="missing keys")
        self._reject(lambda doc: doc["solver"].pop("explicit_dynamic"), fragment="missing keys")

    def test_non_finite_and_illegal_numbers_are_rejected(self):
        standard = lambda doc: doc["solver"]["standard_dynamic_implicit"]      # noqa: E731
        for mutate in (lambda doc: doc["material"].update(youngs_modulus_MPa=float("nan")),
                       lambda doc: doc["material"].update(density_tonne_mm3=0.0),
                       lambda doc: doc["contact"].update(friction=-1.0),
                       lambda doc: standard(doc).update(slip_tolerance=0.0),
                       lambda doc: standard(doc).update(maximum_increments=0),
                       lambda doc: standard(doc).update(time_period_s=0.0),
                       lambda doc: standard(doc).update(field_frequency=0),
                       lambda doc: standard(doc).update(preselect_history_frequency=-1),
                       lambda doc: doc["shell"].update(integration_points=2.5),
                       lambda doc: doc["platen"].update(width_factor="wide"),
                       lambda doc: standard(doc).update(nlgeom="yes")):
            with self.subTest(mutate=mutate):
                self._reject(mutate)

    def test_increment_ordering_is_enforced(self):
        standard = lambda doc: doc["solver"]["standard_dynamic_implicit"]      # noqa: E731
        self._reject(lambda doc: standard(doc).update(initial_increment_s=0.5,
                                                      maximum_increment_s=0.02))

    def test_unimplemented_values_are_explicit(self):
        self._reject(lambda doc: doc["solver"].update(type="dynamic_implicit"), "NOT_IMPLEMENTED")
        self._reject(lambda doc: doc["loading"].update(amplitude="tabular"), "NOT_IMPLEMENTED")
        self._reject(lambda doc: doc["output"].update(requests=[
            {"kind": "element", "variables": ["S"]}]), "NOT_IMPLEMENTED")

    def test_element_types_must_match_the_mesh_topology(self):
        self._reject(lambda doc: doc["shell"].update(element_type="S4R"),
                     fragment="3-node triangles")
        self._reject(lambda doc: doc["platen"].update(element_type="R3D3"),
                     fragment="4-node quad grid")
        self._reject(lambda doc: doc["shell"].update(element_type="S3R, elset=HACK"))

    def test_output_request_regions_must_exist(self):
        self._reject(lambda doc: doc["output"].update(requests=[
            {"kind": "node", "region": "RP_TOPX", "variables": ["U3"]}]))
        self._reject(lambda doc: doc["output"].update(requests=[
            {"kind": "energy", "region": "RP_TOP", "variables": ["ALLIE"]}]))
        self._reject(lambda doc: doc["output"].update(requests=[
            {"kind": "node", "region": "RP_TOP", "variables": []}]))


class RenderingTests(BuildSandbox):
    """Every research parameter in the config must really change the rendered deck."""

    def _lines(self, attempt, rel):
        return self.block(attempt, rel).splitlines()

    def _thickness_line(self, document):
        return repr(float(document["model"]["thickness_mm"]))

    def test_baseline_deck_uses_the_config_values(self):
        attempt, document = self.build_attempt()
        self.assertEqual(document["status"], "BUILT")
        mesh = self._lines(attempt, "ingredients/shell_mesh.inc")
        self.assertIn("*Element, type=S3R, elset=SHELL_ALL", mesh)
        material = self._lines(attempt, "blocks/material_section.inc")
        self.assertIn("*Material, name=MAT_SHELL", material)
        self.assertIn(" 1.1e-09,", material)
        self.assertIn("484.0, 0.4", material)
        self.assertIn("8.0, 0.0", material)
        self.assertTrue(any(line.endswith(", 5") for line in material), material[-3:])
        contact = self._lines(attempt, "blocks/contact.inc")
        self.assertIn("*Surface Behavior, pressure-overclosure=HARD", contact)
        self.assertIn("*Friction, slip tolerance=0.005", contact)
        self.assertIn("0.6,", contact)
        step = self._lines(attempt, "blocks/step_loading.inc")
        self.assertIn("*Step, name=Compression, nlgeom=YES, inc=10000", step)
        self.assertIn("*Dynamic, application=MODERATE DISSIPATION, initial=NO", step)
        self.assertIn("0.001, 1.0, 1e-08, 0.02", step)
        self.assertIn("RP_TOP, 3, 3, -0.2", step)
        outputs = self._lines(attempt, "blocks/outputs.inc")
        self.assertEqual(outputs[0], "*Restart, write, frequency=0")
        self.assertIn("*Output, field, variable=PRESELECT, frequency=50", outputs)
        self.assertIn("*Energy Output", outputs)
        self.assertIn("*Node Output, nset=RP_Y_CTRL", outputs)
        self.assertEqual(outputs[-1], "*Output, history, variable=PRESELECT, frequency=10")

    def test_element_types_come_from_the_config(self):
        """Only 3-node shell / 4-node rigid types fit this mesh, so S3 is the test case."""
        attempt, _ = self.build_attempt(
            lambda doc: doc["shell"].update(element_type="S3"))
        self.assertIn("*Element, type=S3, elset=SHELL_ALL",
                      self._lines(attempt, "ingredients/shell_mesh.inc"))
        rigid = self._lines(attempt, "blocks/rigid_platens.inc")
        self.assertIn("*Element, type=R3D4, elset=PLATE_BOTTOM", rigid)
        self.assertIn("*Element, type=R3D4, elset=PLATE_TOP", rigid)

    def test_material_numbers_and_table_come_from_the_config(self):
        attempt, _ = self.build_attempt(lambda doc: doc["material"].update(
            density_tonne_mm3=2.5e-09, youngs_modulus_MPa=1000.0, poisson_ratio=0.25,
            plastic_table=[[5.0, 0.0], [7.0, 0.5]]))
        material = self._lines(attempt, "blocks/material_section.inc")
        self.assertIn(" 2.5e-09,", material)
        self.assertIn("1000.0, 0.25", material)
        self.assertIn("5.0, 0.0", material)
        self.assertIn("7.0, 0.5", material)
        self.assertNotIn("8.0, 0.0", material)

    def test_shell_section_and_relative_density_change_the_thickness(self):
        base, base_doc = self.build_attempt()
        thick, thick_doc = self.build_attempt(
            lambda doc: doc["shell"].update(target_relative_density=0.2, integration_points=3))
        self.assertAlmostEqual(thick_doc["model"]["thickness_mm"],
                               2 * base_doc["model"]["thickness_mm"])
        self.assertIn(self._thickness_line(thick_doc) + ", 3",
                      self._lines(thick, "blocks/material_section.inc"))
        self.assertNotIn(self._thickness_line(base_doc),
                         self._lines(thick, "blocks/material_section.inc"))

    def test_platen_geometry_comes_from_the_config(self):
        base, base_doc = self.build_attempt()
        bigger, doc = self.build_attempt(
            lambda d: d["platen"].update(width_factor=2.0, mesh_size_mm=2.0))
        self.assertNotEqual(self._lines(base, "blocks/rigid_platens.inc"),
                            self._lines(bigger, "blocks/rigid_platens.inc"))
        self.assertEqual(base_doc["static_checks"]["region_integrity"]["status"], "PASS")
        # width_factor 2.0 with mesh_size 2.0 gives exactly one interval per platen:
        # 4 nodes per platen, still starting above the 8 shell nodes.
        self.assertEqual(doc["model"]["labels"]["first_plate_node"], 13)
        self.assertIn("13, 16, 1", self._lines(bigger, "blocks/rigid_platens.inc"))

    def test_fractional_platen_intervals_are_refused(self):
        with self.assertRaises(PipelineError) as caught:
            self.build_attempt(lambda doc: doc["platen"].update(width_factor=1.7,
                                                                mesh_size_mm=1.0))
        self.assertEqual(caught.exception.code, "NOT_IMPLEMENTED")

    def test_contact_keywords_come_from_the_config(self):
        attempt, _ = self.build_attempt(lambda doc: (
            doc["contact"].update(normal="soft", allow_separation=False, friction=0.2),
            doc["solver"]["standard_dynamic_implicit"].update(slip_tolerance=0.01)))
        contact = self._lines(attempt, "blocks/contact.inc")
        self.assertIn("*Surface Behavior, pressure-overclosure=SOFT, no separation", contact)
        self.assertIn("*Friction, slip tolerance=0.01", contact)
        self.assertIn("0.2,", contact)

    def test_self_contact_can_be_switched_off(self):
        on, _ = self.build_attempt()
        off, _ = self.build_attempt(lambda doc: doc["contact"].update(self_contact=False))
        self.assertNotIn("*Contact Exclusions", self._lines(on, "blocks/contact.inc"))
        lines = self._lines(off, "blocks/contact.inc")
        self.assertIn("*Surface, name=SHELL_FACES, type=ELEMENT", lines)
        self.assertIn("*Surface, name=PLATE_FACES, type=ELEMENT", lines)
        self.assertIn("*Contact Inclusions", lines)
        self.assertIn("SHELL_FACES, PLATE_FACES", lines)
        self.assertNotIn("*Contact Inclusions, ALL EXTERIOR", lines)
        # The two surfaces must cover the shell and both plates.
        start = lines.index("*Surface, name=SHELL_FACES, type=ELEMENT") + 1
        self.assertEqual(lines[start], "SHELL_ALL,")
        start = lines.index("*Surface, name=PLATE_FACES, type=ELEMENT") + 1
        self.assertEqual(lines[start:start + 2], ["PLATE_BOTTOM,", "PLATE_TOP,"])

    def test_amplitude_shapes(self):
        smooth, _ = self.build_attempt()
        ramp, _ = self.build_attempt(lambda doc: doc["loading"].update(amplitude="ramp"))
        self.assertIn("*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP",
                      self._lines(smooth, "blocks/step_loading.inc"))
        ramp_lines = self._lines(ramp, "blocks/step_loading.inc")
        self.assertEqual(ramp_lines[0], "*Amplitude, name=AMP_COMPRESSION")
        self.assertEqual(ramp_lines[1], "0.0, 0.0, 1.0, 1.0")

    def test_loading_target_comes_from_the_config(self):
        attempt, document = self.build_attempt(
            lambda doc: doc["loading"].update(target_compression_strain=0.35))
        step = self._lines(attempt, "blocks/step_loading.inc")
        self.assertIn("RP_TOP, 3, 3, -0.35", step)
        self.assertIn("Compression: eps=0.35, U3=-0.35 mm, T=1 s", step)
        self.assertAlmostEqual(document["model"]["target_displacement_mm"], -0.35)

    def test_standard_step_keywords_come_from_the_config(self):
        attempt, _ = self.build_attempt(lambda doc: doc["solver"][
            "standard_dynamic_implicit"].update(
                nlgeom=False, application="quasi_static", initial_acceleration=True,
                initial_increment_s=0.01, minimum_increment_s=1e-06, maximum_increment_s=0.1,
                maximum_increments=42, time_period_s=2.5))
        step = self._lines(attempt, "blocks/step_loading.inc")
        self.assertIn("*Step, name=Compression, nlgeom=NO, inc=42", step)
        self.assertIn("*Dynamic, application=QUASI STATIC, initial=YES", step)
        self.assertIn("0.01, 2.5, 1e-06, 0.1", step)
        self.assertIn("0.0, 0.0, 2.5, 1.0", step)

    def test_output_requests_come_from_the_config(self):
        attempt, _ = self.build_attempt(lambda doc: (
            doc["solver"]["standard_dynamic_implicit"].update(
                restart_frequency=5, field_frequency=7, history_frequency=3,
                preselect_history_frequency=0),
            doc["output"].update(requests=[
                {"kind": "node", "region": "RP_BOTTOM", "variables": ["RF1", "U1"]}])))
        self.assertEqual(self._lines(attempt, "blocks/outputs.inc"),
                         ["*Restart, write, frequency=5",
                          "*Output, field, variable=PRESELECT, frequency=7",
                          "*Output, history, frequency=3",
                          "*Node Output, nset=RP_BOTTOM",
                          "RF1, U1"])

    def test_report_records_the_deck_and_the_config_hash(self):
        attempt, document = self.build_attempt(name="report")
        root = file_hash(Path(attempt) / "physical.inp")
        self.assertEqual(document["provenance"]["physical_inp_sha256"], root)
        self.assertEqual(document["deck"]["files"], {
            rel: file_hash(Path(attempt) / rel) for rel in (DECK_ROOT,) + INCLUDE_ORDER})
        self.assertEqual(document["deck"]["provenance"],
                         {"ingredients/pbc_map.json":
                          file_hash(Path(attempt) / "ingredients/pbc_map.json")})
        self.assertEqual(document["provenance"]["config_sha256"],
                         file_hash(Path(self.folder.name) / "sim_report.json"))
        self.assertEqual(document["claims"]["datacheck"], "NOT_RUN")
        self.assertEqual(document["claims"]["dataset_eligible"], False)
        self.assertIn("git_commit", document["provenance"])


class StaticCheckTests(BuildSandbox):
    """The static check must catch a deck that stopped matching its own report."""

    def _checks(self, attempt, report):
        return static_checks(Path(attempt), report["deck"]["files"])

    def _status(self, checks):
        return {name: result["status"] for name, result in checks.items()}

    def test_clean_attempt_passes_every_check(self):
        attempt, document = self.build_attempt()
        status = self._status(self._checks(attempt, document))
        self.assertEqual(status, {"deck_files_present": "PASS", "deck_sha256": "PASS",
                                  "include_graph": "PASS", "region_integrity": "PASS",
                                  "step_structure": "PASS"})

    def test_changed_include_is_detected(self):
        attempt, document = self.build_attempt()
        path = Path(attempt) / "blocks/contact.inc"
        path.write_text(path.read_text(encoding="utf-8") + "** tampered\n", encoding="utf-8")
        checks = self._checks(attempt, document)
        self.assertEqual(self._status(checks)["deck_sha256"], "FAILED")
        self.assertIn("blocks/contact.inc", str(checks["deck_sha256"]["details"]))

    def test_missing_include_is_detected(self):
        attempt, document = self.build_attempt()
        (Path(attempt) / "blocks/step_end.inc").unlink()
        status = self._status(self._checks(attempt, document))
        self.assertEqual(status["deck_files_present"], "FAILED")
        self.assertEqual(status["include_graph"], "FAILED")

    def test_changed_include_sequence_is_detected(self):
        attempt, document = self.build_attempt()
        deck = Path(attempt) / "physical.inp"
        deck.write_text(deck.read_text(encoding="utf-8").replace(
            "*Include, input=blocks/contact.inc\n", ""), encoding="utf-8")
        status = self._status(self._checks(attempt, document))
        self.assertEqual(status["include_graph"], "FAILED")

    def test_unsafe_include_path_is_detected(self):
        attempt, document = self.build_attempt()
        deck = Path(attempt) / "physical.inp"
        deck.write_text(deck.read_text(encoding="utf-8").replace(
            "*Include, input=blocks/contact.inc", "*Include, input=../outside.inc"),
            encoding="utf-8")
        checks = self._checks(attempt, document)
        self.assertEqual(self._status(checks)["include_graph"], "FAILED")
        self.assertIn("unsafe include path", str(checks["include_graph"]["details"]))

    def test_missing_region_is_detected(self):
        attempt, document = self.build_attempt()
        rigid = Path(attempt) / "blocks/rigid_platens.inc"
        rigid.write_text(rigid.read_text(encoding="utf-8").replace(
            "*Nset, nset=RP_TOP\n", "*Nset, nset=RP_TOPP\n"), encoding="utf-8")
        checks = self._checks(attempt, document)
        self.assertEqual(self._status(checks)["region_integrity"], "FAILED")
        self.assertIn("RP_TOP", str(checks["region_integrity"]["details"]))

    def test_output_outside_the_step_is_detected(self):
        attempt, document = self.build_attempt()
        deck = Path(attempt) / "physical.inp"
        text = deck.read_text(encoding="utf-8")
        deck.write_text(text.replace(
            "*Include, input=blocks/outputs.inc\n*Include, input=blocks/step_end.inc",
            "*Include, input=blocks/step_end.inc\n*Include, input=blocks/outputs.inc"),
            encoding="utf-8")
        checks = self._checks(attempt, document)
        self.assertEqual(self._status(checks)["step_structure"], "FAILED")
        self.assertIn("*output in blocks/outputs.inc is not inside the step",
                      str(checks["step_structure"]["details"]))
        self.assertEqual(self._status(checks)["include_graph"], "FAILED")

    def test_include_paths_reads_the_deck_graph(self):
        attempt, _ = self.build_attempt()
        self.assertEqual(include_paths((Path(attempt) / "physical.inp").read_text()),
                         list(INCLUDE_ORDER))

    def test_failed_mesh_keeps_the_attempt_as_evidence(self):
        """A mesh that fails its contract in build() leaves the attempt on disk."""
        BuildSandbox.counter += 1
        name = "attempt_%d" % BuildSandbox.counter
        simulation = write_synthetic_simulation(self.folder.name, name="sim_%s.json" % name)
        out = Path(self.folder.name) / name
        broken = Path(self.folder.name) / "broken"
        broken.mkdir()
        from sandbox import write_bundle
        paths = write_bundle(broken / "m.npz", broken / "m.json", broken / "m.csv",
                             report_overrides={"surface_area_mm2": 3.0})
        with self.assertRaises(PipelineError):
            build(*paths, simulation, out)
        self.assertTrue(out.is_dir(), "the failed attempt must be kept for inspection")
        self.assertFalse((out / "physical.inp").exists())
        self.assertFalse((out / "build_report.json").exists())


if __name__ == "__main__":
    unittest.main()
