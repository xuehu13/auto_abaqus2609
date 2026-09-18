"""CLI entry point: run through 'pixi run cli <command> ...' from the workspace root.

This refuses to run outside the Pixi default environment (PIXI_ENVIRONMENT_NAME must
be 'default' and CONDA_PREFIX must match sys.prefix): a system or Anaconda
interpreter is not a supported entry point for this project.

    run-case   the whole single-case pipeline (mesh -> ... -> extract)
    run-batch  many cases through the same run_case(), one directory per case
    run-experiment    one commented total config -> run-batch (user entry; RUN_GUIDE.md)
    summarize-batch   rebuild the batch tables from the case directories
    mesh | mesh-datacheck | build | datacheck | solve | extract   one stage, for debugging
    plan       what each stage consumes and produces
    qa-history one history CSV against the curve QA policy
"""
import argparse
import json
import os
from pathlib import Path
import sys

from pipeline.common import PipelineError

ROOT = Path(__file__).resolve().parent
DEFAULT_CASE = "config/cases/fig1.json"
DEFAULT_SIMULATION = "config/simulation.json"

PLAN = {
    "experiment": {"command": "pixi run cli run-experiment --config "
                              "config/experiments/production.json",
                   "note": "user entry: one commented total config (cases, geometry/mesh, "
                           "material/shell/loading/solver, runtime) -> run-batch; snapshots "
                           "of the effective config land in the batch directory",
                   "layout": "work/<experiment_id>/{<case_id>/, batch_summary.csv, "
                             "results_index.jsonl, failed_cases.jsonl, production_used.json}"},
    "one_case": {"command": "pixi run cli run-case --case config/cases/fig1.json "
                            "--simulation config/simulation.json",
                 "note": "resumes from work/<case_id>/status.json; use --force to redo",
                 "layout": "work/<case_id>/{mesh,abaqus,results,status.json,run.log}"},
    "many_cases": {"command": "pixi run cli run-batch --cases config/cases.jsonl "
                             "--case-defaults config/case_defaults.json "
                             "--simulation config/simulation.json [--workers 1]",
                   "note": "same run_case() per line of the JSONL; DONE skipped, INTERRUPTED "
                           "resumed, failed skipped unless --retry-failed",
                   "layout": "work/<batch>/{<case_id>/, batch_summary.csv, results_index.jsonl, "
                             "failed_cases.jsonl, batch.log}"},
    "stages": [
        {"stage": "mesh", "command": "pixi run cli mesh --case ...",
         "consumes": "config/cases/<case_id>.json",
         "produces": "work/<case_id>/mesh/engine (frozen vendor stages 00-06 + CGAL)"},
        {"stage": "mesh_datacheck", "command": "pixi run cli mesh-datacheck --case ...",
         "consumes": "the mesh-check INP written by vendor stage 06",
         "produces": "Abaqus mesh data check logs + vendor stage-07 validation"},
        {"stage": "build", "command": "pixi run cli build --case ... --simulation ...",
         "consumes": "mesh outputs + config/simulation.json",
         "produces": "work/<case_id>/abaqus/{ingredients,blocks,physical.inp,build_report.json}"},
        {"stage": "datacheck", "command": "pixi run cli datacheck --case ...",
         "consumes": "the built deck", "produces": "datacheck_report.json + logs"},
        {"stage": "solve", "command": "pixi run cli solve --case ...",
         "consumes": "the accepted deck", "produces": "solve_report.json + ODB"},
        {"stage": "extract", "command": "pixi run cli extract --case ...",
         "consumes": "the solved ODB",
         "produces": "results/{history.csv,stress_strain.csv,summary.json}"},
    ],
    "config": {"case": "config/cases/<case_id>.json",
               "simulation": "config/simulation.json (material, contact, loading, solver, output)",
               "runtime": "config/runtime.json (machine-local: Abaqus launcher, cpus, wall limit)"},
    "notes": ["Solver is chosen in config/simulation.json: solver.type is",
              "standard_dynamic_implicit or explicit_dynamic.",
              "The mesh and build stages never launch Abaqus. run-case DOES run datacheck and",
              "solve, so a long solve starts as soon as you call run-case (or solve) yourself."],
}


def _runtime_options(parser):
    parser.add_argument("--runtime", help="Runtime config path (default config/runtime.json)")
    parser.add_argument("--abaqus-command", help="Abaqus launcher; overrides the runtime config")
    parser.add_argument("--cpus", type=int, help="Override cpus for this run")
    parser.add_argument("--timeout-s", type=int, help="Override the stage wall limit in seconds")
    parser.add_argument("--job-name", help="Abaqus job name (default <case_id>_dc / _solve)")


def _main():
    prefix = os.environ.get("CONDA_PREFIX")  # Set by Pixi too; no manager invocation.
    if (os.environ.get("PIXI_ENVIRONMENT_NAME") != "default" or not prefix
            or Path(prefix).resolve() != Path(sys.prefix).resolve()):
        raise PipelineError("PIXI_REQUIRED",
                            "Use pixi run cli <command> from the workspace; system Python is "
                            "unsupported.")
    parser = argparse.ArgumentParser(
        description="Research pipeline: surface -> mesh -> deck -> data check -> solve -> results")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Print the stage list and the layout of one case run")

    p = sub.add_parser("run-case", help="Run the whole single-case pipeline (resumable)")
    p.add_argument("--case", default=DEFAULT_CASE)
    p.add_argument("--simulation", default=DEFAULT_SIMULATION)
    p.add_argument("--work-root", default=str(ROOT / "work"),
                   help="Case directories live in <work-root>/<case_id>")
    p.add_argument("--force", action="store_true", help="Re-run every stage")
    _runtime_options(p)

    p = sub.add_parser("mesh", help="Frozen mesh stages 00-06 + CGAL for one case")
    p.add_argument("--case", default=DEFAULT_CASE)
    p.add_argument("--work-root", default=str(ROOT / "work"))
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("mesh-datacheck", help="Abaqus data check of the mesh-check INP + stage 07")
    p.add_argument("--case", default=DEFAULT_CASE)
    p.add_argument("--work-root", default=str(ROOT / "work"))
    _runtime_options(p)

    p = sub.add_parser("build", help="Assemble physical.inp from the mesh and the simulation config")
    p.add_argument("--case", default=DEFAULT_CASE)
    p.add_argument("--simulation", default=DEFAULT_SIMULATION)
    p.add_argument("--work-root", default=str(ROOT / "work"))
    p.add_argument("--force", action="store_true")

    for name, help_text in (("datacheck", "Run one real Abaqus Physical Data Check"),
                            ("solve", "Run one real Abaqus analysis"),
                            ("extract", "ODB -> results/history_stress-strain CSV")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--case", default=DEFAULT_CASE)
        p.add_argument("--work-root", default=str(ROOT / "work"))
        _runtime_options(p)
        if name == "extract":
            p.add_argument("--odb", help="Read this ODB instead of the one solve_report.json "
                                         "names (debugging: re-extract an older result)")

    p = sub.add_parser("qa-history", help="Check one history CSV against the curve QA policy")
    p.add_argument("--csv", required=True)
    p.add_argument("--height-mm", type=float, required=True)
    p.add_argument("--area-mm2", type=float, required=True)
    p.add_argument("--reaction-sign", type=int, required=True, choices=(-1, 1))
    p.add_argument("--policy", required=True)
    p.add_argument("--out", required=True, help="NEW JSON output path")

    p = sub.add_parser("run-experiment",
                       help="Run one batch from a commented total config "
                            "(config/experiments/production.json); see docs/RUN_GUIDE.md")
    p.add_argument("--config", default="config/experiments/production.json",
                   help="Total experiment config (whole-line // comments allowed)")

    p = sub.add_parser("run-batch", help="Run many cases through the same single-case pipeline")
    p.add_argument("--cases", default="config/cases.jsonl", help="JSONL: one case per line")
    p.add_argument("--case-defaults", default="config/case_defaults.json",
                   help="Shared mesh parameters merged into every case")
    p.add_argument("--simulation", default=DEFAULT_SIMULATION)
    p.add_argument("--work-root", default=None,
                   help="Batch directory (default work/batch_<timestamp>)")
    p.add_argument("--workers", type=int, default=1,
                   help="Cases computed at the same time (default 1; you decide)")
    p.add_argument("--retry-failed", action="store_true",
                   help="Also run cases that failed in an earlier batch run")
    p.add_argument("--max-retries", type=int, default=0,
                   help="Extra attempts per case with the IDENTICAL config (default 0)")
    p.add_argument("--force", action="store_true", help="Re-run every selected case")
    _runtime_options(p)

    p = sub.add_parser("summarize-batch", help="Rebuild batch_summary.csv from the case dirs")
    p.add_argument("--work-root", required=True, help="Batch directory")
    args = parser.parse_args()

    if args.command == "plan":
        return PLAN
    if args.command == "qa-history":
        return _run_qa_history(args)
    if args.command == "run-case":
        from pipeline.run_case import run_case
        return run_case(args.case, args.simulation, work_root=args.work_root,
                        runtime_path=args.runtime, force=args.force, cpus=args.cpus,
                        timeout_s=args.timeout_s, job_name=args.job_name,
                        abaqus_command=args.abaqus_command)
    if args.command == "run-batch":
        from pipeline.batch import run_batch
        return run_batch(args.cases, args.simulation, defaults_path=args.case_defaults,
                         work_root=args.work_root, workers=args.workers,
                         retry_failed=args.retry_failed, max_retries=args.max_retries,
                         force=args.force, runtime_path=args.runtime, cpus=args.cpus,
                         timeout_s=args.timeout_s, abaqus_command=args.abaqus_command)
    if args.command == "run-experiment":
        from pipeline.experiment import start_experiment
        return start_experiment(args.config)
    if args.command == "summarize-batch":
        from pipeline.batch import rebuild_summary
        return rebuild_summary(args.work_root)
    return _run_stage(args)


def _run_stage(args):
    """One stage, inside the case directory the run-case layout defines."""
    from pipeline import abaqus
    from pipeline import extract as extract_module
    from pipeline.build import build
    from pipeline.common import read_json, safe_id
    from pipeline.mesh import load_case, run_mesh
    from pipeline.run_case import set_aside

    case = load_case(args.case)
    case_id = safe_id(case["case_id"])
    work_dir = Path(args.work_root) / case_id
    mesh_dir, deck_dir = work_dir / "mesh", work_dir / "abaqus"
    if args.command == "mesh":
        if args.force:
            set_aside(mesh_dir, "cli")
        return run_mesh(args.case, mesh_dir, print)
    if args.command == "mesh-datacheck":
        return abaqus.run_mesh_datacheck(read_json(mesh_dir / "mesh_result.json"),
                                         abaqus_command=args.abaqus_command, cpus=args.cpus,
                                         timeout_s=args.timeout_s, runtime_path=args.runtime)
    if args.command == "build":
        if args.force:
            set_aside(deck_dir, "cli")
        mesh_result = read_json(mesh_dir / "mesh_result.json")
        return build(mesh_result["npz"], mesh_result["report"], mesh_result["pairs_csv"],
                     args.simulation, deck_dir)
    if args.command == "datacheck":
        return abaqus.run_datacheck(deck_dir, abaqus_command=args.abaqus_command,
                                    job_name=args.job_name, cpus=args.cpus,
                                    timeout_s=args.timeout_s, runtime_path=args.runtime)
    if args.command == "solve":
        return abaqus.run_solve(deck_dir, abaqus_command=args.abaqus_command,
                                job_name=args.job_name, cpus=args.cpus,
                                timeout_s=args.timeout_s, runtime_path=args.runtime)
    return extract_module.extract(deck_dir, work_dir / "results", case_id=case_id,
                                  runtime_path=args.runtime,
                                  abaqus_command=args.abaqus_command,
                                  timeout_s=args.timeout_s or 3600, log=print,
                                  odb_path=getattr(args, "odb", None))


def _run_qa_history(args):
    from pipeline.common import write_json
    from pipeline.curve_qa import assess, load_policy, read_history_csv
    if Path(args.out).exists():
        raise PipelineError("OUTPUT_EXISTS", "Use a new QA output path.")
    columns = read_history_csv(args.csv)
    assessment = assess(columns, args.height_mm, args.area_mm2, args.reaction_sign,
                        load_policy(args.policy))
    write_json(args.out, assessment)
    return assessment


def main():
    result = _main()
    shown = result
    if isinstance(result, dict) and "rows" in result:
        # A batch result can hold 20k rows: never print them all.
        shown = {key: value for key, value in result.items() if key != "rows"}
    print(json.dumps(shown, indent=2, ensure_ascii=False, allow_nan=False, default=str))
    if isinstance(result, dict) and result.get("status") in (
            "CURVE_QA_FAILED", "DATACHECK_FAILED", "SOLVE_FAILED",
            "DATACHECK_COMPLETED_WITH_WARNINGS", "SOLVE_COMPLETED_WITH_WARNINGS",
            "VENDOR_VALIDATION_FAILED"):
        return 3  # Non-clean result: the report was written, review is needed.
    if isinstance(result, dict) and result.get("FAILED"):
        return 3  # The batch finished but some cases failed; see failed_cases.jsonl.
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PipelineError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "code": getattr(exc, "code", "INPUT_OR_IO_ERROR"),
                          "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
