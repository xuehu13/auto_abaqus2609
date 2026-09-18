"""One-case pipeline: mesh -> mesh data check -> build -> data check -> solve -> extract.

The whole run lives in one directory, so there is no staging and no per-stage copy:

    work/<case_id>/
        mesh/     frozen vendor stages 00-06 (+ CGAL) and the mesh data check logs
        abaqus/   physical.inp, blocks/, ingredients/, logs and the ODB
        results/  history.csv, stress_strain.csv, summary.json
                  (+ curve_qa.json when runtime.results.curve_qa_policy is set)
        status.json
        run.log

Resume is deliberately simple: a stage is skipped when its own result file says it
already succeeded, and the two config SHA256 recorded in status.json decide whether
an earlier result is still valid (case config changed -> everything re-runs;
simulation config changed -> build onwards re-runs). ``--force`` re-runs everything.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import time

from .abaqus import load_runtime, run_datacheck, run_mesh_datacheck, run_solve
from .build import DECK_ROOT, build
from .common import (PipelineError, digest, read_json, safe_id, write_json)
from .curve_qa import record_curve_qa
from .extract import extract
from .mesh import load_case, run_mesh

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("mesh", "mesh_datacheck", "build", "datacheck", "solve", "extract")
#: Stages a changed simulation config invalidates (the mesh does not depend on it).
_SIMULATION_DEPENDENT = ("build", "datacheck", "solve", "extract")
_ACCEPTED_DATACHECK = ("DATACHECK_PASSED", "DATACHECK_COMPLETED_WITH_WARNINGS")
_COMPLETED_SOLVE = ("SOLVE_COMPLETED", "SOLVE_COMPLETED_WITH_WARNINGS")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _Log:
    """Append one line per event to run.log and echo it to the console."""

    def __init__(self, path, echo):
        self.path = Path(path)
        self.echo = echo

    def __call__(self, message):
        line = "%s | %s" % (_now(), message)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        self.echo(line)


def _status_of(path):
    return read_json(path).get("status") if Path(path).is_file() else None


def _deck_root_sha(report):
    """SHA256 of physical.inp as recorded by a stage report (None when absent)."""
    return ((report or {}).get("deck") or {}).get("files", {}).get(DECK_ROOT)


def _stage_done(stage, work_dir):
    """Has this stage already produced its own success evidence for THIS deck?

    The stage reports are chained by the deck SHA256 they ran, so a report left
    over from an older deck can never mark a stage as done.
    """
    work_dir = Path(work_dir)
    if stage == "mesh":
        return (work_dir / "mesh" / "mesh_result.json").is_file()
    if stage == "mesh_datacheck":
        return _status_of(work_dir / "mesh" / "meshcheck_report.json") == "PASSED"
    if stage == "build":
        return _status_of(work_dir / "abaqus" / "build_report.json") == "BUILT"
    if stage == "datacheck":
        report_path = work_dir / "abaqus" / "datacheck_report.json"
        if _status_of(report_path) not in _ACCEPTED_DATACHECK:
            return False
        build_path = work_dir / "abaqus" / "build_report.json"
        if not build_path.is_file():
            return False
        return (_deck_root_sha(read_json(report_path))
                == _deck_root_sha(read_json(build_path)))
    if stage == "solve":
        report_path = work_dir / "abaqus" / "solve_report.json"
        if not report_path.is_file():
            return False
        document = read_json(report_path)
        odb = (document.get("abaqus_output") or {}).get("odb") or {}
        if document.get("status") not in _COMPLETED_SOLVE:
            return False
        datacheck_path = work_dir / "abaqus" / "datacheck_report.json"
        if not datacheck_path.is_file():
            return False
        return (_deck_root_sha(document) == _deck_root_sha(read_json(datacheck_path))
                and (work_dir / "abaqus" / odb.get("path", "")).is_file())
    if stage == "extract":
        summary_path = work_dir / "results" / "summary.json"
        if not summary_path.is_file():
            return False
        build_path = work_dir / "abaqus" / "build_report.json"
        if not build_path.is_file():
            return False
        # Like datacheck/solve, the extract stage is chained to the deck it ran:
        # a summary from an older deck never counts as done.
        return (read_json(summary_path).get("deck_root_sha256")
                == _deck_root_sha(read_json(build_path)))
    raise PipelineError("CONFIG_INVALID", "Unknown stage: " + repr(stage))


def results_complete(work_dir):
    """Are the three result files present and marked successful?"""
    work_dir = Path(work_dir)
    summary_path = work_dir / "results" / "summary.json"
    if not summary_path.is_file():
        return False
    if not (work_dir / "results" / "history.csv").is_file():
        return False
    if not (work_dir / "results" / "stress_strain.csv").is_file():
        return False
    try:
        return read_json(summary_path).get("success") is True
    except (ValueError, OSError):
        return False


def _record_curve_qa(work_dir, results_cfg, log):
    """Recorded curve QA (``runtime.results.curve_qa_policy``): never a gate.

    Runs whenever the extract stage runs, and also on resume when its results are
    already done, so ``results/curve_qa.json`` always reflects the policy that is
    configured right now. A missing or invalid policy file is a loud config error.
    """
    policy = (results_cfg or {}).get("curve_qa_policy")
    if not policy:
        return None
    policy_path = Path(policy)
    if not policy_path.is_absolute():
        policy_path = ROOT / policy_path
    work_dir = Path(work_dir)
    summary = read_json(work_dir / "results" / "summary.json")
    return record_curve_qa(work_dir / "results", policy_path=policy_path,
                           height_mm=summary["height_mm"],
                           area_mm2=summary["reference_area_mm2"], log=log)


def set_aside(path, stamp):
    """Move a superseded stage directory aside; evidence is never deleted."""
    path = Path(path)
    if not path.exists():
        return None
    target = path.with_name(path.name + ".previous_" + stamp)
    index = 1
    while target.exists():
        index += 1
        target = path.with_name(path.name + ".previous_%s_%d" % (stamp, index))
    os.rename(path, target)
    return target


def _invalidated(previous, case_sha, simulation_sha, force):
    """Stages that must re-run because the config changed (or --force was used)."""
    if force or not previous:
        return set(STAGES)
    if previous.get("case_config_sha256") != case_sha:
        return set(STAGES)
    if previous.get("simulation_config_sha256") != simulation_sha:
        return set(_SIMULATION_DEPENDENT)
    return set()


def run_case(case_path, simulation_path, *, case_document=None, work_root=None, runtime_path=None,
             force=False, cpus=None, timeout_s=None, job_name=None, abaqus_command=None,
             log=print):
    """Run (or resume) the whole single-case pipeline and return the final status.

    ``case_document`` runs an in-memory case config (batch: defaults + one record)
    instead of reading ``case_path``; the config SHA is then the digest of that
    document, so resume keeps working without a file on disk.
    """
    case = load_case(case_path, document=case_document)
    case_id = safe_id(case["case_id"])
    work_root = Path(work_root) if work_root else ROOT / "work"
    work_dir = work_root / case_id
    work_dir.mkdir(parents=True, exist_ok=True)
    logger = _Log(work_dir / "run.log", log)
    status_path = work_dir / "status.json"
    previous = read_json(status_path) if status_path.is_file() else {}
    # Resume keys are content digests, not file bytes: the same case supplied as a
    # file (config/cases/*.json) or as a merged batch record must be the same case.
    case_sha = digest(case)
    simulation = read_json(simulation_path)
    simulation_sha = digest(simulation)
    stale = _invalidated(previous, case_sha, simulation_sha, force)
    solver = simulation["solver"]["type"]
    logger("run-case %s (solver=%s, work=%s)" % (case_id, solver, work_dir))
    # An unfinished previous run cannot still be active: this process is the only
    # one that could have been running it. Complete results are accepted as DONE,
    # anything else resumes from the first stage without success evidence.
    recovered = None
    if previous.get("status") == "RUNNING":
        if results_complete(work_dir):
            recovered = "DONE"
            logger("previous run was interrupted but its results are complete: DONE")
        else:
            recovered = "INTERRUPTED"
            logger("previous run was interrupted at stage %r: resuming"
                   % previous.get("stage"))
    if recovered == "DONE" and not force:
        status = dict(previous, stage="done", status="DONE", message=None,
                      updated=_now(), recovered_from="INTERRUPTED")
        status["stages"] = dict(previous.get("stages") or {})
        write_json(status_path, status)
        logger("case %s DONE (results were already complete)" % case_id)
        return status
    if force:
        logger("--force: every stage runs again")
    elif stale:
        logger("config changed: stages to re-run: " + ", ".join(sorted(stale)))
    if stale:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        # Only supersede the directories whose stages are actually stale, so a
        # changed simulation config keeps an expensive mesh.
        for stage, name in (("mesh", "mesh"), ("build", "abaqus"), ("extract", "results")):
            if stage in stale:
                moved = set_aside(work_dir / name, stamp)
                if moved is not None:
                    logger("previous %s moved to %s" % (name, moved.name))
    status = {"case_id": case_id, "solver": solver, "work_dir": str(work_dir),
              "case_config_sha256": case_sha, "simulation_config_sha256": simulation_sha,
              "stage": None, "status": "RUNNING", "message": None,
              "stages": dict(previous.get("stages") or {}), "updated": _now()}
    if recovered:
        status["recovered_from"] = recovered
    # Config snapshots: what this case actually ran with, not just the input line.
    write_json(work_dir / "case_used.json", case)
    write_json(work_dir / "simulation_used.json", simulation)
    write_json(status_path, status)
    results_cfg = load_runtime(runtime_path).get("results") or {}
    keep_odb = results_cfg.get("keep_odb", True)
    mesh_dir = work_dir / "mesh"
    deck_dir = work_dir / "abaqus"
    results_dir = work_dir / "results"
    try:
        for stage in STAGES:
            if stage not in stale and _stage_done(stage, work_dir):
                status["stages"].setdefault(stage, {})["status"] = "DONE"
                logger("%-14s skipped (already done)" % stage)
                if stage == "extract":
                    status["stage"] = stage
                    _record_curve_qa(work_dir, results_cfg, logger)
                continue
            status["stage"] = stage
            status["status"] = "RUNNING"
            status["updated"] = _now()
            write_json(status_path, status)
            logger("%-14s start" % stage)
            started = time.monotonic()
            if stage == "mesh":
                runtime = load_runtime(runtime_path)
                if (mesh_dir / "engine").exists():
                    # A partial engine from an interrupted mesh run would make
                    # run_mesh refuse to start: keep it as evidence, start clean.
                    moved = set_aside(mesh_dir / "engine", "interrupted")
                    logger("incomplete mesh engine moved to %s" % moved.name)
                run_mesh(case_path, mesh_dir, logger, case_document=case_document,
                         cgal_executable=(runtime.get("cgal") or {}).get("executable"))
            elif stage == "mesh_datacheck":
                run_mesh_datacheck(read_json(mesh_dir / "mesh_result.json"),
                                   abaqus_command=abaqus_command, cpus=cpus, timeout_s=timeout_s,
                                   runtime_path=runtime_path, log=logger)
            elif stage == "build":
                mesh_result = read_json(mesh_dir / "mesh_result.json")
                if deck_dir.exists():
                    # A deck half-written by an interrupted build would make build()
                    # refuse to start; keep it as evidence and start clean.
                    moved = set_aside(deck_dir, "incomplete")
                    logger("incomplete deck moved to %s" % moved.name)
                build(mesh_result["npz"], mesh_result["report"], mesh_result["pairs_csv"],
                      simulation_path, deck_dir)
            elif stage == "datacheck":
                run_datacheck(deck_dir, abaqus_command=abaqus_command, job_name=job_name,
                              cpus=cpus, timeout_s=timeout_s, runtime_path=runtime_path)
            elif stage == "solve":
                run_solve(deck_dir, abaqus_command=abaqus_command, job_name=job_name,
                          cpus=cpus, timeout_s=timeout_s, runtime_path=runtime_path)
            else:
                extract(deck_dir, results_dir, case_id=case_id, runtime_path=runtime_path,
                        abaqus_command=abaqus_command,
                        timeout_s=timeout_s or 3600, log=logger)
                _record_curve_qa(work_dir, results_cfg, logger)
                if not keep_odb:
                    status["odb_removed"] = drop_odb(deck_dir, logger)
            status["stages"].setdefault(stage, {})["status"] = "DONE"
            status["stages"][stage]["at"] = _now()
            status["stages"][stage]["seconds"] = round(time.monotonic() - started, 1)
            write_json(status_path, status)
            logger("%-14s done (%.1f s)" % (stage, status["stages"][stage]["seconds"]))
    except (PipelineError, OSError) as exc:
        code = getattr(exc, "code", "ERROR")
        status["status"] = code
        status["message"] = str(exc)
        status["stages"].setdefault(status["stage"], {})["status"] = code
        status["stages"][status["stage"]]["message"] = str(exc)
        status["updated"] = _now()
        write_json(status_path, status)
        logger("%-14s FAILED (%s): %s" % (status["stage"], code, str(exc).splitlines()[0]))
        raise
    status["stage"] = "done"
    status["status"] = "DONE"
    status["message"] = None
    status["updated"] = _now()
    write_json(status_path, status)
    logger("case %s DONE (results in %s)" % (case_id, results_dir))
    return status


def drop_odb(deck_dir, log):
    """Remove the solved ODB of a case (runtime.results.keep_odb=false only).

    Called after extraction succeeded, so the curves are already on disk. Nothing
    else is deleted: .dat/.msg/.sta/.inp and the logs stay for failure analysis.
    """
    deck_dir = Path(deck_dir)
    removed = []
    for odb in sorted(deck_dir.glob("*.odb")):
        removed.append([odb.name, odb.stat().st_size])
        odb.unlink()
    if removed:
        log("     odb removed (keep_odb=false): "
            + ", ".join("%s (%.1f MB)" % (name, size / 1048576.0)
                        for name, size in removed))
    return removed
