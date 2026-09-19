"""Solver choice: Standard Dynamic Implicit vs Explicit Dynamic on the same model.

The two decks must differ ONLY where the solver requires it (procedure, contact
slip tolerance, output sampling), and must share geometry, material, thickness,
PBC and the compression target.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.build import build                                       # noqa: E402
from pipeline.common import PipelineError, file_hash                   # noqa: E402
from sandbox import synthetic_bundle, write_synthetic_simulation       # noqa: E402

#: Blocks a solver switch must never touch (mesh, geometry, material, BCs).
SHARED_BLOCKS = ("physical.inp", "ingredients/shell_mesh.inc", "blocks/material_section.inc",
                 "blocks/rigid_platens.inc", "ingredients/lateral_pbc.inc",
                 "blocks/boundary_conditions.inc", "blocks/step_end.inc")
#: Blocks the solver switch is allowed to rewrite.
SOLVER_BLOCKS = ("blocks/contact.inc", "blocks/step_loading.inc", "blocks/outputs.inc")


class SolverDeckTests(unittest.TestCase):
    counter = 0

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.paths = synthetic_bundle(Path(self.folder.name) / "mesh")

    def deck(self, mutate=None, label=None):
        SolverDeckTests.counter += 1
        label = label or ("deck_%d" % SolverDeckTests.counter)
        simulation = write_synthetic_simulation(self.folder.name, mutate=mutate,
                                               name=("sim_%s.json" % label))
        out = Path(self.folder.name) / label
        document = build(*self.paths, simulation, out)
        return out, document

    def lines(self, deck, rel):
        return (Path(deck) / rel).read_text(encoding="utf-8").splitlines()

    def explicit(self, document):
        document["solver"]["type"] = "explicit_dynamic"

    def test_solver_type_is_switchable(self):
        standard, standard_doc = self.deck()
        explicit, explicit_doc = self.deck(self.explicit)
        self.assertEqual(standard_doc["solver"]["type"], "standard_dynamic_implicit")
        self.assertEqual(explicit_doc["solver"]["type"], "explicit_dynamic")
        self.assertIsNone(standard_doc["solver"]["mass_scaling"])
        self.assertEqual(explicit_doc["solver"]["mass_scaling"], {"enabled": False})

    def test_step_keywords_differ_where_the_solver_requires_it(self):
        standard, _ = self.deck()
        explicit, _ = self.deck(self.explicit)
        std_step = self.lines(standard, "blocks/step_loading.inc")
        exp_step = self.lines(explicit, "blocks/step_loading.inc")
        self.assertIn("*Step, name=Compression, nlgeom=YES, inc=10000", std_step)
        self.assertIn("*Dynamic, application=MODERATE DISSIPATION, initial=NO", std_step)
        self.assertIn("0.001, 1.0, 1e-08, 0.02", std_step)
        self.assertIn("*Step, name=Compression", exp_step)
        self.assertIn("*Dynamic, Explicit", exp_step)
        self.assertEqual(exp_step[exp_step.index("*Dynamic, Explicit") + 1], ", 1.0")
        self.assertNotIn("inc=10000", " ".join(exp_step))
        self.assertNotIn("MODERATE DISSIPATION", " ".join(exp_step))
        self.assertNotIn("initial=NO", " ".join(exp_step))

    def test_loading_and_amplitude_are_identical(self):
        standard, std_doc = self.deck()
        explicit, exp_doc = self.deck(self.explicit)
        for deck in (standard, explicit):
            lines = self.lines(deck, "blocks/step_loading.inc")
            self.assertIn("*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP", lines)
            self.assertIn("RP_TOP, 3, 3, -0.2", lines)
        self.assertEqual(std_doc["model"]["target_displacement_mm"],
                         exp_doc["model"]["target_displacement_mm"])
        self.assertEqual(std_doc["model"]["thickness_mm"], exp_doc["model"]["thickness_mm"])

    def test_shared_blocks_are_byte_identical(self):
        standard, _ = self.deck()
        explicit, _ = self.deck(self.explicit)
        for rel in SHARED_BLOCKS:
            self.assertEqual(file_hash(Path(standard) / rel), file_hash(Path(explicit) / rel),
                             rel)
        for rel in SOLVER_BLOCKS:
            self.assertNotEqual(file_hash(Path(standard) / rel),
                                file_hash(Path(explicit) / rel), rel)

    def test_slip_tolerance_is_standard_only_but_friction_is_in_both(self):
        standard, _ = self.deck()
        explicit, explicit_doc = self.deck(self.explicit)
        self.assertIn("*Friction, slip tolerance=0.005",
                      self.lines(standard, "blocks/contact.inc"))
        exp_contact = self.lines(explicit, "blocks/contact.inc")
        self.assertIn("*Friction", exp_contact)
        self.assertNotIn("slip tolerance", " ".join(exp_contact))
        self.assertEqual(exp_contact[exp_contact.index("*Friction") + 1], "0.6,")
        self.assertNotIn("slip_tolerance", json.dumps(explicit_doc["simulation"]["contact"]))

    def test_output_keywords_follow_the_solver(self):
        standard, _ = self.deck()
        explicit, _ = self.deck(self.explicit)
        std_out = self.lines(standard, "blocks/outputs.inc")
        exp_out = self.lines(explicit, "blocks/outputs.inc")
        self.assertIn("*Restart, write, frequency=0", std_out)
        self.assertIn("*Output, field, variable=PRESELECT, frequency=50", std_out)
        self.assertIn("*Output, history, frequency=1", std_out)
        self.assertIn("*Output, history, variable=PRESELECT, frequency=10", std_out)
        self.assertIn("*Output, field, variable=PRESELECT, number interval=100, time marks=NO",
                      exp_out)
        self.assertIn("*Output, history, time interval=0.001", exp_out)
        self.assertFalse([line for line in exp_out if line.startswith("*Restart")])
        self.assertFalse([line for line in exp_out if "variable=PRESELECT, frequency" in line])
        # Same requested variables/regions in both solvers.
        for line in ("*Energy Output", "*Node Output, nset=RP_TOP", "RF3, U3",
                     "ALLAE, ALLIE, ALLKE, ALLPD, ALLWK, ETOTAL"):
            self.assertIn(line, std_out)
            self.assertIn(line, exp_out)

    def test_output_frequencies_come_from_the_solver_block(self):
        explicit, _ = self.deck(lambda document: (
            self.explicit(document),
            document["solver"]["explicit_dynamic"].update(field_number_interval=25,
                                                          history_time_interval_s=0.005,
                                                          field_time_marks=True)))
        lines = self.lines(explicit, "blocks/outputs.inc")
        self.assertIn("*Output, field, variable=PRESELECT, number interval=25, time marks=YES",
                      lines)
        self.assertIn("*Output, history, time interval=0.005", lines)

    def test_mass_scaling_is_off_by_default_and_explicit_when_enabled(self):
        off, _ = self.deck(self.explicit)
        self.assertFalse([line for line in self.lines(off, "blocks/step_loading.inc")
                          if "Mass Scaling" in line])
        on, document = self.deck(lambda doc: (
            self.explicit(doc),
            doc["solver"]["explicit_dynamic"].update(
                mass_scaling={"enabled": True, "factor": 100.0})))
        step_lines = self.lines(on, "blocks/step_loading.inc")
        self.assertIn("*Fixed Mass Scaling, factor=100.0", step_lines)
        # The keyword is step-level: it must sit INSIDE the Explicit step.
        order = [step_lines.index(marker) for marker in
                 ("*Step, name=Compression", "*Dynamic, Explicit",
                  "*Fixed Mass Scaling, factor=100.0",
                  "*Boundary, amplitude=AMP_COMPRESSION")]
        self.assertEqual(order, sorted(order),
                         "*Fixed Mass Scaling must follow *Dynamic, Explicit "
                         "and precede *Boundary")
        self.assertEqual(document["solver"]["mass_scaling"],
                         {"enabled": True, "factor": 100.0})
        with self.assertRaises(PipelineError) as caught:
            self.deck(lambda doc: (
                self.explicit(doc),
                doc["solver"]["explicit_dynamic"].update(mass_scaling={"enabled": True})))
        self.assertEqual(caught.exception.code, "CONFIG_INVALID")

    def test_standard_deck_has_no_mass_scaling(self):
        standard, _ = self.deck()
        self.assertFalse([line for line in self.lines(standard, "blocks/step_loading.inc")
                          if "Mass Scaling" in line],
                         "Standard decks must never carry a mass scaling keyword")

    def test_self_contact_switch_applies_to_both_solvers(self):
        for mutate in (lambda doc: doc["contact"].update(self_contact=False),
                       lambda doc: (self.explicit(doc),
                                    doc["contact"].update(self_contact=False))):
            with self.subTest(mutate=mutate):
                deck, _ = self.deck(mutate)
                lines = self.lines(deck, "blocks/contact.inc")
                self.assertIn("*Surface, name=SHELL_FACES, type=ELEMENT", lines)
                self.assertIn("SHELL_FACES, PLATE_FACES", lines)
                self.assertNotIn("*Contact Inclusions, ALL EXTERIOR", lines)

    def test_time_period_comes_from_the_active_solver_block(self):
        explicit, document = self.deck(lambda doc: (
            self.explicit(doc),
            doc["solver"]["explicit_dynamic"].update(time_period_s=2.5)))
        self.assertEqual(document["solver"]["time_period_s"], 2.5)
        self.assertIn("0.0, 0.0, 2.5, 1.0", self.lines(explicit, "blocks/step_loading.inc"))
        self.assertIn(", 2.5", self.lines(explicit, "blocks/step_loading.inc"))


if __name__ == "__main__":
    unittest.main()
