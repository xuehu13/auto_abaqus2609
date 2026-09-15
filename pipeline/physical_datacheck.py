"""Real Abaqus Physical Data Check (M2): one static-validated deck, one datacheck job.

This module answers exactly one question: does the real local Abaqus accept the
physical.inp that the M1 builder produced? It stages a verified M1 build into a
new attempt, invokes `abaqus job=<name> input=physical.inp datacheck
interactive`, keeps every generated file as evidence, parses the datacheck
diagnostics and writes a structured report.

Scope guards: no real analysis is ever submitted (the command always contains
the literal 'datacheck' argument and never 'analysis' or 'continue'), the
return code alone never decides the outcome (diagnostics and artifacts are
required), and no warning whitelist exists. Solve, ODB QA and dataset
eligibility stay NOT_RUN/false regardless of the datacheck outcome.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .common import PipelineError, atomic_json, atomic_text, file_hash, read_json, reserve_directory

_INPUT_NAME = "physical.inp"
_DEFAULT_JOB_NAME = "fig1_m2_datacheck"
_DEFAULT_TIMEOUT_S = 3600
_ENVIRONMENT_LOCAL = Path(__file__).resolve().parents[1] / "config" / "environment.local.json"
_JOB_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")
_ERROR_PREFIX = "***ERROR"
_WARNING_PREFIX = "***WARNING"
# Continuation lines of a diagnostic message stop at the next keyword/blank line.
_CONTEXT_STOP = ("***", "*", "END OF", "THE ANALYSIS")
# Required datacheck artifacts: Abaqus 2026 datacheck interactive runs complete
# without writing a .log (stdout capture carries that role), so .log is optional.
# .msg/.log/.exception and everything else Abaqus produces are collected when
# present and parsed when applicable.
_REQUIRED_ARTIFACTS = ("dat", "odb")
_ABORT_MARKERS = ("exited with errors", "aborted", "abend")
_DATACHECK_COMPLETE_MARKER = "ANALYSIS DATACHECK COMPLETE"

# M2 safe/conservative Data Check execution profile: serial element operations
# keep preprocessing off the machine-specific parallel path that reproducibly
# failed during General Contact connectivity processing on the development
# machine (see docs/HANDOFF_CURRENT.md "Runtime portability"). This is a Data
# Check policy only: it is NOT part of the physical model, it never enters
# physical.inp or the M1 identity keys, and it is NOT the M3 Solve policy.
_SAFE_EXECUTION_POLICY = {"cpus": 1, "standard_parallel": "solver"}
_ALLOWED_STANDARD_PARALLEL = ("all", "solver")
_POLICY_LOCAL = Path(__file__).resolve().parents[1] / "config" / "datacheck_runtime.local.json"

# Files that must be staged from the source build: the deck itself plus every
# include it references (relative structure preserved), and the provenance JSONs.
_STAGED_DECK_FILES = (
    "physical.inp",
    "ingredients/shell_mesh.inc",
    "ingredients/lateral_pbc.inc",
    "blocks/material_section.inc",
    "blocks/rigid_platens.inc",
    "blocks/boundary_conditions.inc",
    "blocks/contact.inc",
    "blocks/step_loading.inc",
    "blocks/outputs.inc",
    "blocks/step_end.inc",
)
_PROVENANCE_FILES = (("model_manifest.json", "source_model_manifest.json"),
                     ("build_report.json", "source_build_report.json"))

# Light keyword classification for batch triage later. A category never makes a
# warning safe; every message is preserved verbatim in the report.
_CATEGORY_RULES = (
    ("STRAINFREE", ("strainfree", "strain-free")),
    ("CONTACT", ("contact", "overclosure", "copen", "cpress")),
    ("PBC_CONSTRAINT", ("equation", "periodic")),
    ("OVERCONSTRAINT", ("overconstraint", "conflicting constraint", "duplicate",
                        "redundant constraint")),
    ("ZERO_PIVOT", ("zero pivot", "numerical singularity", "singularity", "zero force")),
    ("RIGID_BODY", ("rigid body", "rigid")),
    ("MATERIAL", ("material", "plastic", "elastic", "density")),
    ("ELEMENT", ("element", "mesh", "distort")),
    ("OUTPUT", ("output", "odb", "request", "variable")),
)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _scan_diagnostic_file(path, prefix):
    """Collect one entry per line containing the prefix, with short continuation text.

    This understands only the line-oriented forms of real Abaqus .dat/.msg/.log
    diagnostics; it is not a general Abaqus log parser.
    """
    entries = []
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    for index, line in enumerate(lines):
        if prefix not in line:
            continue
        message = [line.strip()]
        for follow in lines[index + 1: index + 8]:
            stripped = follow.strip()
            if not stripped or stripped.startswith(_CONTEXT_STOP):
                break
            message.append(stripped)
        entries.append({"source_file": Path(path).name, "line_number": index + 1,
                        "message": "\n".join(message)})
    return entries


def categorize(message):
    lowered = message.lower()
    for category, keywords in _CATEGORY_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    return "OTHER"


def parse_diagnostics(dat_path, msg_path, log_path):
    """Extract errors[], warnings[], completion and abort evidence from datacheck files."""
    errors, warnings = [], []
    for path in (dat_path, msg_path, log_path):
        if path is None or not Path(path).is_file():
            continue
        errors.extend(_scan_diagnostic_file(path, _ERROR_PREFIX))
        warnings.extend(_scan_diagnostic_file(path, _WARNING_PREFIX))
    for entry in errors:
        entry["category"] = categorize(entry["message"])
    for entry in warnings:
        entry["category"] = categorize(entry["message"])
    log_text = (Path(log_path).read_text(encoding="utf-8", errors="replace")
                if log_path and Path(log_path).is_file() else "")
    dat_text = (Path(dat_path).read_text(encoding="utf-8", errors="replace")
                if dat_path and Path(dat_path).is_file() else "")
    haystack = (log_text + "\n" + dat_text).lower()
    return {
        "error_count": len(errors),
        "warning_count": len(warnings),
        "errors": errors,
        "warnings": warnings,
        "categories": sorted({entry["category"] for entry in errors + warnings}),
        "datacheck_complete_evidence": _DATACHECK_COMPLETE_MARKER.lower() in haystack,
        "job_completed_evidence": "completed" in log_text.lower(),
        "abort_evidence": [marker for marker in _ABORT_MARKERS if marker in haystack],
    }


def resolve_launcher(explicit=None, environment_path=None):
    """Resolve the local Abaqus launcher without hard-coding any install path.

    Order: explicit CLI value (must resolve; no silent fallback) -> project
    environment config (Git-ignored environment.local.json convention,
    abaqus_launcher may be null) -> PATH `abaqus` -> PATH `abq2026`. Windows
    .bat/.cmd launchers are valid. Anything unresolvable raises
    ABAQUS_LAUNCHER_NOT_FOUND; the system PATH is never modified.
    """
    if explicit:
        resolved = Path(explicit)
        if resolved.is_file():
            return {"path": str(resolved), "source": "cli"}
        found = shutil.which(explicit)
        if found:
            return {"path": str(found), "source": "cli"}
        raise PipelineError("ABAQUS_LAUNCHER_NOT_FOUND",
                            "Explicit Abaqus launcher not found: " + repr(explicit))
    candidates = []
    env_path = Path(environment_path) if environment_path else _ENVIRONMENT_LOCAL
    if env_path.is_file():
        try:
            configured = read_json(env_path).get("abaqus_launcher")
        except (ValueError, OSError):
            configured = None
        if configured:
            candidates.append(("environment:" + env_path.name, configured))
    for name in ("abaqus", "abq2026"):
        candidates.append(("path:" + name, name))
    for source, candidate in candidates:
        resolved = Path(candidate)
        if resolved.is_file():
            return {"path": str(resolved), "source": source}
        found = shutil.which(candidate)
        if found:
            return {"path": str(found), "source": source}
    raise PipelineError("ABAQUS_LAUNCHER_NOT_FOUND",
                        "No Abaqus launcher found. Pass --abaqus-command, set "
                        "abaqus_launcher in config/environment.local.json, or put "
                        "abaqus/abq2026 on the PATH; the system PATH is never modified.")


def query_release(launcher_path):
    """Ask the resolved launcher for its release string; failure is recorded, not fatal."""
    try:
        completed = subprocess.run([str(launcher_path), "information=release"],
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"release": None, "return_code": None, "error": str(exc)}
    text = (completed.stdout or "") + (completed.stderr or "")
    match = re.search(r"Abaqus\s+20\d\d[^\r\n]*", text)
    return {"release": match.group(0).strip() if match else text.strip()[:120] or None,
            "return_code": completed.returncode}


def _run_process(argv, cwd, timeout_s):
    """Run the launcher as a plain subprocess; Windows executes .bat/.cmd itself.

    Job name, input file and the fixed 'datacheck'/'interactive' arguments are
    generated or strictly validated by this module, never free user text.
    """
    completed = subprocess.run([str(part) for part in argv], cwd=str(cwd),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout_s)
    return completed.returncode, completed.stdout or "", completed.stderr or ""

def _load_source_build(build_dir):
    """A datacheck may only run on a build that M1 static validation passed."""
    build_dir = Path(build_dir)
    manifest_path = build_dir / "model_manifest.json"
    report_path = build_dir / "build_report.json"
    if not manifest_path.is_file() or not report_path.is_file():
        raise PipelineError("SOURCE_BUILD_INVALID",
                            "Source build lacks model_manifest.json/build_report.json: " + str(build_dir))
    manifest, report = read_json(manifest_path), read_json(report_path)
    if manifest.get("status") != "PHYSICAL_INP_STATIC_VALIDATED":
        raise PipelineError("SOURCE_BUILD_INVALID",
                            "Source build status must be PHYSICAL_INP_STATIC_VALIDATED, got: "
                            + repr(manifest.get("status")))
    if report.get("status") != "STATIC_VALIDATION_PASSED" or report.get("static_validation") != "PASS":
        raise PipelineError("SOURCE_BUILD_INVALID",
                            "Source build static validation must be PASS, got: "
                            + repr(report.get("static_validation")))
    if manifest.get("dataset_eligible") is not False:
        raise PipelineError("SOURCE_BUILD_INVALID", "Source build claims dataset eligibility.")
    recorded = manifest.get("physical_inp", {}).get("sha256")
    deck = build_dir / _INPUT_NAME
    if not deck.is_file() or not recorded or file_hash(deck) != recorded:
        raise PipelineError("SOURCE_BUILD_INVALID",
                            "physical.inp is missing or its SHA256 does not match the manifest.")
    return build_dir, manifest, report


def _stage_inputs(source_dir, attempt):
    """Copy the exact deck/include set (and provenance) with SHA256 verified after copy.

    Bytes are copied verbatim and never modified; any mismatch aborts the run so
    the report can always claim Abaqus checked the static-validated model.
    """
    staged = []
    for rel in _STAGED_DECK_FILES:
        src, dst = source_dir / rel, attempt / rel
        if not src.is_file():
            raise PipelineError("SOURCE_BUILD_INVALID", "Source build is missing: " + rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        if file_hash(src) != file_hash(dst):
            raise PipelineError("STAGING_SHA_MISMATCH", "Staged file differs from source: " + rel)
        staged.append({"path": rel, "sha256": file_hash(dst), "role": "input"})
    for src_name, dst_name in _PROVENANCE_FILES:
        src, dst = source_dir / src_name, attempt / dst_name
        dst.write_bytes(src.read_bytes())
        if file_hash(src) != file_hash(dst):
            raise PipelineError("STAGING_SHA_MISMATCH", "Staged file differs from source: " + dst_name)
        staged.append({"path": dst_name, "sha256": file_hash(dst), "role": "provenance"})
    return staged


def _collect_artifacts(attempt, job_name, staged_paths):
    """Keep every generated file; classify the diagnostic ones and hash them."""
    known_kinds = ("dat", "msg", "log", "odb", "prt", "mdl", "stt", "res", "com", "023")
    generated, classified = [], {"dat": None, "msg": None, "log": None, "odb": None}
    for path in sorted(attempt.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(attempt).as_posix()
        if rel in staged_paths:
            continue
        suffix = path.suffix.lower().lstrip(".")
        entry = {"path": rel, "size_bytes": path.stat().st_size,
                 "sha256": file_hash(path),
                 "kind": suffix if suffix in known_kinds else "other"}
        generated.append(entry)
        if rel == job_name + ".dat":
            classified["dat"] = path
        elif rel == job_name + ".msg":
            classified["msg"] = path
        elif rel == job_name + ".log":
            classified["log"] = path
        elif suffix == "odb" and classified["odb"] is None:
            classified["odb"] = path
    return generated, classified

def _resolve_execution_policy(cpus, standard_parallel, policy_path):
    """Resolve the Data Check execution policy: CLI > machine-local file > safe default.

    The policy is machine/runtime-local. cpus and standard_parallel only appear
    in the Abaqus command line and the datacheck provenance/report; they never
    enter physical.inp and never change the M1 model identity keys.
    """
    resolved = dict(_SAFE_EXECUTION_POLICY)
    source = "safe_default"
    path = Path(policy_path) if policy_path else _POLICY_LOCAL
    if path.is_file():
        configured = read_json(path)
        unexpected = set(configured) - {"schema_version", "cpus", "standard_parallel"}
        if configured.get("schema_version") != 1 or unexpected:
            raise PipelineError("CONFIG_INVALID",
                                "datacheck runtime policy file must use schema 1 with only "
                                "schema_version, cpus and standard_parallel: " + str(path))
        if configured.get("cpus") is not None:
            resolved["cpus"] = configured["cpus"]
        if configured.get("standard_parallel") is not None:
            resolved["standard_parallel"] = configured["standard_parallel"]
        source = "local_environment"
    if cpus is not None:
        resolved["cpus"] = cpus
        source = "cli"
    if standard_parallel is not None:
        resolved["standard_parallel"] = standard_parallel
        source = "cli"
    value = resolved["cpus"]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PipelineError("CONFIG_INVALID", "cpus must be an integer >= 1: " + repr(value))
    mode = resolved["standard_parallel"]
    if not isinstance(mode, str) or mode.strip().lower() not in _ALLOWED_STANDARD_PARALLEL:
        raise PipelineError("CONFIG_INVALID",
                            "standard_parallel must be one of "
                            + repr(list(_ALLOWED_STANDARD_PARALLEL)) + ": " + repr(mode))
    return {"cpus": value, "standard_parallel": mode.strip().lower(), "source": source}


def run_datacheck(build_dir, output, abaqus_command=None, job_name=_DEFAULT_JOB_NAME,
                  environment_path=None, timeout_s=_DEFAULT_TIMEOUT_S,
                  cpus=None, standard_parallel=None, policy_path=None):
    """Stage a verified M1 build and run one real Abaqus Physical Data Check.

    Returns the datacheck report dict (status DATACHECK_PASSED /
    DATACHECK_COMPLETED_WITH_WARNINGS / DATACHECK_FAILED). Pre-condition
    failures raise PipelineError and leave no partial attempt.
    """
    if not _JOB_NAME_RE.match(job_name or ""):
        raise PipelineError("CONFIG_INVALID",
                            "job_name must be ASCII letters/digits/underscore only: " + repr(job_name))
    source_dir, manifest, build_report = _load_source_build(build_dir)
    launcher = resolve_launcher(abaqus_command, environment_path)
    policy = _resolve_execution_policy(cpus, standard_parallel, policy_path)
    release = query_release(launcher["path"])
    attempt = reserve_directory(output)
    staged_entries = _stage_inputs(source_dir, attempt)
    staged_paths = {entry["path"] for entry in staged_entries}
    argv = [launcher["path"], "job=" + job_name, "input=" + _INPUT_NAME,
            "datacheck", "interactive",
            "cpus=%d" % policy["cpus"],
            "standard_parallel=%s" % policy["standard_parallel"]]
    started = _utc_now()
    try:
        returncode, stdout, stderr = _run_process(argv, attempt, timeout_s)
    except subprocess.TimeoutExpired as exc:
        raise PipelineError("DATACHECK_TIMEOUT",
                            "Abaqus datacheck exceeded the %ss wall limit; the attempt is "
                            "kept for inspection." % timeout_s) from exc
    ended = _utc_now()
    atomic_text(attempt / "stdout.txt", stdout)
    atomic_text(attempt / "stderr.txt", stderr)
    atomic_json(attempt / "command.json", {
        "launcher": launcher, "release": release, "arguments": argv[1:],
        "execution_policy": policy,
        "cwd": str(attempt), "job_name": job_name, "input": _INPUT_NAME,
        "datacheck_flag_present": "datacheck" in argv,
        "analysis_flag_present": any(flag in argv for flag in ("analysis", "continue")),
        "start_time": started, "end_time": ended, "return_code": returncode,
        "source_physical_inp_sha256": manifest["physical_inp"]["sha256"],
        "source_build_key": manifest["build_key"],
        "source_manifest_sha256": file_hash(source_dir / "model_manifest.json"),
    })
    generated, artifacts = _collect_artifacts(attempt, job_name, staged_paths)
    diagnostics = parse_diagnostics(artifacts["dat"], artifacts["msg"], artifacts["log"])
    missing = [kind for kind in _REQUIRED_ARTIFACTS if artifacts[kind] is None]
    if (returncode != 0 or diagnostics["error_count"] or diagnostics["abort_evidence"]
            or missing):
        status, claim = "DATACHECK_FAILED", "FAIL"
    elif diagnostics["warning_count"]:
        status, claim = "DATACHECK_COMPLETED_WITH_WARNINGS", "COMPLETED_WITH_WARNINGS"
    else:
        status, claim = "DATACHECK_PASSED", "PASS"
    report = {
        "schema_version": 1,
        "status": status,
        "source_build": {
            "path": str(source_dir),
            "model_key": manifest["identity"]["model_key"],
            "scaffold_key": manifest["scaffold_key"],
            "build_key": manifest["build_key"],
            "source_manifest_sha256": file_hash(source_dir / "model_manifest.json"),
            "physical_inp_sha256": manifest["physical_inp"]["sha256"],
        },
        "execution_policy": policy,
        "staged_files": staged_entries,
        "abaqus": {
            "launcher": launcher, "release": release, "job_name": job_name,
            "command": argv, "cwd": str(attempt), "return_code": returncode,
            "start_time": started, "end_time": ended,
        },
        "artifacts": {
            "required_presence": {kind: artifacts[kind] is not None
                                  for kind in _REQUIRED_ARTIFACTS},
            "generated_files": generated,
        },
        "diagnostics": diagnostics,
        "claims": {
            "physical_datacheck": claim,
            "solve": "NOT_RUN",
            "odb_results_qa": "NOT_RUN",
            "dataset_eligible": False,
        },
        "warning": "A Physical Data Check only proves Abaqus input-stage acceptance on this "
                   "machine. It does NOT prove convergence, a completed 30% compression, "
                   "correct contact/PBC behavior under load, quasi-static validity or dataset "
                   "eligibility; the datacheck .odb is not a results ODB.",
    }
    if status == "DATACHECK_FAILED":
        report["failure_reasons"] = (
            (["return_code=%d" % returncode] if returncode != 0 else [])
            + (["%d ***ERROR entries" % diagnostics["error_count"]]
               if diagnostics["error_count"] else [])
            + (["abort evidence: " + ", ".join(diagnostics["abort_evidence"])]
               if diagnostics["abort_evidence"] else [])
            + (["missing required artifacts: " + ", ".join(missing)] if missing else []))
    atomic_json(attempt / "datacheck_report.json", report)
    return report