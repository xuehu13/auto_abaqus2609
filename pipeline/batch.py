"""Batch driver: run_case() over a list of cases.

The whole idea is one loop:

    for case in cases:
        run_case(case)

Cases come from a JSONL file (one surface per line) plus a shared defaults file.
A batch directory keeps one sub-directory per case, exactly like a single run, and
adds four small bookkeeping files the main process writes after each finished case:

    work/<batch>/
        <case_id>/            mesh/ abaqus/ results/ status.json run.log (unchanged)
        batch_summary.csv     one row per case
        results_index.jsonl   successful cases only (for the dataset builder)
        failed_cases.jsonl    failed cases only (for a later re-run)
        batch.log             one line per case event

Nothing here knows about Abaqus, meshes or solvers: it only passes the simulation
config to run_case() and reads back status.json / results/summary.json. One worker
runs one whole case; retries reuse the identical inputs and only re-run the stage
that failed.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import json
import os
from pathlib import Path
import threading
from datetime import datetime, timezone

from .common import PipelineError, digest, file_hash, read_json, safe_id, write_json
from .mesh import load_case
from .run_case import STAGES, results_complete, run_case

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "config" / "cases.jsonl"
DEFAULT_CASE_DEFAULTS = ROOT / "config" / "case_defaults.json"
#: Statuses of a finished case directory, derived from status.json.
PENDING = "PENDING"
INTERRUPTED = "INTERRUPTED"
DONE = "DONE"
SUMMARY_COLUMNS = ("case_id", "surface_expression", "solver", "status", "failed_stage",
                   "message",
                   "mesh_wall_time_s", "mesh_datacheck_wall_time_s", "build_wall_time_s",
                   "datacheck_wall_time_s", "solve_wall_time_s", "extract_wall_time_s",
                   "total_wall_time_s",
                   "points", "final_strain", "max_stress_MPa", "max_ke_ie_ratio",
                   "result_path")
_BATCH_FILES = ("batch_summary.csv", "results_index.jsonl", "failed_cases.jsonl",
                "batch_config.json", "batch.log")
_CASE_KEYS = ("case_id", "surface_expression")


# ---------------------------------------------------------------------------
# Cases: defaults + one JSONL record, merged. No inheritance tree, no templates.
# ---------------------------------------------------------------------------

def merge_case(defaults, record):
    """Merge one case record over the shared defaults (nested dicts merged one level).

    A record may carry an ``overrides`` dict, which is merged last so a case can
    change a single nested value without repeating the whole block.
    """
    def merge(base, extra):
        out = dict(base)
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = merge(out[key], value)
            else:
                out[key] = value
        return out

    overrides = record.get("overrides") or {}
    plain = {key: value for key, value in record.items() if key != "overrides"}
    return merge(merge(defaults, plain), overrides if isinstance(overrides, dict) else {})


def _read_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            text = line.strip()
            if not text or text.startswith("#"):
                continue
            try:
                record = json.loads(text)
            except ValueError as exc:
                raise PipelineError("CASES_FILE_INVALID",
                                    "%s line %d is not valid JSON: %s" % (path, number, exc))
            if not isinstance(record, dict):
                raise PipelineError("CASES_FILE_INVALID",
                                    "%s line %d must be a JSON object" % (path, number))
            records.append(record)
    if not records:
        raise PipelineError("CASES_FILE_INVALID", "No cases found in " + str(path))
    return records


def load_cases(cases_path, defaults_path=None):
    """Read the case list, merge defaults and validate every merged case.

    Duplicate case_id or a case_id that is not a safe directory name stops the whole
    batch: two cases writing into one directory would silently mix results.
    """
    cases_path = Path(cases_path)
    defaults_path = Path(defaults_path) if defaults_path else None
    defaults = read_json(defaults_path) if defaults_path and defaults_path.is_file() else {}
    records = _read_jsonl(cases_path)
    # Fail fast when the shared defaults themselves are unusable.
    probe = dict(defaults)
    probe.update({"case_id": "validate_defaults", "surface_expression": "0.0"})
    load_case(cases_path, document=probe)
    cases, seen = [], {}
    for record in records:
        missing = [key for key in _CASE_KEYS if not record.get(key)]
        if missing:
            raise PipelineError("CASES_FILE_INVALID",
                                "%s: a case record is missing %s" % (cases_path, missing))
        case_id = safe_id(record["case_id"])
        if case_id in seen:
            raise PipelineError("CASES_FILE_INVALID",
                                "Duplicate case_id %r (also on line %d)" % (case_id, seen[case_id]))
        seen[case_id] = len(cases) + 1
        case = merge_case(defaults, record)
        load_case(cases_path, document=case)
        cases.append({"case_id": case_id, "surface_expression": case["surface_expression"],
                      "case_config_sha256": digest(case), "document": case})
    return cases


# ---------------------------------------------------------------------------
# Case state: status.json + results/summary.json are the only sources of truth.
# ---------------------------------------------------------------------------

def case_state(work_dir):
    """Summarise one case directory: status, failed stage, per-stage seconds, curve data."""
    work_dir = Path(work_dir)
    state = {"case_id": work_dir.name, "status": PENDING, "failed_stage": None, "message": None,
             "solver": None, "seconds": {}, "summary": None,
             "result_path": str(work_dir / "results") if (work_dir / "results").is_dir() else None}
    status_path = work_dir / "status.json"
    if status_path.is_file():
        document = read_json(status_path)
        raw = document.get("status")
        state["solver"] = document.get("solver")
        state["failed_stage"] = document.get("stage") if raw not in (DONE, "RUNNING") else None
        state["message"] = document.get("message")
        state["seconds"] = {stage: entry.get("seconds")
                            for stage, entry in (document.get("stages") or {}).items()
                            if isinstance(entry, dict)}
        if raw == DONE:
            state["status"] = DONE
        elif raw == "RUNNING":
            # Cannot be active any more: either it finished (results complete) or it
            # was interrupted and will resume.
            if results_complete(work_dir):
                state["status"] = DONE
            else:
                state["status"] = INTERRUPTED
                state["message"] = ("interrupted during stage %r" % document.get("stage"))
        else:
            state["status"] = raw or "UNKNOWN"
    summary_path = work_dir / "results" / "summary.json"
    if summary_path.is_file():
        try:
            state["summary"] = read_json(summary_path)
        except (ValueError, OSError):
            state["summary"] = None
    if state["status"] == DONE and not results_complete(work_dir):
        state["status"] = INTERRUPTED
        state["message"] = "status.json says DONE but the result files are incomplete"
    return state


def _settle_interrupted(work_dir, log):
    """A RUNNING status whose results are already complete is a finished case.

    The process that would have finished it was killed (reboot, Ctrl+C, closed
    window), so nothing is running any more: record DONE instead of leaving a
    misleading RUNNING behind for every later reader.
    """
    status_path = Path(work_dir) / "status.json"
    if not status_path.is_file() or not results_complete(work_dir):
        return False
    document = read_json(status_path)
    if document.get("status") != "RUNNING":
        return False
    document.update(stage="done", status=DONE, message=None, recovered_from=INTERRUPTED,
                    updated=_now())
    write_json(status_path, document)
    log("settled %s: was RUNNING at stage %r but its results are complete -> DONE"
        % (work_dir.name, document.get("stage")))
    return True


def _decide(state, *, force, retry_failed):
    """Run, skip a finished case, or skip a failed one without --retry-failed."""
    if force:
        return "run"
    if state["status"] == DONE:
        return "skip_done"
    if state["status"] in (PENDING, INTERRUPTED):
        return "run"
    return "run" if retry_failed else "skip_failed"


def _first_failed_stage(state, work_dir):
    """Stage name that did not finish, for the summary's failed_stage column."""
    if state["failed_stage"]:
        return state["failed_stage"]
    for stage in STAGES:
        if (state["seconds"].get(stage) is None and stage != "extract"
                and not _stage_finished(stage, work_dir)):
            return stage
    return None


def _stage_finished(stage, work_dir):
    from .run_case import _stage_done
    try:
        return _stage_done(stage, work_dir)
    except PipelineError:
        return False


def _one_line(message, limit=300):
    """Collapse a multi-line failure message into one CSV-friendly line.

    The full text stays in the case's status.json; the summary only needs a pointer.
    """
    text = " ".join(str(message or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def _summary_row(case, state, work_dir):
    """One batch_summary.csv row; unknown values stay empty (never faked as 0)."""
    summary = state["summary"] or {}
    seconds = state["seconds"] or {}
    known = [seconds.get(stage) for stage in STAGES if seconds.get(stage) is not None]
    row = {"case_id": case.get("case_id"),
           "surface_expression": case.get("surface_expression"),
           "solver": state.get("solver") or summary.get("solver"),
           "status": state["status"],
           "failed_stage": _first_failed_stage(state, work_dir) if state["status"] not in (
               DONE, PENDING, INTERRUPTED) else None,
           "message": _one_line(state.get("message")),
           "points": summary.get("points"),
           "final_strain": summary.get("final_strain"),
           "max_stress_MPa": summary.get("max_stress_MPa"),
           "max_ke_ie_ratio": summary.get("max_ke_ie_ratio"),
           "total_wall_time_s": round(sum(known), 1) if known else None,
           "result_path": state["result_path"] if state["status"] == DONE else None}
    for stage in STAGES:
        row[stage + "_wall_time_s"] = seconds.get(stage)
    return row


def _write_batch_files(batch_dir, rows, cases, *, cases_path, defaults_path, simulation_path,
                       workers, retry_failed, max_retries, force):
    """Rewrite the four bookkeeping files (20k rows is a small CSV: no incremental IO)."""
    batch_dir = Path(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    order = {case["case_id"]: index for index, case in enumerate(cases)}
    rows = sorted(rows, key=lambda row: order.get(row["case_id"], 1 << 30))
    with (batch_dir / "batch_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(SUMMARY_COLUMNS), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: ("" if row.get(key) is None else row.get(key))
                             for key in SUMMARY_COLUMNS})
    _write_jsonl(batch_dir / "results_index.jsonl",
                 [{key: row[key] for key in ("case_id", "surface_expression", "solver")}
                  | {"stress_strain_csv": str(Path(row["case_id"]) / "results" / "stress_strain.csv"),
                     "history_csv": str(Path(row["case_id"]) / "results" / "history.csv"),
                     "summary_json": str(Path(row["case_id"]) / "results" / "summary.json")}
                  for row in rows if row["status"] == DONE])
    _write_jsonl(batch_dir / "failed_cases.jsonl",
                 [{"case_id": row["case_id"], "surface_expression": row["surface_expression"],
                   "stage": row["failed_stage"], "status": row["status"],
                   "message": row["message"],
                   "status_json": str(Path(row["case_id"]) / "status.json")}
                  for row in rows if row["status"] not in (DONE, PENDING, INTERRUPTED)])
    write_json(batch_dir / "batch_config.json",
               {"cases_file": str(cases_path), "case_defaults_file": str(defaults_path or ""),
                "simulation_file": str(simulation_path),
                "simulation_sha256": file_hash(simulation_path),
                "workers": workers, "retry_failed": retry_failed, "max_retries": max_retries,
                "force": force, "total_cases": len(cases), "updated": _now()})
    return rows


def _write_jsonl(path, records):
    with Path(path).open("w", encoding="utf-8", newline="\n") as stream:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_case_safe(case, simulation_path, *, work_root, runtime_path, force=False, cpus=None,
                  timeout_s=None, abaqus_command=None, attempts=1):
    """Run one case with optional identical-input retries; never raises case failures.

    Retries re-run the SAME config: run_case resumes from the stage that failed, so no
    scientific parameter is ever changed to make a case succeed.
    """
    error = None
    for _attempt in range(1, max(1, attempts) + 1):
        try:
            run_case(None, simulation_path, case_document=case["document"],
                     work_root=work_root, runtime_path=runtime_path, force=force,
                     cpus=cpus, timeout_s=timeout_s, abaqus_command=abaqus_command,
                     log=lambda message: None)
            error = None
            break
        except (PipelineError, OSError) as exc:
            error = exc
    return error


def run_batch(cases_path=None, simulation_path=None, *, defaults_path=None, work_root=None,
              workers=1, retry_failed=False, max_retries=0, force=False, runtime_path=None,
              cpus=None, timeout_s=None, abaqus_command=None, log=print):
    """Run every case in ``cases_path`` through run_case(), one case per worker."""
    cases_path = Path(cases_path or DEFAULT_CASES)
    simulation_path = Path(simulation_path)
    defaults_path = Path(defaults_path) if defaults_path else DEFAULT_CASE_DEFAULTS
    if not defaults_path.is_file():
        defaults_path = None
    batch_dir = Path(work_root) if work_root else ROOT / "work" / (
        "batch_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    batch_dir.mkdir(parents=True, exist_ok=True)
    cases = load_cases(cases_path, defaults_path)
    simulation = read_json(simulation_path)
    solver = simulation["solver"]["type"]
    workers = max(1, int(workers))
    runtime = read_json(runtime_path) if runtime_path else {}
    if workers > 1:
        log("workers=%d x solve cpus=%s -> up to ~%d CPUs; lower --workers if Abaqus is license "
            "or memory limited" % (workers, (runtime.get("solve") or {}).get("cpus", "?"),
                                   workers * int((runtime.get("solve") or {}).get("cpus", 4))))
    log("batch %s: %d cases, solver=%s, workers=%d" % (batch_dir, len(cases), solver, workers))
    batch_log = _Log(batch_dir / "batch.log", log)
    batch_log("cases=%s defaults=%s simulation=%s (solver=%s) workers=%d retry_failed=%s "
              "max_retries=%d force=%s" % (cases_path, defaults_path, simulation_path, solver,
                                           workers, retry_failed, max_retries, force))
    states = {case["case_id"]: case_state(batch_dir / case["case_id"]) for case in cases}
    todo, skipped = [], {"skip_done": 0, "skip_failed": 0}
    for case in cases:
        decision = _decide(states[case["case_id"]], force=force, retry_failed=retry_failed)
        if decision == "run":
            todo.append(case)
        else:
            if decision == "skip_done":
                _settle_interrupted(batch_dir / case["case_id"], batch_log)
            skipped[decision] += 1
            batch_log("skip %s (%s, status=%s)" % (case["case_id"], decision,
                                                   states[case["case_id"]]["status"]))
    log("to run: %d | already done: %d | failed and skipped: %d"
        % (len(todo), skipped["skip_done"], skipped["skip_failed"]))
    rows_by_id = {case["case_id"]: _summary_row(case, states[case["case_id"]],
                                                batch_dir / case["case_id"])
                  for case in cases}

    def publish():
        _write_batch_files(batch_dir, list(rows_by_id.values()), cases,
                           cases_path=cases_path, defaults_path=defaults_path,
                           simulation_path=simulation_path, workers=workers,
                           retry_failed=retry_failed, max_retries=max_retries, force=force)

    publish()
    interrupted, finished = False, 0
    if todo:
        pool = ThreadPoolExecutor(max_workers=workers)
        jobs = {}
        try:
            for case in todo:
                jobs[pool.submit(run_case_safe, case, simulation_path, work_root=batch_dir,
                                 runtime_path=runtime_path, force=force, cpus=cpus,
                                 timeout_s=timeout_s, abaqus_command=abaqus_command,
                                 attempts=1 + max(0, max_retries))] = case
            for future in as_completed(jobs):
                case = jobs[future]
                error = future.result()
                row = _summary_row(case, case_state(batch_dir / case["case_id"]),
                                   batch_dir / case["case_id"])
                rows_by_id[case["case_id"]] = row
                finished += 1
                batch_log("%s status=%s%s%s" % (
                    case["case_id"], row["status"],
                    "" if row["failed_stage"] is None else " stage=" + str(row["failed_stage"]),
                    "" if not error else " message=" + str(error).splitlines()[0]))
                log("[%d/%d] %-16s %-14s %s s" % (
                    finished, len(todo), case["case_id"], row["status"],
                    row["total_wall_time_s"] if row["total_wall_time_s"] is not None else "-"))
                publish()
        except KeyboardInterrupt:
            interrupted = True
            log("interrupted: no new case will start; running cases are allowed to finish")
            for future in jobs:
                future.cancel()
        finally:
            pool.shutdown(wait=True)
    # The final table is rebuilt from the case directories, so it also reflects a
    # KeyboardInterrupt (and anything an external process changed meanwhile).
    rows = [_summary_row(case, case_state(batch_dir / case["case_id"]),
                         batch_dir / case["case_id"]) for case in cases]
    _write_batch_files(batch_dir, rows, cases, cases_path=cases_path,
                       defaults_path=defaults_path, simulation_path=simulation_path,
                       workers=workers, retry_failed=retry_failed, max_retries=max_retries,
                       force=force)
    totals = {"DONE": 0, "FAILED": 0, "REMAINING": 0}
    for row in rows:
        if row["status"] == DONE:
            totals["DONE"] += 1
        elif row["status"] in (PENDING, INTERRUPTED):
            totals["REMAINING"] += 1
        else:
            totals["FAILED"] += 1
    batch_log("batch finished: DONE=%d FAILED=%d REMAINING=%d interrupted=%s"
              % (totals["DONE"], totals["FAILED"], totals["REMAINING"], interrupted))
    log("DONE=%d  FAILED=%d  REMAINING=%d%s"
        % (totals["DONE"], totals["FAILED"], totals["REMAINING"],
           "  (interrupted by user)" if interrupted else ""))
    return {"batch_dir": str(batch_dir), "cases": len(cases), "interrupted": interrupted,
            "summary_csv": str(batch_dir / "batch_summary.csv"), "rows": rows, **totals}


def rebuild_summary(batch_dir, *, log=print):
    """Rebuild batch_summary.csv / results_index.jsonl / failed_cases.jsonl from the cases."""
    batch_dir = Path(batch_dir)
    config_path = batch_dir / "batch_config.json"
    if not config_path.is_file():
        raise PipelineError("BATCH_DIR_INVALID", "No batch_config.json in " + str(batch_dir))
    config = read_json(config_path)
    cases_path = Path(config["cases_file"])
    defaults_path = Path(config["case_defaults_file"]) if config.get("case_defaults_file") else None
    if defaults_path is not None and not defaults_path.is_file():
        defaults_path = None
    cases = load_cases(cases_path, defaults_path)
    rows = [_summary_row(case, case_state(batch_dir / case["case_id"]),
                         batch_dir / case["case_id"]) for case in cases]
    _write_batch_files(batch_dir, rows, cases, cases_path=cases_path, defaults_path=defaults_path,
                       simulation_path=Path(config["simulation_file"]),
                       workers=config.get("workers", 1),
                       retry_failed=config.get("retry_failed", False),
                       max_retries=config.get("max_retries", 0),
                       force=config.get("force", False))
    done = sum(1 for row in rows if row["status"] == DONE)
    log("rebuilt %d rows (%d DONE) in %s" % (len(rows), done, batch_dir))
    return {"batch_dir": str(batch_dir), "cases": len(rows),
            "summary_csv": str(batch_dir / "batch_summary.csv"), "rows": rows, "DONE": done}


class _Log:
    """Append one line per event to batch.log and echo it to the console."""

    def __init__(self, path, echo):
        self.path = Path(path)
        self.echo = echo

    def __call__(self, message):
        line = "%s | %s" % (_now(), message)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")
        self.echo(line)
