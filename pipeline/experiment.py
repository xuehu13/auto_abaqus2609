"""production.json -> the EXISTING run_batch(). A thin user entry, nothing more.

This module is a config adapter, not a pipeline: it reads one commented total
config (config/experiments/production.json), splits it into the three documents
the current system already consumes (case defaults, simulation, runtime), writes
them plus the effective config snapshot into the batch directory for
provenance, and calls pipeline.batch.run_batch(). Mesh/build/abaqus/batch logic
is never duplicated here.

Comment convention: only WHOLE lines whose first non-blank characters are "//"
are ignored before standard json.loads. A "//" inside a string value is never
touched. No JSON5, no block comments, no third-party parser.
"""
from __future__ import annotations

import json
from pathlib import Path

from .batch import run_batch
from .common import PipelineError, finite, positive_int, read_json, require_keys, safe_id, \
    write_json, boolean

ROOT = Path(__file__).resolve().parents[1]

_EXPERIMENT_REQUIRED = ("experiment_id", "cases_file", "work_root", "workers",
                        "retry_failed", "max_retries", "force")
_TOP_LEVEL = ("experiment", "geometry", "mesh", "material", "shell", "pbc", "platen",
              "contact", "loading", "solver", "output", "runtime")
_RUNTIME_REQUIRED = ("abaqus", "cgal", "results", "datacheck", "solve")


def strip_line_comments(text):
    """Drop only whole lines whose first non-blank characters are "//"."""
    return "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("//"))


def load_production(path):
    """Read production.json: strip whole-line // comments, then standard json.loads."""
    path = Path(path)
    if not path.is_file():
        raise PipelineError("CONFIG_INVALID", "Experiment config not found: " + str(path))
    try:
        document = json.loads(strip_line_comments(
            path.read_text(encoding="utf-8-sig")))
    except ValueError as exc:
        raise PipelineError("CONFIG_INVALID",
                            "Experiment config is not valid JSON after removing whole-line "
                            "// comments: " + str(path) + " (" + str(exc) + ")") from exc
    return require_keys(document, path, _TOP_LEVEL, (), "experiment config")


def build_inputs(document, root=ROOT):
    """Split production.json into (paths, case defaults, simulation, runtime).

    Paths are resolved against ``root`` (the repository root, the same reference
    every other CLI option uses). Raises on unknown categories/keys and on a
    cases file that does not exist, so a typo fails before any Abaqus run."""
    root = Path(root)
    document = require_keys(document, "<production.json>", _TOP_LEVEL, (),
                            "experiment config")
    experiment = require_keys(document["experiment"], "<production.json>.experiment",
                              _EXPERIMENT_REQUIRED, (), "experiment.experiment")
    experiment_id = safe_id(experiment["experiment_id"])
    if experiment_id != experiment["experiment_id"]:
        raise PipelineError("CONFIG_INVALID",
                            "experiment.experiment_id must already be a safe directory "
                            "name, got " + repr(experiment["experiment_id"]))
    positive_int(experiment["workers"], "experiment.workers")
    for key in ("max_retries",):
        if isinstance(experiment[key], bool) or not isinstance(experiment[key], int) \
                or experiment[key] < 0:
            raise PipelineError("CONFIG_INVALID",
                                "experiment.%s must be an integer >= 0." % key)
    boolean(experiment["retry_failed"], "experiment.retry_failed")
    boolean(experiment["force"], "experiment.force")

    def rooted(value):
        candidate = Path(value)
        return candidate if candidate.is_absolute() else root / candidate

    cases_path = rooted(experiment["cases_file"])
    if not cases_path.is_file():
        raise PipelineError("CONFIG_INVALID",
                            "experiment.cases_file does not exist: " + str(cases_path))
    batch_dir = rooted(experiment["work_root"]) / experiment_id

    geometry = require_keys(document["geometry"], "<production.json>.geometry",
                            ("iso_level", "unit_cell_size_mm"), (), "experiment.geometry")
    finite(geometry["iso_level"], "geometry.iso_level")
    finite(geometry["unit_cell_size_mm"], "geometry.unit_cell_size_mm", positive=True)
    mesh = require_keys(document["mesh"], "<production.json>.mesh",
                        ("topology_sampling_intervals", "boundary_target_spacing_mm",
                         "cgal", "tolerances", "meshcheck"), (), "experiment.mesh")
    case_defaults = {"iso_level": geometry["iso_level"],
                     "unit_cell_size_mm": geometry["unit_cell_size_mm"],
                     "mesh": mesh}

    simulation_keys = ("material", "shell", "pbc", "platen", "contact", "loading",
                       "solver", "output")
    simulation = {key: document[key] for key in simulation_keys}
    runtime = require_keys(document["runtime"], "<production.json>.runtime",
                           _RUNTIME_REQUIRED, (), "experiment.runtime")
    return {"experiment_id": experiment_id, "cases_path": cases_path,
            "batch_dir": batch_dir, "workers": experiment["workers"],
            "retry_failed": experiment["retry_failed"],
            "max_retries": experiment["max_retries"], "force": experiment["force"],
            "case_defaults": case_defaults, "simulation": dict(simulation),
            "runtime": runtime}


def start_experiment(config_path, *, root=ROOT, run_batch_fn=run_batch, log=print):
    """The whole run-experiment command: read, map, snapshot, call run_batch."""
    document = load_production(config_path)
    inputs = build_inputs(document, root=root)
    batch_dir = inputs["batch_dir"]
    batch_dir.mkdir(parents=True, exist_ok=True)

    # Provenance snapshot: what this batch actually ran with. An existing file is
    # never overwritten — identical content is fine (resume), different content
    # means the user is reusing an experiment_id for a changed experiment.
    used_path = batch_dir / "production_used.json"
    if used_path.is_file():
        if read_json(used_path) != document:
            raise PipelineError("EXPERIMENT_ID_REUSE",
                                "%s already holds a DIFFERENT effective config for "
                                "experiment_id '%s'; keep provenance by choosing a new "
                                "experiment_id (or restore the old config)."
                                % (used_path, inputs["experiment_id"]))
    else:
        write_json(used_path, document)
    write_json(batch_dir / "case_defaults.json", inputs["case_defaults"])
    write_json(batch_dir / "simulation.json", inputs["simulation"])
    write_json(batch_dir / "runtime.json", inputs["runtime"])

    log("experiment %s: %d worker(s), cases from %s"
        % (inputs["experiment_id"], inputs["workers"], inputs["cases_path"]))
    log("effective config snapshots: %s" % batch_dir)
    return run_batch_fn(cases_path=inputs["cases_path"],
                        simulation_path=batch_dir / "simulation.json",
                        defaults_path=batch_dir / "case_defaults.json",
                        work_root=batch_dir,
                        workers=inputs["workers"],
                        retry_failed=inputs["retry_failed"],
                        max_retries=inputs["max_retries"],
                        force=inputs["force"],
                        runtime_path=batch_dir / "runtime.json",
                        log=log)
