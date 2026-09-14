"""Candidate Abaqus-only worker. Syntax checked here; requires local Abaqus ODB integration.

abaqus python abaqus_worker/export_history.py --odb job.odb --out regions.json
abaqus python abaqus_worker/export_history.py --odb job.odb --map region_map.json --out raw_history.json

Map format: {"step": "Compression", "requests": {
  "top": {"region": "EXACT KEY FROM regions.json", "variables": ["U3", "RF3"]},
  "energy": {"region": "EXACT KEY FROM regions.json", "variables": ["ALLIE", "ALLKE", "ALLAE"]}}}
Each history retains its OWN time axis. No invented region names, no silent missing variables.
"""
import argparse
import json
import os
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--odb", required=True)
    parser.add_argument("--map")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    if os.path.exists(args.out):
        raise RuntimeError("Output already exists; choose another attempt output.")
    from odbAccess import openOdb
    odb = openOdb(path=os.path.abspath(args.odb), readOnly=True)
    try:
        if not args.map:
            result = {"status": "REGION_INVENTORY_ONLY", "steps": {
                step_name: {key: list(region.historyOutputs.keys()) for key, region in step.historyRegions.items()}
                for step_name, step in odb.steps.items()}, "dataset_eligible": False}
        else:
            with open(args.map, encoding="utf-8-sig") as stream:
                mapping = json.load(stream)
            step = odb.steps[mapping["step"]]
            data = {}
            for alias, spec in mapping["requests"].items():
                region = step.historyRegions[spec["region"]]
                data[alias] = {name: [list(pair) for pair in region.historyOutputs[name].data]
                               for name in spec["variables"]}
                if any(not values for values in data[alias].values()):
                    raise RuntimeError("Empty history output in " + alias)
            result = {"status": "RAW_HISTORY_EXPORTED", "map": mapping, "histories": data,
                      "dataset_eligible": False, "note": "No contact/PBC/material/full-solve QA is performed by this worker."}
        result["odb_path"] = os.path.abspath(args.odb)
    finally:
        odb.close()
    out = os.path.abspath(args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=os.path.dirname(out), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, out)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


if __name__ == "__main__":
    main()
