"""Sequential driver for the ref30_02..05 implicit/explicit experiment.

Experiment tooling only - it shells out to `pixi run cli run-case` and touches
no pipeline code. One run at a time; a run that exceeds WALL_BUDGET_S is killed
by PID tree (never by image name) and the driver moves to the next one.

    python experiments/ref30_2to5_20260918/run_all.py
"""
from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXP = Path(__file__).resolve().parent
WORK_ROOT = ROOT / "work" / "exp_ref30_2to5_20260918"
LOG = EXP / "experiment_log.csv"

#: Hard wall-clock cap per run. The pipeline's own solve.timeout_s (1500 s) fires
#: first and writes a proper SOLVE_TIMEOUT report; this backstop only catches a
#: hang outside the Abaqus stages (mesh/build).
WALL_BUDGET_S = 2100

CASES = ("ref30_02", "ref30_03", "ref30_04", "ref30_05")
RUNS = (
    [("implicit", case, "simulation_implicit.json", "runtime_implicit_cpus8_all.json")
     for case in CASES]
    + [("explicit_T0.006s", case, "simulation_explicit_T0.006s.json", "runtime_explicit_cpus8.json")
       for case in CASES]
    + [("explicit_T0.01s", case, "simulation_explicit_T0.01s.json", "runtime_explicit_cpus8.json")
       for case in CASES]
)


def read_status(work_dir):
    path = work_dir / "status.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def kill_tree(proc):
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                   capture_output=True, text=True)


def main():
    fieldnames = ["group", "case_id", "started_utc", "wall_s", "exit", "pipeline_status",
                  "stage", "message_head"]
    rows = []
    log_path = LOG
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for group, case, simulation, runtime in RUNS:
            work_root = WORK_ROOT / group
            cmd = ["pixi", "run", "cli", "run-case",
                   "--case", str((EXP / "cases" / (case + ".json")).relative_to(ROOT)),
                   "--simulation", str((EXP / simulation).relative_to(ROOT)),
                   "--runtime", str((EXP / runtime).relative_to(ROOT)),
                   "--work-root", str(work_root.relative_to(ROOT))]
            started = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            print("[launch] %s / %s  %s" % (group, case, started), flush=True)
            begin = time.monotonic()
            proc = subprocess.Popen(cmd, cwd=str(ROOT))
            exit_code, note = None, ""
            try:
                exit_code = proc.wait(timeout=WALL_BUDGET_S)
            except subprocess.TimeoutExpired:
                kill_tree(proc)
                proc.wait()
                note = "WALLTIME_KILLED_%ds" % WALL_BUDGET_S
            wall = round(time.monotonic() - begin, 1)
            status = read_status(work_root / case) or {}
            row = {"group": group, "case_id": case, "started_utc": started,
                   "wall_s": wall, "exit": "" if exit_code is None else exit_code,
                   "pipeline_status": status.get("status", "NO_STATUS"),
                   "stage": status.get("stage", ""),
                   "message_head": (note + " " + str(status.get("message") or "")).strip()[:200]}
            rows.append(row)
            writer.writerow(row)
            stream.flush()
            print("[done]   %s / %s  exit=%s wall=%ss status=%s %s"
                  % (group, case, row["exit"], wall, row["pipeline_status"], note), flush=True)
    print("[all] %d runs finished; log: %s" % (len(rows), log_path), flush=True)


if __name__ == "__main__":
    sys.exit(main())
