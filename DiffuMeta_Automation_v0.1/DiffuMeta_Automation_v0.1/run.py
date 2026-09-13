"""Run with ordinary Python 3.10+; --help lists the actually implemented commands."""
import argparse
import csv
import json
from pathlib import Path
import sys

from pipeline.common import PipelineError, atomic_json, read_json
from pipeline.mesher_adapter import STAGES, prepare as prepare_mesher

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description="DiffuMeta v0.1 architecture and preparation tools (no production solve command yet)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Print the complete planned pipeline and implementation status")
    p = sub.add_parser("prepare-mesher", help="Create a private mesher directory and exact command plan; do not execute it")
    p.add_argument("--case", default=str(ROOT / "config/cases/fig1.json"))
    p.add_argument("--environment", default=str(ROOT / "config/environment.example.json"))
    p.add_argument("--vendor", default=str(ROOT / "vendor/periodic_surface_mesher_v1.0"))
    p.add_argument("--out", required=True)
    p = sub.add_parser("prepare-fe", help="Validate mesh contract and write shell/PBC ingredients; no complete physical INP yet")
    p.add_argument("--npz", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--pairs", required=True)
    p.add_argument("--physics", default=str(ROOT / "config/physics.example.json"))
    p.add_argument("--material", default=str(ROOT / "config/materials/demo_surrogate.json"))
    p.add_argument("--out", required=True)
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
                                  "aligned history curve QA"],
                  "next": ["complete physical INP builder", "version-specific launcher and monitor",
                           "ODB contact/PBC/field extraction", "orchestration, reconciliation, acceptance and export"]}
    elif args.command == "prepare-mesher":
        result = prepare_mesher(args.vendor, args.case, args.environment, args.out)
    elif args.command == "prepare-fe":
        from pipeline.prepare_fe import prepare
        result = prepare(args.npz, args.report, args.pairs, args.physics, args.material, args.out)
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (PipelineError, ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "FAILED", "code": getattr(exc, "code", "INPUT_OR_IO_ERROR"), "message": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)
