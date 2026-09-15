"""Run through 'pixi run cli <command>' from the workspace; --help lists the actually implemented commands.

This entry refuses to run outside the Pixi default environment (PIXI_ENVIRONMENT_NAME
must be 'default' and CONDA_PREFIX must match sys.prefix). System Python, Anaconda
Python and any manually activated interpreter are unsupported by design.
"""
import argparse
import csv
import json
import os
from pathlib import Path
import sys

from pipeline.common import PipelineError, atomic_json, read_json
from pipeline.mesher_adapter import STAGES, prepare as prepare_mesher

ROOT = Path(__file__).resolve().parent


def main():
    prefix = os.environ.get("CONDA_PREFIX")  # Set by Pixi too; no manager invocation.
    if (os.environ.get("PIXI_ENVIRONMENT_NAME") != "default" or not prefix
            or Path(prefix).resolve() != Path(sys.prefix).resolve()):
        raise PipelineError("PIXI_REQUIRED", "Use pixi run cli <command> from the workspace; system Python is unsupported.")
    parser = argparse.ArgumentParser(description="DiffuMeta pipeline tools (no batch orchestration yet; solve runs one accepted job)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Print the complete planned pipeline and implementation status")
    p = sub.add_parser("prepare-mesher", help="Create a private mesher directory and exact command plan; do not execute it")
    p.add_argument("--case", default=str(ROOT / "config/cases/fig1.json"))
    local = ROOT / "config/environment.local.json"
    p.add_argument("--environment", default=str(local if local.is_file() else ROOT / "config/environment.example.json"))
    p.add_argument("--cgal-build", help="Build attempt directory produced by build-cgal; optional for preparation only")
    p.add_argument("--vendor", default=str(ROOT / "vendor/periodic_surface_mesher_v1.0"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("prepare-fe", help="Validate mesh contract and write FE ingredients only; the complete physical INP is assembled by build-physical")
    p.add_argument("--npz", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--pairs", required=True)
    p.add_argument("--physics", default=str(ROOT / "config/physics.example.json"))
    p.add_argument("--material", default=str(ROOT / "config/materials/demo_surrogate.json"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("build-physical", help="Assemble physical.inp from verified deterministic blocks and run repository static validation; Abaqus is not invoked")
    p.add_argument("--npz", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--pairs", required=True)
    p.add_argument("--physics", default=str(ROOT / "config/physics.example.json"))
    p.add_argument("--material", default=str(ROOT / "config/materials/demo_surrogate.json"))
    p.add_argument("--numerics", default=str(ROOT / "config/numerics.example.json"))
    p.add_argument("--outputs", default=str(ROOT / "config/outputs.example.json"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("datacheck", help="Stage a static-validated M1 build and run one real Abaqus Physical Data Check (datacheck only; never a solve)")
    p.add_argument("--build-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--abaqus-command", help="Explicit Abaqus launcher; default order: environment.local.json abaqus_launcher -> PATH abaqus -> PATH abq2026")
    p.add_argument("--job-name", default="fig1_m2_datacheck")
    p.add_argument("--cpus", type=int, help="Data Check execution policy override; default order: config/datacheck_runtime.local.json -> safe default cpus=1")
    p.add_argument("--standard-parallel", help="Data Check execution policy override (all|solver); default order: config/datacheck_runtime.local.json -> safe default standard_parallel=solver")
    p = sub.add_parser("solve", help="Stage an accepted M2 datacheck attempt and run one real Abaqus/Standard analysis; no ODB extraction")
    p.add_argument("--datacheck-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--abaqus-command", help="Explicit Abaqus launcher; default order: environment.local.json abaqus_launcher -> PATH abaqus -> PATH abq2026")
    p.add_argument("--job-name", default="fig1_m3_solve")
    p.add_argument("--cpus", type=int, help="Solve execution policy override; default order: config/solve_runtime.local.json -> safe default cpus=1")
    p.add_argument("--standard-parallel", help="Solve execution policy override (all|solver); default order: config/solve_runtime.local.json -> safe default standard_parallel=solver")
    p = sub.add_parser("qa-history", help="Check a previously aligned history CSV; does not accept samples into a dataset")
    p.add_argument("--csv", required=True)
    p.add_argument("--height-mm", type=float, required=True)
    p.add_argument("--area-mm2", type=float, required=True)
    p.add_argument("--reaction-sign", type=int, choices=(-1, 1), required=True)
    p.add_argument("--policy", default=str(ROOT / "config/quality.example.json"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("status", help="Read the stage ledger created by future orchestration or local integration")
    p.add_argument("--db", required=True)
    args = parser.parse_args()
    if args.command == "plan":
        result = {"version": "0.1.0", "production_ready": False,
                  "stages": [{"stage": name, "purpose": desc} for name, desc in STAGES],
                  "implemented": ["isolated mesher preparation", "NPZ/CSV/report contract checks",
                                  "PBC representative equations", "shell/PBC include generation",
                                  "SQLite stage ledger primitives", "stagnation and diagnostic primitives",
                                  "aligned history curve QA",
                                  "M1 complete physical builder: physical.inp assembly with repository "
                                  "static validation, no Abaqus invocation",
                                  "M2 physical data check: accepted-deck staging, real Abaqus datacheck "
                                  "invocation, diagnostics and structured report (Fig.1 passed with "
                                  "warnings)",
                                  "M3 single-job solve: accepted-deck staging, real Abaqus/Standard "
                                  "analysis invocation, completion evidence (.sta/stdout/target step "
                                  "time), structured solve report"],
                  "next": ["M4 ODB automatic extraction (results QA follows)",
                           "orchestration, reconciliation, acceptance and export"]}
    elif args.command == "prepare-mesher":
        result = prepare_mesher(args.vendor, args.case, args.environment, args.out, args.cgal_build)
    elif args.command == "prepare-fe":
        from pipeline.prepare_fe import prepare
        result = prepare(args.npz, args.report, args.pairs, args.physics, args.material, args.out)
    elif args.command == "build-physical":
        from pipeline.physical_builder import build as build_physical
        result = build_physical(args.npz, args.report, args.pairs, args.physics,
                                args.material, args.numerics, args.outputs, args.out)
    elif args.command == "datacheck":
        from pipeline.physical_datacheck import run_datacheck
        result = run_datacheck(args.build_dir, args.out, args.abaqus_command, args.job_name,
                               cpus=args.cpus, standard_parallel=args.standard_parallel)
    elif args.command == "solve":
        from pipeline.physical_solve import run_solve
        result = run_solve(args.datacheck_dir, args.out, args.abaqus_command, args.job_name,
                           cpus=args.cpus, standard_parallel=args.standard_parallel)
    elif args.command == "qa-history":
        from pipeline.curve_qa import assess
        if Path(args.out).exists():
            raise PipelineError("OUTPUT_EXISTS", "Use a new QA output path.")
        with open(args.csv, encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            columns = {k: [] for k in reader.fieldnames or []}
            for row in reader:
                for k in columns:
                    columns[k].append(float(row[k]))
        result = assess(columns, args.height_mm, args.area_mm2, args.reaction_sign, read_json(args.policy))
        atomic_json(args.out, result)
    else:
        from pipeline.state import StateStore
        if not Path(args.db).is_file():
            raise PipelineError("STATE_MISSING", "State database does not exist.")
        db = StateStore(args.db)
        try:
            result = db.status()
        finally:
            db.close()
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    if isinstance(result, dict) and result.get("status") == "CURVE_QA_FAILED":
        return 3
    if isinstance(result, dict) and result.get("status") in (
            "DATACHECK_FAILED", "DATACHECK_COMPLETED_WITH_WARNINGS",
            "SOLVE_FAILED", "SOLVE_COMPLETED_WITH_WARNINGS"):
        return 3  # Non-clean stage result: report is written, exit code signals review needed.
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PipelineError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "code": getattr(exc, "code", "INPUT_OR_IO_ERROR"), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
