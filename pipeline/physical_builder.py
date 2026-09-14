"""Physical build scaffold: reuse verified ingredients, own the manifest contract.

BUILD only proves what is assembled here. This stage validates input and
numerics contracts, reuses the frozen prepare-fe ingredients, renders the
material/section block and records the model identity. The remaining writer
steps are still explicitly NOT_IMPLEMENTED, so a successful build leaves no
physical.inp and claims no Abaqus validation.
"""
from __future__ import annotations

from pathlib import Path

from .common import (PipelineError, atomic_json, atomic_text, digest, file_hash,
                     read_json, reserve_directory)
from .prepare_fe import prepare as prepare_ingredients

_BUILDER_ID = "physical-builder-scaffold-v1"
_INGREDIENT_FILES = ("shell_mesh.inc", "lateral_pbc.inc", "pbc_map.json", "model_inputs.json")
_MATERIAL_BLOCK = "material_section.inc"
_NUMERICS_REQUIRED = ("schema_version", "procedure", "application", "nlgeom",
                      "initial_increment_s", "minimum_increment_s", "maximum_increment_s",
                      "maximum_increments", "automatic_stabilization", "cpus_per_job")


def _require_inputs(paths):
    missing = [str(p) for p in paths if not Path(p).is_file()]
    if missing:
        raise PipelineError("INPUT_MISSING", "Required input files are missing: " + ", ".join(missing))


def _load_numerics(path):
    numerics = read_json(path)
    missing = [key for key in _NUMERICS_REQUIRED if key not in numerics]
    if missing:
        raise PipelineError("CONFIG_INVALID", "numerics config lacks required keys: " + ", ".join(missing))
    # A valid Abaqus procedure this writer does not support yet is NOT a config error.
    if numerics["procedure"] != "dynamic_implicit" or numerics["application"] != "moderate_dissipation":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Only dynamic implicit with moderate dissipation is wired into the builder; "
                            "the requested procedure/application is valid Abaqus usage but unsupported here.")
    if numerics["nlgeom"] is not True:
        raise PipelineError("NOT_IMPLEMENTED",
                            "nlgeom=false is valid Abaqus usage but this writer only supports the "
                            "finite-strain compression contract.")
    if not isinstance(numerics["automatic_stabilization"], bool):
        raise PipelineError("CONFIG_INVALID", "automatic_stabilization must be a boolean.")
    increments = (numerics["initial_increment_s"], numerics["minimum_increment_s"],
                  numerics["maximum_increment_s"])
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 for v in increments)
            or not numerics["minimum_increment_s"] <= numerics["initial_increment_s"]
            <= numerics["maximum_increment_s"]):
        raise PipelineError("CONFIG_INVALID", "Increments must satisfy 0 < minimum <= initial <= maximum.")
    for key in ("maximum_increments", "cpus_per_job"):
        value = numerics[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise PipelineError("CONFIG_INVALID", key + " must be a positive integer.")
    return numerics


# ---------------------------------------------------------------------------
# Writer interfaces (M1-2 .. M1-9). Responsibilities are fixed here only; each
# milestone implements one function. They must never silently emit placeholder
# keyword blocks. Only implemented functions are called by build().
# ---------------------------------------------------------------------------

def _fmt(value):
    """Deterministic shortest round-trip float text: identical input, identical block."""
    return repr(float(value))


def _render_material_section(material, manifest):
    """Render Material/Density/Elastic/Plastic and the homogeneous shell section.

    Keyword syntax follows the validated hand model Fig1_Compression.inp. The
    material dict is the prepare_fe-validated value from ingredients/
    model_inputs.json -- the single source of truth; this renderer only makes a
    defensive structural check plus the unsupported-type decision and never
    re-validates ranges. The thickness is inherited via the manifest and is
    never recomputed. Simpson integration with five thickness points is the
    current builder baseline, not an immutable research parameter. Only
    physics-affecting keywords plus stable generation comments go into the
    block; research data policy metadata stays in the manifest.
    """
    if material.get("type") != "elastic_plastic_table":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Material type " + repr(material.get("type")) + " is valid Abaqus usage "
                            "but this writer only supports elastic_plastic_table.")
    try:
        density = float(material["density_tonne_mm3"])
        young = float(material["E_MPa"])
        poisson = float(material["nu"])
        table = [(float(row[0]), float(row[1])) for row in material["plastic_table_MPa_strain"]]
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise PipelineError("CONFIG_INVALID",
                            "Defensive structural check failed: the prepare_fe-validated material "
                            "does not contain a usable density/E/nu/plastic table.") from exc
    lines = [
        "** Material/section block rendered by physical-builder (M1-2);",
        "** keyword syntax baseline: the validated hand model Fig1_Compression.inp.",
        "*Material, name=MAT_SHELL",
        "*Density",
        " " + _fmt(density) + ",",
        "*Elastic",
        _fmt(young) + ", " + _fmt(poisson),
        "*Plastic",
    ]
    lines.extend(_fmt(stress) + ", " + _fmt(strain) for stress, strain in table)
    lines.extend([
        "*Shell Section, elset=SHELL_ALL, material=MAT_SHELL",
        _fmt(manifest["thickness_mm"]) + ", 5",
        "** Homogeneous shell section, Simpson integration with 5 thickness points;",
        "** this is the current builder baseline, not an immutable research parameter.",
    ])
    return "\n".join(lines) + "\n"


def _render_rigid_platens(physics, manifest):
    """R3D4 platens, reference points and rigid body keywords above/below the cell."""
    raise PipelineError("NOT_IMPLEMENTED", "Rigid platen rendering is not implemented yet.")


def _render_boundary_conditions(physics, manifest):
    """Platen BCs and the lateral macro stretch DOF handling around the PBC RPs."""
    raise PipelineError("NOT_IMPLEMENTED", "Boundary condition rendering is not implemented yet.")


def _render_contact(physics, manifest):
    """General contact semantics (normal/tangential/shell self contact) from the physics profile."""
    raise PipelineError("NOT_IMPLEMENTED", "Contact rendering is not implemented yet.")


def _render_step_and_loading(physics, numerics, manifest):
    """Dynamic implicit step, smooth step amplitude and the target displacement load."""
    raise PipelineError("NOT_IMPLEMENTED", "Step/loading rendering is not implemented yet.")


def _render_outputs(physics, manifest):
    """History/field output requests, each history variable keeping its own time axis."""
    raise PipelineError("NOT_IMPLEMENTED", "Output request rendering is not implemented yet.")


def _assemble_physical_inp(sections, output):
    """Assemble rendered keyword blocks into the final physical.inp (atomic publish)."""
    raise PipelineError("NOT_IMPLEMENTED", "Final INP assembly is not implemented yet.")


def _validate_static_model(folder, manifest):
    """Static checks over an assembled model: includes, labels, sets and target consistency."""
    raise PipelineError("NOT_IMPLEMENTED", "Static model validation is not implemented yet.")


def build(npz, report, pairs, physics_path, material_path, numerics_path, output):
    """Validate contracts, reuse prepare-fe ingredients and write the partial build manifest.

    Input and numerics errors are raised before the attempt directory is created,
    so simple mistakes leave no empty attempts. Failures inside the real
    ingredient preparation keep the attempt as evidence.
    """
    _require_inputs((npz, report, pairs, physics_path, material_path, numerics_path))
    numerics = _load_numerics(numerics_path)
    folder = reserve_directory(output)
    ingredients = folder / "ingredients"
    prepare_ingredients(npz, report, pairs, physics_path, material_path, ingredients)
    model_inputs = read_json(ingredients / "model_inputs.json")
    blocks_dir = folder / "blocks"
    blocks_dir.mkdir()
    atomic_text(blocks_dir / _MATERIAL_BLOCK, _render_material_section(model_inputs["material"], model_inputs))
    material_block_sha = file_hash(blocks_dir / _MATERIAL_BLOCK)
    scaffold_key = digest({"model_key": model_inputs["model_key"], "numerics": numerics,
                           "numerics_sha256": file_hash(numerics_path), "builder": _BUILDER_ID})
    manifest = {
        "schema_version": 1,
        "status": "PHYSICAL_BUILD_PARTIAL",
        "builder": _BUILDER_ID,
        "scaffold_key": scaffold_key,
        "build_key": digest({"scaffold_key": scaffold_key, "builder": _BUILDER_ID,
                             "blocks": {"material_section": material_block_sha}}),
        "identity": {"model_key": model_inputs["model_key"],
                     "physics_profile_id": model_inputs["physics"].get("profile_id"),
                     "material_id": model_inputs["material"].get("material_id"),
                     "note": "Trusted identity is the model_key/scaffold_key digest over full config "
                             "content and source hashes; profile_id/material_id are readable metadata."},
        "mesh_source_hashes": model_inputs["mesh_files"],
        "physics": model_inputs["physics"],
        "material": model_inputs["material"],
        "numerics": numerics,
        "numerics_sha256": file_hash(numerics_path),
        "L_mm": model_inputs["L_mm"],
        "A0_mm2": model_inputs["A0_mm2"],
        "surface_area_mm2": model_inputs["surface_area_mm2"],
        "thickness_mm": model_inputs["thickness_mm"],
        "target_displacement_mm": model_inputs["target_displacement_mm"],
        "shell_nodes": model_inputs["shell_nodes"],
        "shell_elements": model_inputs["shell_elements"],
        "equation_count": model_inputs["equation_count"],
        "labels": model_inputs["labels"],
        "ingredients": {"dir": "ingredients", "files": list(_INGREDIENT_FILES)},
        "blocks": {"dir": "blocks", "material_section": {
            "path": "blocks/" + _MATERIAL_BLOCK, "sha256": material_block_sha,
            "material_type": model_inputs["material"]["type"],
            "material_id": model_inputs["material"].get("material_id"),
            "allow_production_dataset": model_inputs["material"].get("allow_production_dataset"),
            "thickness_mm": model_inputs["thickness_mm"],
            "integration_rule": "simpson", "integration_points": 5}},
        "implemented_stages": ["input contract checks", "numerics contract checks",
                               "ingredient reuse from prepare-fe", "model manifest",
                               "material/section block rendering"],
        "missing_stages": ["rigid platens and reference points",
                           "boundary conditions", "contact", "step and loading", "output requests",
                           "physical.inp assembly", "static model validation", "physical datacheck",
                           "solve", "ODB QA"],
        "dataset_eligible": False,
        "warning": "Partial physical build: keyword blocks are rendered but no physical.inp is "
                   "assembled and no Abaqus validation was performed.",
    }
    atomic_json(folder / "model_manifest.json", manifest)
    return manifest