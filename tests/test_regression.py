"""Fig.1 deck regression: the rebuilt deck must equal the frozen SHA set."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline.build import build                                    # noqa: E402
from pipeline.common import PipelineError, file_hash                # noqa: E402
from sandbox import FINGERPRINTS, SIMULATION, fig1_bundle           # noqa: E402


class Fig1DeckRegressionTests(unittest.TestCase):
    """Rebuild the frozen deck from tracked config and compare byte for byte."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def _bundle(self):
        bundle = fig1_bundle()
        if bundle is None:
            self.skipTest("local Fig.1 mesh bundle (git-ignored work/) is unavailable")
        return bundle

    def test_rebuild_reproduces_the_frozen_deck(self):
        npz, report, pairs = self._bundle()
        out = Path(self.folder.name) / "rebuild"
        document = build(npz, report, pairs, SIMULATION, out)
        self.assertEqual(document["status"], "BUILT")
        self.assertEqual(document["static_validation"], "PASS")
        for rel, expected in sorted(FINGERPRINTS["deck_sha256"].items()):
            self.assertEqual(file_hash(out / rel), expected, rel)
        self.assertEqual(len(FINGERPRINTS["deck_sha256"]), 10)
        # The report must record exactly the bytes that were compared.
        self.assertEqual(document["deck"]["files"], FINGERPRINTS["deck_sha256"])
        self.assertEqual(document["provenance"]["physical_inp_sha256"],
                         FINGERPRINTS["deck_sha256"]["physical.inp"])

    def test_rebuild_is_deterministic(self):
        """Two rebuilds of identical inputs must be byte-identical (no timestamps)."""
        npz, report, pairs = self._bundle()
        for name in ("a", "b"):
            build(npz, report, pairs, SIMULATION, Path(self.folder.name) / name)
        for rel in sorted(FINGERPRINTS["deck_sha256"]):
            self.assertEqual(file_hash(Path(self.folder.name) / "a" / rel),
                             file_hash(Path(self.folder.name) / "b" / rel), rel)

    def test_attempt_is_never_overwritten(self):
        npz, report, pairs = self._bundle()
        out = Path(self.folder.name) / "once"
        build(npz, report, pairs, SIMULATION, out)
        with self.assertRaises(PipelineError) as caught:
            build(npz, report, pairs, SIMULATION, out)
        self.assertEqual(caught.exception.code, "OUTPUT_EXISTS")

    def test_model_facts_match_the_frozen_case(self):
        npz, report, pairs = self._bundle()
        out = Path(self.folder.name) / "facts"
        document = build(npz, report, pairs, SIMULATION, out)
        self.assertEqual(document["case_id"], "fig1")
        self.assertEqual(document["model"]["shell_nodes"], 9483)
        self.assertEqual(document["model"]["shell_elements"], 18164)
        self.assertEqual(document["model"]["equation_count"], 1722)
        self.assertAlmostEqual(document["model"]["target_displacement_mm"], -2.0, places=12)
        self.assertEqual(document["model"]["L_mm"], 10.0)
        checks = {name: result["status"] for name, result in document["static_checks"].items()}
        self.assertEqual(set(checks.values()), {"PASS"}, checks)

    def test_local_frozen_evidence_still_matches(self):
        """When the git-ignored frozen attempt is present, it must match the fixture."""
        attempt = ROOT / FINGERPRINTS["source_attempt"]
        if not (attempt / "physical.inp").is_file():
            self.skipTest("local frozen Fig.1 attempt (git-ignored work/) is unavailable")
        for rel, expected in sorted(FINGERPRINTS["deck_sha256"].items()):
            self.assertEqual(file_hash(attempt / rel), expected, rel)

    def test_fixture_holds_no_machine_private_path(self):
        raw = (Path(ROOT) / "tests/fixtures/fig1_20pct_regression/deck_sha256.json").read_text(
            encoding="utf-8")
        for token in ("C:\\", "F:\\", "E:\\", "Users\\", "xuehu"):
            self.assertNotIn(token, raw, token)

    def test_fixture_records_the_expected_completion(self):
        completion = FINGERPRINTS["expected_completion"]
        self.assertEqual(completion["status"], "SOLVE_COMPLETED_WITH_WARNINGS")
        self.assertEqual(completion["error_count"], 0)
        self.assertEqual(completion["last_step_time"], completion["target_step_time"])
        self.assertIn("artifact identity only", FINGERPRINTS["odb_artifact"]["note"])

    def test_fixture_json_is_loadable(self):
        self.assertEqual(json.loads(json.dumps(FINGERPRINTS))["case"], "fig1")


if __name__ == "__main__":
    unittest.main()
