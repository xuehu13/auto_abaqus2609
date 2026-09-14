"""Boundary checks for task wrappers, without meshing, compiling or Abaqus."""
import argparse
import os
from pathlib import Path
import tempfile
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

import pixi_tasks as tasks
sys.path.insert(0, str(tasks.CODE))
from pipeline.mesher_adapter import prepare, external_environment, cgal_artifact, pixi_prefix
from pipeline.common import PipelineError


class TaskBoundaryTests(unittest.TestCase):
    def test_geo_argv_runs_correct_python_from_path_with_spaces(self):
        with tempfile.TemporaryDirectory(prefix="pixi argv space ") as td:
            script = Path(td) / "probe with spaces.py"
            script.write_text("import sys; print(sys.version.split()[0])", encoding="utf-8")
            result = subprocess.run(pixi_prefix("geo") + ["python", "-B", str(script)],
                                    cwd=td, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), "3.10.21")

    def test_plan_has_no_legacy_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            result = prepare(tasks.VENDOR, tasks.CODE / "config/cases/fig1.json",
                             tasks.CODE / "config/environment.example.json", Path(td) / "plan")
            self.assertEqual(result["unconfigured_stages"], ["CGAL", "MESH_DATACHECK"])
            argv = result["commands"][0]["argv"]
            self.assertEqual(argv[argv.index("--environment") + 1], "geo")
            self.assertIn("--locked", argv)
            self.assertNotIn("geo_python", result["environment"])

    def test_old_schema_fails_instead_of_using_old_python(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "environment.json"
            p.write_text(json.dumps({"schema_version": 1, "geo_python": "old-python"}), encoding="utf-8")
            with self.assertRaises(PipelineError):
                external_environment(p)

    def test_cgal_artifact_rejects_mismatched_lock(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            (p / "build").mkdir()
            exe = p / "build/periodic_surface_mesher.exe"
            exe.write_bytes(b"test artifact, never executed")
            tasks.write_json(p / "build_result.json", {"status": "BUILT_NOT_MESH_VALIDATED", "sha256": tasks.sha(exe)})
            tasks.write_json(p / "inputs.json", {"pixi_lock_sha256": "wrong"})
            with self.assertRaises(PipelineError):
                cgal_artifact(p)

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


if __name__ == "__main__":
    unittest.main()
