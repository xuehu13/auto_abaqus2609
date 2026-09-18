"""Abaqus side: runtime config, launcher gate, staging, Data Check and solve.

No real Abaqus is invoked. The launcher itself is a tiny generated .bat file (so
launcher resolution, the release gate and the real subprocess path are exercised),
while the stage runs patch ``_run_launcher`` to write the files a real job would
produce.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from pipeline import abaqus                                              # noqa: E402
from pipeline.abaqus import (BLOCKED_ENV_VARS, abaqus_env, abaqus_run_argv,  # noqa: E402
                             derive_job_name, enforce_release_gate, load_runtime,
                             parse_release_year, resolve_job_name, resolve_launcher,
                             resolve_runtime, run_datacheck, run_solve, verify_deck)
from pipeline.build import build                                          # noqa: E402
from pipeline.common import PipelineError, file_hash                      # noqa: E402
from sandbox import write_synthetic_simulation, synthetic_bundle          # noqa: E402

#: A real .bat launcher file so resolution, the release gate and the real
#: subprocess path are exercised. cmd.exe splits ``information=release`` into two
#: arguments, so the fake matches on the first token only.
FAKE_LAUNCHER = ("@echo off\r\n"
                 "if \"%~1\"==\"information\" echo Abaqus 2026\r\n")


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "runtime.json"

    def _write(self, document):
        self.path.write_text(json.dumps(document), encoding="utf-8")
        return load_runtime(self.path)

    def test_defaults_are_conservative(self):
        values = resolve_runtime("datacheck", {"abaqus": {}})
        self.assertEqual(values, {"cpus": 1, "standard_parallel": "solver", "mp_mode": None,
                                  "timeout_s": 3600, "source": "default"})
        self.assertEqual(resolve_runtime("solve", {"abaqus": {}})["timeout_s"], 14400)

    def test_runtime_file_overrides_defaults_per_stage(self):
        runtime = self._write({"abaqus": {"release_required": "2026"},
                               "solve": {"cpus": 8, "timeout_s": 60}})
        solve = resolve_runtime("solve", runtime)
        self.assertEqual((solve["cpus"], solve["timeout_s"], solve["source"]),
                         (8, 60, "runtime_file"))
        self.assertEqual(resolve_runtime("datacheck", runtime)["cpus"], 1)
        self.assertEqual(runtime["abaqus"]["release_required"], "2026")

    def test_cli_wins(self):
        runtime = self._write({"datacheck": {"cpus": 2}})
        values = resolve_runtime("datacheck", runtime, cpus=5, standard_parallel="all",
                                 timeout_s=90)
        self.assertEqual((values["cpus"], values["standard_parallel"], values["timeout_s"],
                          values["source"]), (5, "all", 90, "cli"))

    def test_unknown_keys_and_bad_values_are_rejected(self):
        for document in ({"mystery": {}}, {"abaqus": {"launcher": "x", "typo": 1}},
                         {"datacheck": {"cpus": 1, "unknown": 1}}):
            with self.subTest(document=document):
                with self.assertRaises(PipelineError):
                    self._write(document)
        for stage, values in (("datacheck", {"cpus": 0}), ("datacheck", {"cpus": True}),
                              ("datacheck", {"standard_parallel": "everything"}),
                              ("datacheck", {"timeout_s": 0}), ("datacheck", {"timeout_s": 1.5})):
            with self.subTest(values=values):
                with self.assertRaises(PipelineError):
                    resolve_runtime(stage, {stage: values})

    def test_missing_file_falls_back_to_the_template(self):
        runtime = load_runtime(Path(self.folder.name) / "does_not_exist.json")
        self.assertIsNone(runtime["abaqus"].get("launcher"))
        self.assertEqual(resolve_runtime("solve", runtime)["cpus"], 4)

    def test_unknown_stage_is_rejected(self):
        with self.assertRaises(PipelineError):
            resolve_runtime("batch", {})


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.launcher = Path(self.folder.name) / "fake_abaqus.bat"
        self.launcher.write_text(FAKE_LAUNCHER, encoding="ascii")

    def test_parse_release_year_needs_an_abaqus_token(self):
        self.assertEqual(parse_release_year("Abaqus 2026"), 2026)
        self.assertEqual(parse_release_year("Abaqus/Standard 2026"), 2026)
        # The real 2026 launcher spaces the digits out: "Abaqus 2 0 2 6".
        self.assertEqual(parse_release_year("Abaqus JOB abaqus\nAbaqus 2 0 2 6\n"), 2026)
        self.assertEqual(parse_release_year("Abaqus/Standard 2 0 2 6"), 2026)
        self.assertIsNone(parse_release_year(r"E:\ABAQUS\2026\Commands\abaqus.bat"))
        self.assertIsNone(parse_release_year(None))

    def test_launcher_resolution(self):
        self.assertEqual(resolve_launcher({"abaqus": {"launcher": str(self.launcher)}})["path"],
                         str(self.launcher))
        self.assertEqual(resolve_launcher({"abaqus": {}}, str(self.launcher))["path"],
                         str(self.launcher))
        for runtime, explicit in (({"abaqus": {}}, None),
                                  ({"abaqus": {"launcher": "relative"}}, None),
                                  ({"abaqus": {}}, str(Path(self.folder.name) / "missing.bat"))):
            with self.subTest(explicit=explicit):
                with self.assertRaises(PipelineError) as caught:
                    resolve_launcher(runtime, explicit)
                self.assertEqual(caught.exception.code, "EXTERNAL_TOOL_MISSING")

    def test_release_query_and_gate(self):
        info = abaqus.query_release(self.launcher)
        self.assertEqual(info["release_year"], 2026)
        self.assertEqual(enforce_release_gate(self.launcher, "2026", info)["gate"], "enforced")
        self.assertEqual(enforce_release_gate(self.launcher, None, info)["gate"],
                         "not_configured")
        with self.assertRaises(PipelineError) as caught:
            enforce_release_gate(self.launcher, "2025", info)
        self.assertEqual(caught.exception.code, "ABAQUS_RELEASE_MISMATCH")
        with self.assertRaises(PipelineError) as caught:
            enforce_release_gate(self.launcher, "2026",
                                 {"release_string": None, "release_year": None})
        self.assertEqual(caught.exception.code, "ABAQUS_RELEASE_MISMATCH")
        self.assertIsNotNone(info["return_code"])

    def test_abaqus_environment_is_sanitized(self):
        base = {"PATH": "C:/bin", "PYTHONPATH": "C:/pixi/site-packages", "CONDA_PREFIX": "C:/pixi",
                "PIXI_ENVIRONMENT_NAME": "default", "SYSTEMROOT": "C:/Windows", "TEMP": "C:/tmp"}
        child = abaqus_env(base)
        for name in ("PYTHONPATH", "CONDA_PREFIX", "PIXI_ENVIRONMENT_NAME"):
            self.assertNotIn(name, child)
        self.assertEqual(child["SYSTEMROOT"], "C:/Windows")
        self.assertIn("PATH", child)
        self.assertTrue(set(BLOCKED_ENV_VARS).isdisjoint(child))


class JobNameTests(unittest.TestCase):
    def test_derived_names_are_deterministic_and_stage_distinct(self):
        self.assertEqual(derive_job_name("fig1", "datacheck"), "fig1_dc")
        self.assertEqual(derive_job_name("fig1", "solve"), "fig1_solve")
        self.assertEqual(resolve_job_name("solve", "fig1"), ("fig1_solve", "derived"))

    def test_sanitised_names_keep_the_case_distinguishable(self):
        dashed = derive_job_name("Ref-30", "solve")
        dotted = derive_job_name("Ref.30", "solve")
        self.assertNotEqual(dashed, dotted)
        self.assertTrue(dashed.startswith("Ref_30_"), dashed)
        self.assertEqual(dashed, derive_job_name("Ref-30", "solve"))

    def test_long_names_are_truncated_deterministically(self):
        long_case = "c" * 90
        name = derive_job_name(long_case, "datacheck")
        self.assertLessEqual(len(name), 64)
        self.assertEqual(name, derive_job_name(long_case, "datacheck"))
        self.assertNotEqual(name, derive_job_name("c" * 89, "datacheck"))

    def test_explicit_names_are_validated(self):
        self.assertEqual(resolve_job_name("solve", "fig1", "MyJob_1"), ("MyJob_1", "cli"))
        for bad in ("has space", "has-dash", "x" * 65):
            with self.subTest(name=bad):
                with self.assertRaises(PipelineError) as caught:
                    resolve_job_name("solve", "fig1", bad)
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        # An empty explicit name falls back to the derived one.
        self.assertEqual(resolve_job_name("solve", "fig1", ""), ("fig1_solve", "derived"))

    def test_missing_case_id_requires_an_explicit_name(self):
        with self.assertRaises(PipelineError):
            derive_job_name(None, "solve")
        with self.assertRaises(PipelineError):
            derive_job_name("fig1", "publish")


_DATACHECK_FILES = {"{job}.dat": "Abaqus\nANALYSIS DATACHECK COMPLETE\n",
                    "{job}.msg": "no messages\n",
                    "{job}.odb": "datacheck odb placeholder\n"}
#: Abaqus/Explicit writes a different completion token (measured on the 2026
#: install): the Standard phrase is absent from an Explicit datacheck output.
_EXPLICIT_DATACHECK_FILES = {"{job}.dat": "Abaqus\nTHE ANALYSIS HAS COMPLETED SUCCESSFULLY\n",
                             "{job}.msg": "no messages\n",
                             "{job}.odb": "datacheck odb placeholder\n"}
_STA_OK = ("                    STEP      INC      ATT   SEVERE-DISCON\n"
           "                       1         1        1        0     0      3      3"
           "     0.1000     0.1000     0.1000\n"
           "                       1        59        1        0     0      3      3"
           "     1.0000     1.0000     0.0200\n"
           " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
_SOLVE_FILES = {"{job}.dat": "solver output\n", "{job}.msg": "no messages\n",
                "{job}.sta": _STA_OK, "{job}.odb": "results odb placeholder\n"}


class FakeAbaqus:
    """Stand-in for the launcher: records argv and writes a real job's files."""

    def __init__(self, files, returncode=0, stdout=None, timeout=False):
        self.files = files
        self.returncode = returncode
        self.stdout = stdout
        self.timeout = timeout
        self.calls = []

    def __call__(self, argv, cwd, timeout_s, stdout_path, stderr_path):
        argv = [str(part) for part in argv]
        self.calls.append({"argv": argv, "cwd": Path(cwd), "timeout_s": timeout_s})
        if self.timeout:
            raise subprocess.TimeoutExpired(argv, timeout_s)
        cwd = Path(cwd)
        job = next(part[4:] for part in argv if part.startswith("job="))
        for name, text in self.files.items():
            (cwd / name.format(job=job)).write_text(text, encoding="utf-8")
        text = ("Abaqus JOB %s COMPLETED\n" % job) if self.stdout is None else self.stdout
        Path(stdout_path).write_text(text, encoding="utf-8")
        Path(stderr_path).write_text("", encoding="utf-8")
        return self.returncode

    def argv_for(self, index=0):
        return self.calls[index]["argv"]


class StageSandbox(unittest.TestCase):
    """A real built deck directory plus a real (fake) launcher file, no Abaqus."""

    counter = 0

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        root = Path(self.folder.name)
        self.paths = synthetic_bundle(root / "mesh")
        simulation = write_synthetic_simulation(root, name="simulation.json")
        # The case layout: <work>/<case_id>/abaqus holds the deck and every log.
        self.deck_dir = root / "work" / "mini" / "abaqus"
        self.build_report = build(*self.paths, simulation, self.deck_dir)
        self.launcher = root / "fake_abaqus.bat"
        self.launcher.write_text(FAKE_LAUNCHER, encoding="ascii")
        self.runtime = root / "runtime.json"
        self.runtime.write_text(json.dumps(
            {"abaqus": {"launcher": str(self.launcher), "release_required": "2026"},
             "datacheck": {"cpus": 1, "timeout_s": 60},
             "solve": {"cpus": 2, "timeout_s": 60}}), encoding="utf-8")

    def _clean_job_files(self, job):
        """Remove one job's Abaqus products so each subtest starts from a clean dir."""
        for path in Path(self.deck_dir).glob(job + ".*"):
            path.unlink()

    def datacheck(self, runner, **kwargs):
        self._clean_job_files("mini_dc")
        with mock.patch.object(abaqus, "_run_launcher", runner):
            return run_datacheck(self.deck_dir, runtime_path=self.runtime, **kwargs)

    def solve(self, runner, **kwargs):
        self._clean_job_files("mini_solve")
        with mock.patch.object(abaqus, "_run_launcher", runner):
            return run_solve(self.deck_dir, runtime_path=self.runtime, **kwargs)

    def accepted_datacheck(self):
        report = self.datacheck(FakeAbaqus(dict(_DATACHECK_FILES)))
        self.assertEqual(report["status"], "DATACHECK_PASSED")
        return report


class DeckIntegrityTests(StageSandbox):
    """The deck on disk must still be the deck the report recorded (no staging)."""

    def test_verification_passes_for_a_fresh_build(self):
        recorded = verify_deck(self.deck_dir, self.build_report,
                               "SOURCE_BUILD_ARTIFACT_MISMATCH")
        self.assertEqual(recorded["physical.inp"],
                         self.build_report["provenance"]["physical_inp_sha256"])
        self.assertIn("ingredients/pbc_map.json", recorded)

    def test_changed_deck_or_include_is_rejected(self):
        for rel in ("physical.inp", "blocks/contact.inc", "ingredients/pbc_map.json"):
            with self.subTest(rel=rel):
                path = self.deck_dir / rel
                original = path.read_bytes()
                path.write_bytes(original + b"** tampered\n")
                try:
                    with self.assertRaises(PipelineError) as caught:
                        verify_deck(self.deck_dir, self.build_report,
                                    "SOURCE_BUILD_ARTIFACT_MISMATCH")
                    self.assertEqual(caught.exception.code, "SOURCE_BUILD_ARTIFACT_MISMATCH")
                finally:
                    path.write_bytes(original)

    def test_missing_deck_file_is_rejected(self):
        path = self.deck_dir / "blocks/outputs.inc"
        original = path.read_bytes()
        path.unlink()
        try:
            with self.assertRaises(PipelineError) as caught:
                verify_deck(self.deck_dir, self.build_report,
                            "SOURCE_BUILD_ARTIFACT_MISMATCH")
            self.assertEqual(caught.exception.code, "SOURCE_BUILD_ARTIFACT_MISMATCH")
        finally:
            path.write_bytes(original)

    def test_deck_referencing_an_unrecorded_include_is_rejected(self):
        deck = self.deck_dir / "physical.inp"
        original = deck.read_bytes()
        (self.deck_dir / "blocks/extra.inc").write_text("*End Step\n", encoding="utf-8")
        deck.write_text(original.decode("utf-8").replace(
            "*Include, input=blocks/step_end.inc",
            "*Include, input=blocks/step_end.inc\n*Include, input=blocks/extra.inc"),
            encoding="utf-8")
        try:
            report = json.loads(json.dumps(self.build_report))
            report["deck"]["files"]["physical.inp"] = file_hash(deck)
            report["provenance"]["physical_inp_sha256"] = file_hash(deck)
            with self.assertRaises(PipelineError) as caught:
                verify_deck(self.deck_dir, report, "SOURCE_BUILD_ARTIFACT_MISMATCH")
            self.assertIn("blocks/extra.inc", str(caught.exception))
        finally:
            deck.write_bytes(original)
            (self.deck_dir / "blocks/extra.inc").unlink()

    def test_deck_referencing_an_unrecorded_include_is_rejected(self):
        deck = self.deck_dir / "physical.inp"
        original = deck.read_bytes()
        (self.deck_dir / "blocks/extra.inc").write_text("*End Step\n", encoding="utf-8")
        deck.write_text(original.decode("utf-8").replace(
            "*Include, input=blocks/step_end.inc",
            "*Include, input=blocks/step_end.inc\n*Include, input=blocks/extra.inc"),
            encoding="utf-8")
        try:
            # The deck's own SHA is updated in the report, so only the include
            # graph can detect the unrecorded artifact.
            report = json.loads(json.dumps(self.build_report))
            report["deck"]["files"]["physical.inp"] = file_hash(deck)
            report["provenance"]["physical_inp_sha256"] = file_hash(deck)
            with self.assertRaises(PipelineError) as caught:
                verify_deck(self.deck_dir, report, "SOURCE_BUILD_ARTIFACT_MISMATCH")
            self.assertEqual(caught.exception.code, "SOURCE_BUILD_ARTIFACT_MISMATCH")
            self.assertIn("blocks/extra.inc", str(caught.exception))
        finally:
            deck.write_bytes(original)
            (self.deck_dir / "blocks/extra.inc").unlink()


class DatacheckTests(StageSandbox):
    def test_clean_datacheck_passes_and_writes_a_report(self):
        runner = FakeAbaqus(dict(_DATACHECK_FILES))
        report = self.datacheck(runner)
        self.assertEqual(report["status"], "DATACHECK_PASSED")
        self.assertEqual(report["job"], {"name": "mini_dc", "source": "derived"})
        self.assertEqual((report["runtime"]["cpus"], report["runtime"]["timeout_s"]), (1, 60))
        self.assertEqual(report["solver"], "standard_dynamic_implicit")
        self.assertEqual(report["source"]["physical_inp_sha256"],
                         self.build_report["provenance"]["physical_inp_sha256"])
        self.assertEqual(report["provenance"]["config_sha256"],
                         self.build_report["provenance"]["config_sha256"])
        self.assertEqual(report["claims"], {"datacheck": "PASS", "solve": "NOT_RUN",
                                            "dataset_eligible": False})
        self.assertEqual(report["diagnostics"]["error_count"], 0)
        # The command must be a datacheck and must never be an analysis.
        argv = runner.argv_for()
        self.assertEqual(argv[0], str(self.launcher))
        self.assertIn("datacheck", argv)
        self.assertIn("interactive", argv)
        self.assertIn("cpus=1", argv)
        self.assertIn("standard_parallel=solver", argv)
        self.assertNotIn("analysis", argv)
        self.assertNotIn("continue", argv)
        # Nothing was copied: the deck is still the deck the build wrote.
        for rel, expected in self.build_report["deck"]["files"].items():
            self.assertEqual(file_hash(self.deck_dir / rel), expected, rel)
        kinds = {entry["kind"] for entry in report["abaqus_output"]["generated_files"]}
        self.assertTrue({"dat", "msg", "odb"} <= kinds, kinds)
        command = json.loads((self.deck_dir / "datacheck_command.json").read_text(
            encoding="utf-8"))
        self.assertEqual(command["job_name"], "mini_dc")
        self.assertEqual(command["job_name_source"], "derived")
        self.assertTrue(command["datacheck_flag_present"])
        self.assertFalse(command["analysis_flag_present"])
        self.assertTrue((self.deck_dir / "datacheck_report.json").is_file())

    def test_explicit_deck_uses_its_own_command_line(self):
        """standard_parallel is Standard-only: an Explicit data check must not pass it."""
        simulation = write_synthetic_simulation(self.folder.name, name="explicit.json",
                                                mutate=_use_explicit)
        deck = Path(self.folder.name) / "work" / "mini_exp" / "abaqus"
        build(*self.paths, simulation, deck)
        runner = FakeAbaqus(dict(_EXPLICIT_DATACHECK_FILES))
        with mock.patch.object(abaqus, "_run_launcher", runner):
            report = run_datacheck(deck, runtime_path=self.runtime)
        argv = runner.argv_for()
        self.assertIn("datacheck", argv)
        self.assertIn("cpus=1", argv)
        self.assertNotIn("standard_parallel=solver", argv)
        self.assertEqual(report["solver"], "explicit_dynamic")
        self.assertEqual(report["status"], "DATACHECK_PASSED")

    def test_the_completion_token_follows_the_solver(self):
        # A Standard run must not accept the Explicit phrase and vice versa.
        report = self.datacheck(FakeAbaqus(dict(_EXPLICIT_DATACHECK_FILES)))
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertIn("datacheck completion marker missing", report["failure_reasons"])
        deck = Path(self.folder.name) / "work" / "mini_exp" / "abaqus"
        if not deck.is_dir():
            simulation = write_synthetic_simulation(self.folder.name, name="explicit2.json",
                                                    mutate=_use_explicit)
            build(*self.paths, simulation, deck)
        runner = FakeAbaqus(dict(_DATACHECK_FILES))
        with mock.patch.object(abaqus, "_run_launcher", runner):
            report = run_datacheck(deck, runtime_path=self.runtime)
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertIn("datacheck completion marker missing", report["failure_reasons"])

    def test_warnings_and_errors_change_the_status(self):
        warned = dict(_DATACHECK_FILES)
        warned["{job}.dat"] = ("ANALYSIS DATACHECK COMPLETE\n"
                               "***WARNING: contact overclosure was adjusted\n")
        report = self.datacheck(FakeAbaqus(warned))
        self.assertEqual(report["status"], "DATACHECK_COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["diagnostics"]["warning_count"], 1)
        self.assertEqual(report["diagnostics"]["categories"], ["CONTACT"])

        broken = dict(_DATACHECK_FILES)
        broken["{job}.dat"] = "ANALYSIS DATACHECK COMPLETE\n***ERROR: element 12 is distorted\n"
        report = self.datacheck(FakeAbaqus(broken))
        self.assertEqual(report["status"], "DATACHECK_FAILED")
        self.assertEqual(report["claims"]["datacheck"], "FAIL")
        self.assertIn("1 ***ERROR entries", report["failure_reasons"])

    def test_incomplete_or_inconsistent_runs_fail(self):
        cases = {
            "missing_completion_marker": ({"{job}.dat": "nothing to report\n"}, 0),
            "return_code": (dict(_DATACHECK_FILES), 1),
            "missing_odb": ({"{job}.dat": "ANALYSIS DATACHECK COMPLETE\n"}, 0),
            "zero_byte_odb": ({"{job}.dat": "ANALYSIS DATACHECK COMPLETE\n", "{job}.odb": ""}, 0),
            "abort_evidence": ({"{job}.dat": "ANALYSIS DATACHECK COMPLETE\n"
                                             "Abaqus/Standard aborted\n"}, 0),
        }
        for name, (files, code) in cases.items():
            with self.subTest(case=name):
                report = self.datacheck(FakeAbaqus(files, returncode=code))
                self.assertEqual(report["status"], "DATACHECK_FAILED")
                self.assertTrue(report["failure_reasons"])

    def test_explicit_job_name_is_used_and_recorded(self):
        report = self.datacheck(FakeAbaqus(dict(_DATACHECK_FILES)), job_name="MyDatacheck")
        self.assertEqual(report["job"], {"name": "MyDatacheck", "source": "cli"})
        self.assertTrue((self.deck_dir / "MyDatacheck.dat").is_file())

    def test_bad_source_builds_are_rejected_before_running_abaqus(self):
        report_path = self.deck_dir / "build_report.json"
        original = report_path.read_bytes()
        runner = FakeAbaqus(dict(_DATACHECK_FILES))
        try:
            broken = json.loads(original)
            broken["status"] = "STATIC_VALIDATION_FAILED"
            report_path.write_text(json.dumps(broken), encoding="utf-8")
            with mock.patch.object(abaqus, "_run_launcher", runner):
                with self.assertRaises(PipelineError) as caught:
                    run_datacheck(self.deck_dir, runtime_path=self.runtime)
            self.assertEqual(caught.exception.code, "SOURCE_BUILD_INVALID")
            self.assertEqual(runner.calls, [])
        finally:
            report_path.write_bytes(original)
        # A tampered deck is a different failure and also never launches Abaqus.
        contact = self.deck_dir / "blocks/contact.inc"
        good = contact.read_bytes()
        contact.write_bytes(good + b"** tampered\n")
        try:
            with mock.patch.object(abaqus, "_run_launcher", runner):
                with self.assertRaises(PipelineError) as caught:
                    run_datacheck(self.deck_dir, runtime_path=self.runtime)
            self.assertEqual(caught.exception.code, "SOURCE_BUILD_ARTIFACT_MISMATCH")
            self.assertEqual(runner.calls, [])
        finally:
            contact.write_bytes(good)

    def test_timeout_reports_its_own_code(self):
        with self.assertRaises(PipelineError) as caught:
            self.datacheck(FakeAbaqus({}, timeout=True))
        self.assertEqual(caught.exception.code, "DATACHECK_TIMEOUT")


class SolveTests(StageSandbox):
    def test_clean_solve_completes(self):
        self.accepted_datacheck()
        runner = FakeAbaqus(dict(_SOLVE_FILES))
        report = self.solve(runner)
        self.assertEqual(report["status"], "SOLVE_COMPLETED")
        self.assertEqual(report["job"], {"name": "mini_solve", "source": "derived"})
        self.assertEqual(report["completion"]["target_time_reached"], True)
        self.assertEqual(report["completion"]["last_step_time"], 1.0)
        self.assertEqual(report["claims"]["solve"], "COMPLETED")
        self.assertEqual(report["claims"]["odb_results_qa"], "NOT_RUN")
        argv = runner.argv_for()
        self.assertIn("analysis", argv)
        self.assertIn("cpus=2", argv)
        self.assertIn("standard_parallel=solver", argv)
        self.assertNotIn("datacheck", argv)
        self.assertNotIn("recover", argv)
        self.assertEqual(report["abaqus_output"]["odb"]["size_bytes"],
                         (self.deck_dir / "mini_solve.odb").stat().st_size)
        self.assertTrue((self.deck_dir / "solve_report.json").is_file())

    def test_solve_reverifies_the_accepted_deck(self):
        self.accepted_datacheck()
        contact = self.deck_dir / "blocks/contact.inc"
        original = contact.read_bytes()
        contact.write_bytes(original + b"** edited after the data check\n")
        try:
            with mock.patch.object(abaqus, "_run_launcher", FakeAbaqus(dict(_SOLVE_FILES))):
                with self.assertRaises(PipelineError) as caught:
                    run_solve(self.deck_dir, runtime_path=self.runtime)
            self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_ARTIFACT_MISMATCH")
        finally:
            contact.write_bytes(original)

    def test_unfinished_or_unproven_runs_fail(self):
        self.accepted_datacheck()
        partial = dict(_SOLVE_FILES)
        partial["{job}.sta"] = ("                       1         1        1        0     0"
                                "      3      3     0.5000     0.5000     0.1000\n"
                                " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
        cases = {
            "target_not_reached": (partial, 0, None),
            "missing_stdout_token": (dict(_SOLVE_FILES), 0, "no completion token here\n"),
            "missing_sta": ({"{job}.dat": "", "{job}.msg": "", "{job}.odb": "x"}, 0, None),
            "zero_byte_odb": ({"{job}.dat": "", "{job}.msg": "", "{job}.sta": _STA_OK,
                               "{job}.odb": ""}, 0, None),
            "return_code": (dict(_SOLVE_FILES), 1, None),
            "fatal_line": ({"{job}.dat": "THE ANALYSIS HAS NOT BEEN COMPLETED\n",
                            "{job}.msg": "", "{job}.sta": _STA_OK, "{job}.odb": "x"}, 0, None),
        }
        for name, (files, code, stdout) in cases.items():
            with self.subTest(case=name):
                report = self.solve(FakeAbaqus(files, returncode=code, stdout=stdout))
                self.assertEqual(report["status"], "SOLVE_FAILED")
                self.assertEqual(report["claims"]["solve"], "FAIL")
                self.assertTrue(report["failure_reasons"])

    def test_warnings_keep_the_solve_but_flag_it(self):
        self.accepted_datacheck()
        files = dict(_SOLVE_FILES)
        files["{job}.msg"] = "***WARNING: contact overclosure was adjusted\n"
        report = self.solve(FakeAbaqus(files))
        self.assertEqual(report["status"], "SOLVE_COMPLETED_WITH_WARNINGS")
        self.assertEqual(report["claims"]["solve"], "COMPLETED_WITH_WARNINGS")


    def test_only_an_accepted_datacheck_can_be_solved(self):
        self.accepted_datacheck()
        report_path = self.deck_dir / "datacheck_report.json"
        original = report_path.read_bytes()
        runner = FakeAbaqus(dict(_SOLVE_FILES))
        for name, status in (("failed_datacheck", "DATACHECK_FAILED"),
                             ("already_solved", "DATACHECK_PASSED")):
            with self.subTest(case=name):
                document = json.loads(original)
                document["status"] = status
                if name == "already_solved":
                    document["claims"]["solve"] = "COMPLETED"
                report_path.write_text(json.dumps(document), encoding="utf-8")
                with mock.patch.object(abaqus, "_run_launcher", runner):
                    with self.assertRaises(PipelineError) as caught:
                        run_solve(self.deck_dir, runtime_path=self.runtime)
                self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_INVALID")
                self.assertEqual(runner.calls, [])
        report_path.write_bytes(original)
        empty = Path(self.folder.name) / "no_report"
        empty.mkdir()
        with self.assertRaises(PipelineError) as caught:
            run_solve(empty, runtime_path=self.runtime)
        self.assertEqual(caught.exception.code, "SOURCE_DATACHECK_INVALID")

    def test_solve_timeout_reports_its_own_code(self):
        self.accepted_datacheck()
        with self.assertRaises(PipelineError) as caught:
            self.solve(FakeAbaqus({}, timeout=True))
        self.assertEqual(caught.exception.code, "SOLVE_TIMEOUT")

    def test_explicit_sta_and_command_are_solver_specific(self):
        """An Explicit solve passes no standard_parallel and reads the Explicit .sta."""
        simulation = write_synthetic_simulation(self.folder.name, name="explicit.json",
                                                mutate=_use_explicit)
        deck = Path(self.folder.name) / "work" / "mini_exp" / "abaqus"
        build(*self.paths, simulation, deck)
        with mock.patch.object(abaqus, "_run_launcher",
                               FakeAbaqus(dict(_EXPLICIT_DATACHECK_FILES))):
            run_datacheck(deck, runtime_path=self.runtime)
        files = dict(_SOLVE_FILES)
        files["{job}.sta"] = ("  1000  5.000E-04  5.000E-04  00:00:10  1.0E-08  0  0.0  0.0\n"
                             " 2000  1.000E+00  1.000E+00  00:00:20  1.0E-08  0  0.0  0.0\n"
                             " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n")
        runner = FakeAbaqus(files)
        with mock.patch.object(abaqus, "_run_launcher", runner):
            report = run_solve(deck, runtime_path=self.runtime)
        argv = runner.argv_for()
        self.assertIn("analysis", argv)
        self.assertNotIn("standard_parallel=solver", argv)
        self.assertEqual(report["solver"], "explicit_dynamic")
        self.assertEqual(report["completion"]["last_step_time"], 1.0)
        self.assertEqual(report["status"], "SOLVE_COMPLETED")


def _use_explicit(document):
    """Switch a simulation config to the Explicit solver (mesh/config unchanged)."""
    document["solver"]["type"] = "explicit_dynamic"
    return document


class StaParserTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "job.sta"

    def test_successful_increments_only(self):
        self.path.write_text(
            " STEP INC ATT SEVERE-DISCON EQUIL-ITERS TOTAL-ITERS TOTAL TIME STEP TIME\n"
            "    1   1   1    0   0    3    3   0.0010   0.0010   0.0010\n"
            "    1  1U   1    0   0    3    3   0.0005   0.0005   0.0005\n"
            "    1  59   1    0   0    3    3   1.0000   1.0000   0.0200\n"
            " THE ANALYSIS HAS COMPLETED SUCCESSFULLY\n", encoding="utf-8")
        info = abaqus.parse_sta(self.path)
        self.assertEqual(info["increment_count"], 2)
        self.assertEqual((info["last_step"], info["last_increment"]), (1, 59))
        self.assertEqual(info["last_step_time"], 1.0)
        self.assertTrue(info["sta_completion"])

    def test_missing_file_is_reported_not_raised(self):
        info = abaqus.parse_sta(Path(self.folder.name) / "missing.sta")
        self.assertEqual(info, {"sta_exists": False, "increment_count": 0, "last_step": None,
                                "last_increment": None, "last_step_time": None,
                                "sta_completion": False})


class LauncherTimeoutTests(unittest.TestCase):
    """A wall-limit expiry must end the case's WHOLE Abaqus tree and verify that it
    is gone before the call returns; a tree that refuses to die must stop the batch
    with a fatal error (RB-014, confirmed on real stalled standard.exe orphans)."""

    class FakeProc:
        """Popen stand-in without a real handle (job attach degrades to sweep-only)."""
        pid = 4711

        def __init__(self, returncode=None):
            self.returncode = returncode

        def wait(self, timeout=None):
            if self.returncode is None:
                raise subprocess.TimeoutExpired("launcher", timeout)
            return self.returncode

        def poll(self):
            return self.returncode

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.deck_dir = Path(self.folder.name) / "abaqus"
        self.deck_dir.mkdir()
        self.kills = []

    def _fake_world(self, sequences):
        """Patch process enumeration (per call) and PID termination with fakes."""
        state = {"enumerate": 0}

        def processes():
            rows = sequences[min(state["enumerate"], len(sequences) - 1)]
            state["enumerate"] += 1
            return rows

        def terminate(pid):
            self.kills.append(pid)
            return True

        return (mock.patch.object(abaqus, "_system_processes", processes),
                mock.patch.object(abaqus, "_terminate_pid", terminate),
                mock.patch.object(abaqus, "_TREE_POLL_INTERVAL_S", 0.0),
                mock.patch.object(abaqus, "_TREE_GRACE_S", 0.2))

    def _launch(self, proc, patches):
        with mock.patch.object(abaqus.subprocess, "Popen", lambda *a, **k: proc):
            with patches[0], patches[1], patches[2], patches[3]:
                return abaqus._run_launcher(["launcher.bat", "job=mini_solve"], self.deck_dir,
                                            0.05, self.deck_dir / "o.txt",
                                            self.deck_dir / "e.txt")

    def test_timeout_kills_the_tree_and_verifies_before_returning(self):
        deck = str(self.deck_dir).lower()
        solver_row = (99, 1, "standard.exe -indir %s -outdir %s -job mini_solve" % (deck, deck))
        patches = self._fake_world([[solver_row], []])
        with self.assertRaises(subprocess.TimeoutExpired):
            self._launch(self.FakeProc(), patches)
        self.assertEqual(sorted(self.kills), [99, 4711],
                         "the root launcher AND the matched solver PID must be terminated")

    def test_surviving_tree_processes_stop_everything_with_a_fatal_error(self):
        solver_row = (99, 1, "standard.exe -indir %s" % str(self.deck_dir).lower())
        patches = self._fake_world([[solver_row]])
        with self.assertRaises(PipelineError) as caught:
            self._launch(self.FakeProc(), patches)
        self.assertEqual(caught.exception.code, "ABAQUS_TREE_NOT_TERMINATED")
        self.assertTrue(caught.exception.fatal,
                        "an unterminated tree must stop the batch, not be swallowed")
        self.assertEqual(caught.exception.__cause__, None)

    def test_survivors_are_rekilled_during_the_verification_window(self):
        solver_row = (99, 1, "standard.exe -indir %s" % str(self.deck_dir).lower())
        patches = self._fake_world([[solver_row], [solver_row], []])
        with self.assertRaises(subprocess.TimeoutExpired):
            self._launch(self.FakeProc(), patches)
        self.assertGreaterEqual(self.kills.count(99), 2,
                                "a survivor seen in verification must be killed again")

    def test_a_failing_enumeration_is_never_treated_as_a_clean_tree(self):
        """PowerShell failing mid-verification must NOT read as "no processes left":
        unverifiable keeps polling and ends in the fatal branch, never in a pass."""
        patches = self._fake_world([[(99, 1, "standard.exe -indir %s"
                                      % str(self.deck_dir).lower())], None, None, None])
        with self.assertRaises(PipelineError) as caught:
            self._launch(self.FakeProc(), patches)
        self.assertEqual(caught.exception.code, "ABAQUS_TREE_NOT_TERMINATED")
        self.assertTrue(caught.exception.fatal)
        self.assertIn("enumeration itself failed", caught.exception.args[0])

    def test_a_clean_exit_never_touches_any_process(self):
        patches = self._fake_world([[]])
        code = self._launch(self.FakeProc(returncode=0), patches)
        self.assertEqual(code, 0)
        self.assertEqual(self.kills, [])


class CasePidMatchingTests(unittest.TestCase):
    """Identification is by THIS case's deck dir / job name only: never the
    controller itself, never another case's solver."""

    def test_only_this_case_matches(self):
        mine = os.getpid()
        deck = r"F:\repo\work\batch\caseA\abaqus"
        other = r"F:\repo\work\batch\caseB\abaqus"
        rows = [(100, 1, "standard.exe -indir %s -outdir %s" % (deck.lower(), deck.lower())),
                (101, 1, "standard.exe -indir %s" % other.lower()),
                (102, 1, "e:/abaqus/abaqus.bat job=caseA_solve interactive"),
                (mine, 1, "python -B run.py run-case --work-root f:\\repo\\work\\batch"),
                (103, 1, "explorer.exe")]
        pids = abaqus._case_pids(rows, (deck, "caseA_solve"))
        self.assertEqual(sorted(pids), [100, 102])
        self.assertNotIn(mine, pids, "the controller must never match its own command line")

    def test_mixed_separators_and_case_are_normalized(self):
        rows = [(100, 1, "standard.exe -indir f:/repo/work/caseA/abaqus")]
        self.assertEqual(abaqus._case_pids(rows, (r"F:\REPO\work\caseA\abaqus", "")), [100])


if __name__ == "__main__":
    unittest.main()
