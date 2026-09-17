"""Boundary checks for task wrappers, without meshing, compiling or Abaqus."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pixi_tasks as tasks
sys.path.insert(0, str(tasks.CODE))
from pipeline.common import PipelineError  # noqa: E402,F401  (imported by callers below)


class TaskBoundaryTests(unittest.TestCase):
    def test_attempt_rejects_protected_and_nested_directories(self):
        for path in (tasks.ROOT / "baseline_test/new", tasks.VENDOR / "cases/new",
                     tasks.CODE / "work/takeover_20260913_01/new"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                tasks.new_attempt(path)

    def test_attempt_never_overwrites(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with patch.object(tasks, "ROOT", root):
                path = tasks.new_attempt(root / "work/attempt")
                (path / "evidence").write_text("keep", encoding="utf-8")
                with self.assertRaises(FileExistsError):
                    tasks.new_attempt(path)
                self.assertEqual((path / "evidence").read_text(), "keep")

    def test_wrong_environment_fails_before_mesh_work(self):
        with patch.dict(os.environ, {"PIXI_ENVIRONMENT_NAME": "default"}):
            with self.assertRaises(RuntimeError):
                tasks.mesh(argparse.Namespace(stage="pre"))

    def test_record_is_write_once(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "record.json"
            tasks.write_json(p, {"status": "FAILED"})
            with self.assertRaises(FileExistsError):
                tasks.write_json(p, {"status": "PASS"})
            self.assertIn("FAILED", p.read_text())

    def test_frozen_vendor_matches_its_manifest(self):
        tasks.vendor_hashes()


if __name__ == "__main__":
    unittest.main()
