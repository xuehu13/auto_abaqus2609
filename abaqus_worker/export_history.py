"""ODB history export worker. Runs under ABAQUS PYTHON, not under the Pixi env.

    abaqus python abaqus_worker/export_history.py --odb job.odb --out raw.json \
        --step Compression --node RP_TOP=9487 --node RP_X_CTRL=9484 \
        --energy ALLIE,ALLKE,ALLAE

It writes one raw JSON file and nothing else (no CSV, no interpretation): the
solver-agnostic result files are produced by pipeline/extract.py, so the numerics
stay in testable Python and this worker stays a thin odbAccess reader.

Rules: read-only; a missing variable is reported in "missing", never invented as a
zero series; duplicate history keys (Abaqus writes e.g. "ALLIE" and
"ALLIE (Repeated: ...)" when the same request is written twice) are inventoried and
the plain key is preferred.
"""
import argparse
import json
import os
import sys

from odbAccess import openOdb  # noqa: E402  (Abaqus Python only)


def _series(region, variable):
    """Data of ``variable`` in a history region, preferring the plainest key."""
    if region is None:
        return None, []
    keys = sorted(region.historyOutputs.keys())
    exact = [key for key in keys if key == variable]
    plain = [key for key in keys if key.split(" (")[0].strip() == variable and "(" not in key]
    loose = [key for key in keys if key.split(" (")[0].strip() == variable]
    chosen = (exact or plain or loose or [None])[0]
    if chosen is None:
        return None, keys
    data = [[float(t), float(v)] for t, v in region.historyOutputs[chosen].data]
    return chosen, data


def _node_region(step, label):
    suffix = "." + str(label)
    for name in sorted(step.historyRegions.keys()):
        if name.startswith("Node") and name.endswith(suffix):
            return name
    return None


def _whole_model_region(step, variable):
    for name in sorted(step.historyRegions.keys()):
        region = step.historyRegions[name]
        keys = region.historyOutputs.keys()
        if any(key.split(" (")[0].strip() == variable for key in keys):
            return name
    return None


def main():
    parser = argparse.ArgumentParser(description="Export ODB history output as raw JSON.")
    parser.add_argument("--odb", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--step", default="Compression")
    parser.add_argument("--node", action="append", default=[],
                        help="NAME=NODE_LABEL, repeatable")
    parser.add_argument("--node-variables", default="U3,RF3")
    parser.add_argument("--energy", default="ALLIE,ALLKE,ALLAE")
    args = parser.parse_args()
    if os.path.exists(args.out):
        raise RuntimeError("Output already exists: " + args.out)
    node_variables = [name.strip() for name in args.node_variables.split(",") if name.strip()]
    energy_variables = [name.strip() for name in args.energy.split(",") if name.strip()]
    odb = openOdb(path=os.path.abspath(args.odb), readOnly=True)
    try:
        step = odb.steps[args.step]
        result = {"status": "RAW_HISTORY_EXPORTED", "odb": os.path.abspath(args.odb),
                  "step": args.step, "frames": len(step.frames),
                  "frame_times": [float(frame.frameValue) for frame in step.frames],
                  "history_regions": {name: sorted(region.historyOutputs.keys())
                                      for name, region in sorted(step.historyRegions.items())},
                  "nodes": {}, "energy": {}, "missing": {"nodes": [], "energy": []},
                  "chosen_keys": {}}
        for entry in args.node:
            if "=" not in entry:
                raise RuntimeError("--node must be NAME=NODE_LABEL: " + repr(entry))
            name, label = entry.split("=", 1)
            region_name = _node_region(step, label.strip())
            series = {}
            for variable in node_variables:
                key, data = _series(step.historyRegions[region_name] if region_name else None,
                                    variable)
                if key is None or not data:
                    result["missing"]["nodes"].append(name + "." + variable)
                    continue
                series[variable] = data
                result["chosen_keys"][name + "." + variable] = key
            result["nodes"][name] = {"region": region_name, "series": series}
        for variable in energy_variables:
            region_name = _whole_model_region(step, variable)
            key, data = _series(step.historyRegions[region_name] if region_name else None,
                                variable)
            if key is None or not data:
                result["missing"]["energy"].append(variable)
                continue
            result["energy"][variable] = data
            result["chosen_keys"][variable] = key
            result.setdefault("energy_region", region_name)
    finally:
        odb.close()
    with open(args.out, "w") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print("exported raw history:", args.out)
    print("frames:", result["frames"], "| nodes:", sorted(result["nodes"]),
          "| energy:", sorted(result["energy"]), "| missing:", result["missing"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:            # Abaqus Python: report and exit non-zero
        sys.stderr.write("EXPORT FAILED: %s: %s\n" % (type(exc).__name__, exc))
        raise SystemExit(1)
