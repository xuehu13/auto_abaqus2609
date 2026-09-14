"""Physical build scaffold: reuse verified ingredients, own the manifest contract.

BUILD only proves what is assembled here. This stage validates input and
numerics contracts, reuses the frozen prepare-fe ingredients, renders the
material/section and rigid-platen blocks and records the model identity. The
remaining writer steps are still explicitly NOT_IMPLEMENTED, so a successful
build leaves no physical.inp and claims no Abaqus validation.
"""
from __future__ import annotations

import math
from pathlib import Path

from .common import (PipelineError, atomic_json, atomic_text, digest, file_hash,
                     read_json, reserve_directory)
from .prepare_fe import prepare as prepare_ingredients

_BUILDER_ID = "physical-builder-scaffold-v1"
_INGREDIENT_FILES = ("shell_mesh.inc", "lateral_pbc.inc", "pbc_map.json", "model_inputs.json")
_MATERIAL_BLOCK = "material_section.inc"
_RIGID_BLOCK = "rigid_platens.inc"
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


def _platen_plan(physics, manifest):
    """Resolve config-driven platen geometry and the label-safe assignment plan.

    No Fig.1 numbers are hardcoded: geometry comes from physics["platens"] and
    manifest["L_mm"], every label from manifest["labels"]. The plan reproduces
    the validated hand model: one deterministic grid per platen, centered on the
    cell xy center, bottom at z=0 and top at z=L.
    """
    platen = physics["platens"]
    if platen.get("type") != "R3D4" or platen.get("initial_z") != "0_and_L":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Platen type " + repr(platen.get("type")) + " with initial_z "
                            + repr(platen.get("initial_z")) + " is valid Abaqus usage but this "
                            "writer only supports R3D4 platens at z=0 and z=L.")
    width_factor = platen.get("width_factor")
    mesh_size = platen.get("mesh_size_mm")
    for name, value in (("width_factor", width_factor), ("mesh_size_mm", mesh_size)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) \
                or not math.isfinite(value) or value <= 0:
            raise PipelineError("CONFIG_INVALID", name + " must be a positive finite number.")
    L = float(manifest["L_mm"])
    width = width_factor * L
    intervals = width / mesh_size
    rounded = round(intervals)
    if rounded < 1 or not math.isclose(intervals, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise PipelineError("NOT_IMPLEMENTED",
                            "This builder requires the platen width (" + _fmt(width) + " mm) to be an "
                            "exact integer multiple of mesh_size_mm (" + _fmt(mesh_size) + " mm); it "
                            "will not silently round the mesh size.")
    intervals = int(rounded)
    labels = manifest["labels"]
    rp_labels = {key: int(labels[key]) for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")}
    shell_nodes, shell_elements = int(manifest["shell_nodes"]), int(manifest["shell_elements"])
    first_node, first_element = int(labels["first_plate_node"]), int(labels["first_plate_element"])
    per_side = intervals + 1
    nodes_per_platen, elements_per_platen = per_side ** 2, intervals ** 2
    # Label safety audit: prove the assignment is collision free before rendering.
    if len(set(rp_labels.values())) != 4:
        raise PipelineError("LABEL_CONFLICT", "The four control/reference node labels are not distinct.")
    if any(label <= shell_nodes for label in rp_labels.values()):
        raise PipelineError("LABEL_CONFLICT", "Control/reference node labels must all lie above the shell nodes.")
    bottom_nodes = (first_node, first_node + nodes_per_platen - 1)
    top_nodes = (bottom_nodes[1] + 1, bottom_nodes[1] + nodes_per_platen)
    bottom_elements = (first_element, first_element + elements_per_platen - 1)
    top_elements = (bottom_elements[1] + 1, bottom_elements[1] + elements_per_platen)
    if min(bottom_nodes) <= shell_nodes or min(top_nodes) <= max(bottom_nodes):
        raise PipelineError("LABEL_CONFLICT", "Plate node ranges overlap the shell nodes or each other.")
    if min(bottom_elements) <= shell_elements or min(top_elements) <= max(bottom_elements):
        raise PipelineError("LABEL_CONFLICT", "Plate element ranges overlap the shell elements or each other.")
    if any(rp in range(bottom_nodes[0], top_nodes[1] + 1) for rp in rp_labels.values()):
        raise PipelineError("LABEL_CONFLICT", "A control/reference label falls inside the plate node ranges.")
    return {
        "element_type": platen["type"], "L": L, "width": width, "mesh_size": float(mesh_size),
        "intervals": intervals, "per_side_nodes": per_side,
        "nodes_per_platen": nodes_per_platen, "elements_per_platen": elements_per_platen,
        "x": (L / 2 - width / 2, L / 2 + width / 2), "y": (L / 2 - width / 2, L / 2 + width / 2),
        "rp_labels": rp_labels,
        "rp_coords": {"rp_bottom": (L / 2, L / 2, 0.0), "rp_top": (L / 2, L / 2, L),
                      "rp_x": (1.5 * L, L / 2, L / 2), "rp_y": (L / 2, 1.5 * L, L / 2)},
        "bottom_nodes": bottom_nodes, "top_nodes": top_nodes,
        "bottom_elements": bottom_elements, "top_elements": top_elements,
    }


def _render_rigid_platens(physics, manifest):
    """Render control nodes, NSETs, both rigid platens and the two *Rigid Body definitions.

    Semantics baseline: the validated hand model Fig1_Compression.inp instances
    one RigidPlate part twice with translation only, so bottom and top share the
    same deterministic local connectivity and both carry +Z element normals
    (normal_policy=baseline_shared_connectivity_plus_z_both, pending contact-side
    validation at M1-4). rp_x/rp_y are PBC macro control nodes and belong to no
    rigid body. No Boundary/Surface/Contact/Step/Loading/Output keywords are
    emitted here.
    """
    plan = _platen_plan(physics, manifest)
    n, per = plan["intervals"], plan["per_side_nodes"]
    x0, y0 = plan["x"][0], plan["y"][0]
    step = plan["width"] / n
    node_labels, coords = plan["rp_labels"], plan["rp_coords"]
    element_type = plan["element_type"]

    def grid_lines(first_label, z):
        lines, label = [], first_label
        for row in range(per):
            y = y0 + row * step
            for col in range(per):
                lines.append("%d, %s, %s, %s" % (label, _fmt(x0 + col * step), _fmt(y), _fmt(z)))
                label += 1
        return lines

    def element_lines(first_label, first_node):
        lines, label = [], first_label
        for row in range(n):
            for col in range(n):
                a = first_node + row * per + col
                lines.append("%d, %d, %d, %d, %d" % (label, a, a + 1, a + per + 1, a + per))
                label += 1
        return lines

    lines = [
        "** Rigid platens and control/reference nodes rendered by physical-builder (M1-3a).",
        "** Semantics baseline: hand model Fig1_Compression.inp instances one RigidPlate part",
        "** twice with translation only, so bottom and top share the same local connectivity",
        "** and both carry +Z element normals; contact-side validation is deferred to M1-4.",
        "** RP_X_CTRL/RP_Y_CTRL are PBC macro control nodes and belong to no rigid body.",
        "*Node",
    ]
    for key in ("rp_x", "rp_y", "rp_bottom", "rp_top"):
        lines.append("%d, %s, %s, %s" % (node_labels[key], *(_fmt(v) for v in coords[key])))
    lines.extend(["*Nset, nset=RP_X_CTRL", "%d," % node_labels["rp_x"],
                  "*Nset, nset=RP_Y_CTRL", "%d," % node_labels["rp_y"],
                  "*Nset, nset=RP_BOTTOM", "%d," % node_labels["rp_bottom"],
                  "*Nset, nset=RP_TOP", "%d," % node_labels["rp_top"],
                  "*Node"])
    lines.extend(grid_lines(plan["bottom_nodes"][0], 0.0))
    lines.append("*Element, type=%s, elset=PLATE_BOTTOM" % element_type)
    lines.extend(element_lines(plan["bottom_elements"][0], plan["bottom_nodes"][0]))
    lines.extend(["*Nset, nset=PLATE_BOTTOM_NODES, generate",
                  "%d, %d, 1" % plan["bottom_nodes"],
                  "*Node"])
    lines.extend(grid_lines(plan["top_nodes"][0], plan["L"]))
    lines.append("*Element, type=%s, elset=PLATE_TOP" % element_type)
    lines.extend(element_lines(plan["top_elements"][0], plan["top_nodes"][0]))
    lines.extend(["*Nset, nset=PLATE_TOP_NODES, generate",
                  "%d, %d, 1" % plan["top_nodes"],
                  "*Rigid Body, ref node=%d, elset=PLATE_BOTTOM" % node_labels["rp_bottom"],
                  "*Rigid Body, ref node=%d, elset=PLATE_TOP" % node_labels["rp_top"]])
    return "\n".join(lines) + "\n"


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
    rigid_plan = _platen_plan(model_inputs["physics"], model_inputs)
    atomic_text(blocks_dir / _RIGID_BLOCK, _render_rigid_platens(model_inputs["physics"], model_inputs))
    rigid_block_sha = file_hash(blocks_dir / _RIGID_BLOCK)
    scaffold_key = digest({"model_key": model_inputs["model_key"], "numerics": numerics,
                           "numerics_sha256": file_hash(numerics_path), "builder": _BUILDER_ID})
    manifest = {
        "schema_version": 1,
        "status": "PHYSICAL_BUILD_PARTIAL",
        "builder": _BUILDER_ID,
        "scaffold_key": scaffold_key,
        "build_key": digest({"scaffold_key": scaffold_key, "builder": _BUILDER_ID,
                             "blocks": {"material_section": material_block_sha,
                                        "rigid_platens": rigid_block_sha}}),
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
        "blocks": {"dir": "blocks",
            "material_section": {
                "path": "blocks/" + _MATERIAL_BLOCK, "sha256": material_block_sha,
                "material_type": model_inputs["material"]["type"],
                "material_id": model_inputs["material"].get("material_id"),
                "allow_production_dataset": model_inputs["material"].get("allow_production_dataset"),
                "thickness_mm": model_inputs["thickness_mm"],
                "integration_rule": "simpson", "integration_points": 5},
            "rigid_platens": {
                "path": "blocks/" + _RIGID_BLOCK, "sha256": rigid_block_sha,
                "element_type": rigid_plan["element_type"],
                "width_mm": rigid_plan["width"], "mesh_size_mm": rigid_plan["mesh_size"],
                "intervals_per_side": rigid_plan["intervals"],
                "nodes_per_platen": rigid_plan["nodes_per_platen"],
                "elements_per_platen": rigid_plan["elements_per_platen"],
                "bottom_z_mm": 0.0, "top_z_mm": rigid_plan["L"],
                "xy_extent_mm": {"x_min_mm": rigid_plan["x"][0], "x_max_mm": rigid_plan["x"][1],
                                 "y_min_mm": rigid_plan["y"][0], "y_max_mm": rigid_plan["y"][1]},
                "rp_labels": rigid_plan["rp_labels"],
                "node_ranges": {"bottom": list(rigid_plan["bottom_nodes"]),
                                "top": list(rigid_plan["top_nodes"])},
                "element_ranges": {"bottom": list(rigid_plan["bottom_elements"]),
                                   "top": list(rigid_plan["top_elements"])},
                "normal_policy": "baseline_shared_connectivity_plus_z_both",
                "normal_policy_status": "baseline_reproduction_pending_contact_validation"}},
        "implemented_stages": ["input contract checks", "numerics contract checks",
                               "ingredient reuse from prepare-fe", "model manifest",
                               "material/section block rendering",
                               "rigid platens/reference points block rendering"],
        "missing_stages": ["boundary conditions", "contact", "step and loading", "output requests",
                           "physical.inp assembly", "static model validation", "physical datacheck",
                           "solve", "ODB QA"],
        "dataset_eligible": False,
        "warning": "Partial physical build: keyword blocks are rendered but no physical.inp is "
                   "assembled and no Abaqus validation was performed.",
    }
    atomic_json(folder / "model_manifest.json", manifest)
    return manifest