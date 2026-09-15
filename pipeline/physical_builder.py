"""Physical build: reuse verified ingredients, assemble physical.inp, validate statically.

BUILD only proves what is assembled here. This stage validates input and
numerics/outputs contracts, reuses the frozen prepare-fe ingredients, renders
the material/section, rigid-platen, boundary-condition, contact and step/output
blocks (M1-2..M1-6), assembles them into a top-level physical.inp through a
fixed include order (M1-7) and runs repository-owned static validation over the
assembled artifacts. A PASS means internal self-consistency only: Abaqus
keyword acceptance (Physical Data Check), solve and ODB QA are NOT performed or
claimed, and dataset_eligible stays false.
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
_BC_BLOCK = "boundary_conditions.inc"
_CONTACT_BLOCK = "contact.inc"
_STEP_LOADING_BLOCK = "step_loading.inc"
_STEP_END_BLOCK = "step_end.inc"
_OUTPUTS_BLOCK = "outputs.inc"
_NUMERICS_REQUIRED = ("schema_version", "procedure", "application", "nlgeom",
                      "initial_acceleration_policy",
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
    if numerics["automatic_stabilization"]:
        raise PipelineError("NOT_IMPLEMENTED",
                            "automatic_stabilization=true is valid Abaqus usage but no stabilization "
                            "keyword rendering has been validated in this writer.")
    if not isinstance(numerics["initial_acceleration_policy"], str):
        raise PipelineError("CONFIG_INVALID", "initial_acceleration_policy must be a string.")
    if numerics["initial_acceleration_policy"] != "bypass":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Initial acceleration policy " + repr(numerics["initial_acceleration_policy"])
                            + " is valid Abaqus usage but this writer only supports bypass (initial=NO), "
                            "matching the hand baseline policy.")
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
    (normal_policy=baseline_shared_connectivity_plus_z_both, contact
    initialization validation deferred to the M2 physical data check). rp_x/rp_y
    are PBC macro control nodes and belong to no rigid body. No
    Boundary/Surface/Contact/Step/Loading/Output keywords are emitted here.
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
        "** and both carry +Z element normals; contact initialization validation is deferred",
        "** to the M2 physical data check.",
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
    """Render the model-level zero-valued platen constraints.

    Evidence baseline: hand model BC_BOTTOM_FIXED (RP_BOTTOM DOF1..6 = 0) and
    BC_TOP_GUIDE (RP_TOP DOF1,2,4,5,6 = 0; DOF3 free until the compression
    step). RP_X_CTRL/RP_Y_CTRL receive NO boundary: their DOF1/DOF2 are the
    lateral PBC macro control DOFs used by the equations. The nonzero U3
    loading and the amplitude belong to the future step/loading milestone, so
    this renderer must not read or emit any loading parameter.
    """
    if physics.get("boundary_mode") != "lateral_xy_platens":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Boundary mode " + repr(physics.get("boundary_mode")) + " is valid "
                            "Abaqus usage but this writer only supports lateral_xy_platens.")
    labels = manifest["labels"]
    try:
        rp = [int(labels[key]) for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")]
    except (KeyError, TypeError, ValueError) as exc:
        raise PipelineError("CONFIG_INVALID",
                            "Defensive label contract check failed: the four control/reference "
                            "labels must exist and be integers.") from exc
    if len(set(rp)) != 4:
        raise PipelineError("CONFIG_INVALID", "The four control/reference node labels are not distinct.")
    return "\n".join([
        "** Zero-valued platen constraints; nonzero compression is rendered later",
        "** by the step/loading milestone (top U3 intentionally left free here).",
        "** The two PBC macro control nodes receive no boundary, by hand-baseline evidence.",
        "** Bottom rigid platen fully fixed (hand baseline BC_BOTTOM_FIXED).",
        "*Boundary",
        "RP_BOTTOM, 1, 1",
        "RP_BOTTOM, 2, 2",
        "RP_BOTTOM, 3, 3",
        "RP_BOTTOM, 4, 4",
        "RP_BOTTOM, 5, 5",
        "RP_BOTTOM, 6, 6",
        "** Top rigid platen guide (hand baseline BC_TOP_GUIDE).",
        "*Boundary",
        "RP_TOP, 1, 1",
        "RP_TOP, 2, 2",
        "RP_TOP, 4, 4",
        "RP_TOP, 5, 5",
        "RP_TOP, 6, 6",
    ]) + "\n"


def _render_contact(physics, manifest):
    """Render the hand-baseline General Contact definition.

    Baseline policy (Fig1_Compression.inp): Abaqus/Standard General Contact over
    the ALL EXTERIOR self-contact domain with one global property assignment.
    The hand baseline's optional surface-interaction scalar data line (1.0,
    only relevant for 2D models or node-based contact pairs) is intentionally
    omitted: this model is 3D element-based, so that default scalar does not
    apply. No explicit surfaces, no contact-initialization keywords, and the OP
    parameter is not applicable in Abaqus/Standard here. Validation of the
    actual contact initialization belongs to the M2 data check.
    """
    contact = physics.get("contact")
    if not isinstance(contact, dict):
        raise PipelineError("CONFIG_INVALID", "physics.contact must be an object.")
    for key in ("normal", "allow_separation", "tangential", "friction", "slip_tolerance", "shell_self_contact"):
        if key not in contact:
            raise PipelineError("CONFIG_INVALID", "contact config lacks required key: " + key)
    if not isinstance(contact["normal"], str):
        raise PipelineError("CONFIG_INVALID", "contact.normal must be a string.")
    if not isinstance(contact["tangential"], str):
        raise PipelineError("CONFIG_INVALID", "contact.tangential must be a string.")
    if not isinstance(contact["allow_separation"], bool) or not isinstance(contact["shell_self_contact"], bool):
        raise PipelineError("CONFIG_INVALID", "contact.allow_separation and shell_self_contact must be booleans.")
    friction = contact["friction"]
    slip = contact["slip_tolerance"]
    for name, value in (("friction", friction), ("slip_tolerance", slip)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise PipelineError("CONFIG_INVALID", "contact." + name + " must be a finite number.")
    if friction < 0:
        raise PipelineError("CONFIG_INVALID", "contact.friction must be >= 0.")
    if slip <= 0:
        raise PipelineError("CONFIG_INVALID", "contact.slip_tolerance must be > 0.")
    # Supported policy of this baseline writer; alternatives are valid Abaqus
    # modelling choices but this writer implements exactly one policy.
    if contact["normal"] != "hard":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Normal behavior " + repr(contact["normal"]) + " is valid Abaqus usage "
                            "but this writer only supports hard pressure-overclosure.")
    if contact["allow_separation"] is not True:
        raise PipelineError("NOT_IMPLEMENTED",
                            "allow_separation=false (NO SEPARATION) is valid Abaqus usage but the "
                            "ALL EXTERIOR baseline writer only supports the default separation "
                            "semantics expressed by omitting NO SEPARATION.")
    if contact["tangential"] != "penalty":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Tangential policy " + repr(contact["tangential"]) + " is valid Abaqus "
                            "usage but this writer relies on the Standard default penalty/stiffness "
                            "friction semantics, matching the hand baseline.")
    if contact["shell_self_contact"] is not True:
        raise PipelineError("NOT_IMPLEMENTED",
                            "shell_self_contact=false is valid Abaqus usage but this writer uses the "
                            "ALL EXTERIOR self-contact domain and must not silently emit the same "
                            "domain with self-contact disabled.")
    return "\n".join([
        "** Contact definition rendered by physical-builder (M1-4).",
        "** Baseline policy: Abaqus/Standard General Contact with ALL EXTERIOR.",
        "** The hand baseline's optional surface-interaction scalar line (1.0, used only",
        "** for 2D models or node-based contact pairs) is intentionally omitted here:",
        "** this model is 3D element-based, so that default scalar does not apply.",
        "*Surface Interaction, name=ContactProp",
        "*Friction, slip tolerance=" + _fmt(slip),
        _fmt(friction) + ",",
        "*Surface Behavior, pressure-overclosure=HARD",
        "*Contact",
        "*Contact Inclusions, ALL EXTERIOR",
        "*Contact Property Assignment",
        ", , ContactProp",
    ]) + "\n"


def _render_step_and_loading(physics, numerics, manifest):
    """Render the compression step opening, its smooth-step amplitude and the
    RP_TOP U3 displacement loading.

    Baseline: hand model *Amplitude SMOOTH STEP + *Step Compression + *Dynamic
    MODERATE DISSIPATION with bypassed initial acceleration calculation. The
    amplitude endpoint equals the current step time period, so the relative
    amplitude 0 -> 1 spans the whole step for any time_period_s. Only the
    loading DOF (RP_TOP U3) is prescribed in-step; the zero-valued guide DOFs
    from the boundary block stay active under the default OP=MOD history
    semantics. The target displacement is the prepare_fe-verified manifest
    value and is never recomputed here. No Restart/Output/End Step keywords
    are emitted (outputs.inc and step_end.inc are separate blocks).
    """
    if physics.get("amplitude") != "smooth_step":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Amplitude type " + repr(physics.get("amplitude")) + " is valid Abaqus "
                            "usage but this writer only supports the smooth-step profile spanning "
                            "the entire current step.")
    period = physics.get("time_period_s")
    if not isinstance(period, (int, float)) or isinstance(period, bool) \
            or not math.isfinite(period) or period <= 0:
        raise PipelineError("CONFIG_INVALID", "physics.time_period_s must be a positive finite number.")
    target_u3 = manifest["target_displacement_mm"]
    subheading = "Compression: eps=%.6g, U3=%.6g mm, T=%.6g s" % (
        physics["target_compression_strain"], target_u3, period)
    return "\n".join([
        "*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP",
        "0.0, 0.0, " + _fmt(period) + ", 1.0",
        "*Step, name=Compression, nlgeom=YES, inc=%d" % numerics["maximum_increments"],
        subheading,
        "*Dynamic, application=MODERATE DISSIPATION, initial=NO",
        "%s, %s, %s, %s" % (_fmt(numerics["initial_increment_s"]), _fmt(period),
                            _fmt(numerics["minimum_increment_s"]), _fmt(numerics["maximum_increment_s"])),
        "*Boundary, amplitude=AMP_COMPRESSION",
        "RP_TOP, 3, 3, " + _fmt(target_u3),
    ]) + "\n"


def _render_step_end():
    """Render the step closing keyword; the future outputs block is placed before it."""
    return "*End Step\n"


def _load_outputs(path):
    """Load and validate the output request policy (Layer 1: ODB/restart writes).

    Runs before the attempt directory is created, so an invalid outputs config
    leaves no empty attempt. Only the Fig.1 baseline policy kinds are supported;
    alternatives are valid Abaqus usage and fail as NOT_IMPLEMENTED. Variable
    applicability is validated by Abaqus during the M2 physical data check and
    region existence by M1-7 static validation.
    """
    outputs = read_json(path)
    if not isinstance(outputs, dict):
        raise PipelineError("CONFIG_INVALID", "outputs config must be an object.")
    for key in ("schema_version", "profile_id", "restart", "field_groups", "history_groups"):
        if key not in outputs:
            raise PipelineError("CONFIG_INVALID", "outputs config lacks required key: " + key)
    version = outputs["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise PipelineError("CONFIG_INVALID", "outputs schema_version must be an integer.")
    if version != 1:
        raise PipelineError("NOT_IMPLEMENTED",
                            "Outputs schema version %s is structurally valid but this writer "
                            "implements schema 1." % version)
    if not isinstance(outputs["profile_id"], str) or not outputs["profile_id"].strip():
        raise PipelineError("CONFIG_INVALID", "outputs profile_id must be a non-empty string.")
    restart = outputs["restart"]
    if not isinstance(restart, dict) or not isinstance(restart.get("policy"), str):
        raise PipelineError("CONFIG_INVALID", "outputs.restart.policy must be a string.")
    if restart["policy"] != "disabled":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Restart policy " + repr(restart["policy"]) + " is valid Abaqus usage "
                            "but this writer only implements the disabled baseline (frequency=0).")
    for name in ("field_groups", "history_groups"):
        if not isinstance(outputs[name], list):
            raise PipelineError("CONFIG_INVALID", "outputs." + name + " must be a list.")
    # Empty group lists must not silently fall back to Abaqus default output:
    # "no explicit output request" re-enables procedure-specific PRESELECT.
    # Disabling an output channel is a legitimate future policy that needs its
    # own design and Data Check, so v1 refuses it as NOT_IMPLEMENTED.
    if not outputs["field_groups"]:
        raise PipelineError("NOT_IMPLEMENTED",
                            "Empty field_groups are not yet supported as an explicit "
                            "disabled-output policy; the writer must not rely on Abaqus default "
                            "output. Design and validate a field-disable policy separately.")
    if not outputs["history_groups"]:
        raise PipelineError("NOT_IMPLEMENTED",
                            "Empty history_groups are not yet supported as an explicit "
                            "disabled-output policy; the writer must not rely on Abaqus default "
                            "output. Design and validate a history-disable policy separately.")
    for group in outputs["field_groups"]:
        _validate_output_group(group, "field")
    for group in outputs["history_groups"]:
        _validate_output_group(group, "history")
    return outputs


def _validate_output_group(group, channel):
    if not isinstance(group, dict):
        raise PipelineError("CONFIG_INVALID", channel + " group must be an object.")
    schedule = group.get("schedule")
    if not isinstance(schedule, dict) or "type" not in schedule:
        raise PipelineError("CONFIG_INVALID", channel + " group schedule must be an object with a type.")
    if not isinstance(schedule["type"], str):
        raise PipelineError("CONFIG_INVALID", "schedule type must be a string.")
    if schedule["type"] != "every_n_increments":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Output schedule " + repr(schedule["type"]) + " is valid Abaqus usage "
                            "but this writer only implements every_n_increments; note that NUMBER "
                            "INTERVAL with TIME MARKS can change increment placement, so alternative "
                            "schedules are not treated as pure display parameters.")
    n = schedule.get("n")
    if isinstance(n, bool) or not isinstance(n, int) or n < 1:
        raise PipelineError("CONFIG_INVALID", "schedule n must be an integer >= 1.")
    mode = group.get("mode")
    requests = group.get("requests")
    if mode == "preselect":
        if requests is not None:
            raise PipelineError("CONFIG_INVALID", "A preselect group must not also define requests.")
        return
    if channel == "field":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Explicit field output requests are valid Abaqus usage but this writer "
                            "only implements the field PRESELECT baseline in v1.")
    if mode not in (None, "explicit"):
        raise PipelineError("CONFIG_INVALID", "history group mode " + repr(mode) + " is not part of "
                            "outputs schema 1.")
    if not isinstance(requests, list) or not requests:
        raise PipelineError("CONFIG_INVALID", "An explicit history group needs a non-empty requests list.")
    for request in requests:
        _validate_output_request(request, channel)


def _validate_output_request(request, channel):
    if not isinstance(request, dict):
        raise PipelineError("CONFIG_INVALID", channel + " request must be an object.")
    kind = request.get("kind")
    if not isinstance(kind, str):
        raise PipelineError("CONFIG_INVALID", channel + " request kind must be a string.")
    supported = ("energy", "node") if channel == "history" else ()
    if kind not in supported:
        raise PipelineError("NOT_IMPLEMENTED",
                            "Output request kind " + repr(kind) + " is valid Abaqus usage but this "
                            "writer only implements " + (", ".join(supported) or "none") + " in v1.")
    if request.get("mode") != "explicit":
        raise PipelineError("CONFIG_INVALID", channel + " request mode must be 'explicit' in v1.")
    region = request.get("region")
    if not isinstance(region, dict):
        raise PipelineError("CONFIG_INVALID", channel + " request region must be an object.")
    region_type = region.get("type")
    if not isinstance(region_type, str) or not region_type.strip():
        raise PipelineError("CONFIG_INVALID", "region.type must be a non-empty string.")
    if kind == "energy" and region_type != "whole_model":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Energy request region " + repr(region_type) + " is valid Abaqus usage "
                            "but this writer only implements whole-model energy.")
    if kind == "node" and region_type != "node_set":
        raise PipelineError("NOT_IMPLEMENTED",
                            "Node request region " + repr(region_type) + " is valid Abaqus usage "
                            "but this writer only implements node_set regions in v1.")
    name = region.get("name")
    if region_type != "whole_model" and (
            not isinstance(name, str) or not name.strip() or "\n" in name or "," in name):
        raise PipelineError("CONFIG_INVALID",
                            "region.name must be a non-empty string without newline or comma "
                            "for this region type.")
    variables = request.get("variables")
    if not isinstance(variables, list) or not variables:
        raise PipelineError("CONFIG_INVALID", "request variables must be a non-empty list.")
    for variable in variables:
        if not isinstance(variable, str) or not variable.strip() or "\n" in variable \
                or "," in variable or variable.strip().startswith("*"):
            raise PipelineError("CONFIG_INVALID",
                                "output variables must be non-empty strings without newline/comma "
                                "and must not start with '*': " + repr(variable))


def _render_outputs(outputs):
    """Render restart and field/history output requests (Layer 1: what is
    written to the ODB/restart file). The group-oriented config maps one-to-one
    onto *Output groups; PRESELECT is a group-level mode, not a request kind.
    The Dynamic omitted history PRESELECT frequency is rendered explicitly as
    its documented direct-INP effective default (every 10 increments). No
    extraction, dataset or visualization logic belongs here.
    """
    lines = ["*Restart, write, frequency=0"]
    for group in outputs["field_groups"]:
        lines.append("*Output, field, variable=PRESELECT, frequency=%d" % group["schedule"]["n"])
    for group in outputs["history_groups"]:
        if group.get("mode") == "preselect":
            lines.append("*Output, history, variable=PRESELECT, frequency=%d" % group["schedule"]["n"])
            continue
        lines.append("*Output, history, frequency=%d" % group["schedule"]["n"])
        for request in group["requests"]:
            if request["kind"] == "energy":
                lines.append("*Energy Output")
            else:
                lines.append("*Node Output, nset=%s" % request["region"]["name"])
            lines.append(", ".join(request["variables"]))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# M1-7: physical.inp assembly and repository-owned static validation.
#
# The static validator understands ONLY the deterministic keyword forms this
# repository itself generates (see the block renderers and prepare_fe). It is
# deliberately not a general Abaqus INP parser, and a PASS never claims that
# Abaqus accepted the deck: that judgement belongs to the M2 Physical Data
# Check and later real-ODB QA milestones.
# ---------------------------------------------------------------------------

_STATIC_INCLUDE_ORDER = (
    ("shell mesh (prepare-fe ingredient)", "ingredients/shell_mesh.inc"),
    ("material/section block (M1-2)", "blocks/material_section.inc"),
    ("rigid platens and control nodes (M1-3a)", "blocks/rigid_platens.inc"),
    ("lateral PBC equations (prepare-fe ingredient)", "ingredients/lateral_pbc.inc"),
    ("model-level boundary conditions (M1-3b)", "blocks/boundary_conditions.inc"),
    ("general contact (M1-4)", "blocks/contact.inc"),
    ("compression step and loading (M1-5)", "blocks/step_loading.inc"),
    ("output requests (M1-6)", "blocks/outputs.inc"),
    ("step close (M1-5)", "blocks/step_end.inc"),
)

_STATIC_ARTIFACTS = tuple(path for _, path in _STATIC_INCLUDE_ORDER) + (
    "ingredients/pbc_map.json", "ingredients/model_inputs.json", "physical.inp")

_MODEL_REGION_NODESETS = ("RP_X_CTRL", "RP_Y_CTRL", "RP_BOTTOM", "RP_TOP",
                          "PLATE_BOTTOM_NODES", "PLATE_TOP_NODES")
_MODEL_REGION_ELEMENTSETS = ("SHELL_ALL", "PLATE_BOTTOM", "PLATE_TOP")
# Output-style keywords must sit strictly inside the compression step.
_IN_STEP_OUTPUT_KEYWORDS = ("*restart", "*output", "*energy output",
                            "*node output", "*element output")
_BC_BLOCK_SOURCE = "blocks/boundary_conditions.inc"
_STEP_LOADING_SOURCE = "blocks/step_loading.inc"
_PBC_SOURCE = "ingredients/lateral_pbc.inc"
_OUTPUTS_SOURCE = "blocks/outputs.inc"


def _assemble_physical_inp(sections, output):
    """Assemble the top-level physical.inp as fixed-order *Include references.

    The deck stays a thin include graph over the deterministic artifacts; no
    keyword content is duplicated here. Include paths are attempt-relative with
    forward slashes (never absolute, never '..') and publication is atomic via
    atomic_text. Returns the published file's SHA256.
    """
    lines = [
        "** physical.inp assembled by physical-builder (M1-7).",
        "** Repository static validation only: this deck proves that the",
        "** deterministic blocks assembled here are internally self-consistent.",
        "** It does NOT claim Abaqus keyword-parser acceptance (that is the M2",
        "** Physical Data Check), solve success, ODB quality or dataset eligibility.",
        "** Fixed assembly order: shell mesh -> material/section -> rigid platens ->",
        "** lateral PBC -> model BCs -> contact -> step/loading -> outputs -> End Step.",
    ]
    lines.extend("*Include, input=" + path for _, path in sections)
    atomic_text(output, "\n".join(lines) + "\n")
    return file_hash(output)


def _keyword_sections(text):
    """Split generated keyword text into (keyword, params, data rows) sections.

    Handles exactly the deterministic forms this repository writes: '*'-keyword
    lines with comma-separated key=value parameters, '**' comments and plain
    comma-separated data rows. This is not a general Abaqus INP parser.
    """
    sections = []
    keyword, params, data = None, {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("**"):
            continue
        if line.startswith("*"):
            if keyword is not None:
                sections.append((keyword, params, data))
            parts = line.split(",")
            keyword = parts[0].strip().lower()
            params = {}
            for part in parts[1:]:
                if "=" in part:
                    key, value = part.split("=", 1)
                    params[key.strip().lower()] = value.strip()
                elif part.strip():
                    params[part.strip().lower()] = ""
            data = []
        elif keyword is not None:
            data.append([part.strip() for part in line.split(",")])
    if keyword is not None:
        sections.append((keyword, params, data))
    return sections


def _parse_includes(text):
    """Return the ordered *Include input paths of a top-level deck."""
    return [params.get("input", "") for keyword, params, _data in _keyword_sections(text)
            if keyword == "*include"]


def _is_unsafe_include_path(target):
    """Only attempt-relative forward-slash paths are allowed; anything else is unsafe."""
    if not target or target != target.strip() or "\\" in target or ":" in target:
        return True
    if target.startswith(("/", "~")):
        return True
    parts = target.split("/")
    return ".." in parts or "" in parts or "." in parts


def _scan_static_model(folder, include_paths):
    """Collect the assembled model's deterministic content for the static checks.

    Node/element definitions keep every occurrence so duplicate labels stay
    detectable by the checks; references are validated against the full
    definition sets. The deck list preserves the flattened include order used by
    the structural step checks.
    """
    folder = Path(folder)
    nodes, elements, nsets, elsets = {}, {}, {}, {}
    equations, boundaries, rigid_bodies, deck = [], [], [], []
    for rel in include_paths:
        text = (folder / rel).read_text(encoding="utf-8")
        for keyword, params, data in _keyword_sections(text):
            deck.append({"source": rel, "keyword": keyword, "params": params, "data": data})
            if keyword == "*node":
                for row in data:
                    nodes.setdefault(int(row[0]), []).append(rel)
            elif keyword == "*element":
                for row in data:
                    entry = {"elset": params.get("elset"),
                             "conn": [int(value) for value in row[1:]], "source": rel}
                    elements.setdefault(int(row[0]), []).append(entry)
                    if entry["elset"]:
                        elsets.setdefault(entry["elset"], []).append(int(row[0]))
            elif keyword in ("*nset", "*elset"):
                name = params.get("nset") or params.get("elset") or ""
                labels = (nsets if keyword == "*nset" else elsets).setdefault(name, [])
                if "generate" in params:
                    start, end, step = (int(value) for value in data[0][:3])
                    labels.extend(range(start, end + 1, step))
                else:
                    labels.extend(int(value) for row in data for value in row if value)
            elif keyword == "*equation":
                values = [value for row in data[1:] for value in row if value]
                terms = [(int(values[i]), int(values[i + 1]), float(values[i + 2]))
                         for i in range(0, len(values), 3)]
                equations.append({"source": rel, "terms": terms})
            elif keyword == "*boundary":
                rows = [(row[0], int(row[1]), int(row[2]),
                         float(row[3]) if len(row) > 3 and row[3] else None)
                        for row in data if row and row[0]]
                boundaries.append({"source": rel, "params": params, "rows": rows})
            elif keyword == "*rigid body":
                rigid_bodies.append({"source": rel, "params": params})
    return {"nodes": nodes, "elements": elements, "nsets": nsets, "elsets": elsets,
            "equations": equations, "boundaries": boundaries,
            "rigid_bodies": rigid_bodies, "deck": deck}


def _validate_static_model(folder, manifest):
    """Run the repository-owned static checks over an assembled attempt.

    Returns {check_name: {"status": "PASS"|"FAILED", ["details": ...]}}. The
    checks cover artifact integrity, the include graph, node/element label
    contracts, reference integrity, set/region existence, PBC reference
    consistency, the boundary/loading contract, step structure, target and
    time/amplitude consistency and output-region integrity. They deliberately
    do NOT judge physics, convergence or Abaqus acceptance.
    """
    folder = Path(folder)
    checks = {}

    def record(name, problems):
        checks[name] = {"status": "FAILED" if problems else "PASS"}
        if problems:
            checks[name]["details"] = list(problems)

    # A. artifact integrity: every expected file exists and every manifest
    # block SHA256 still matches the bytes on disk (tampering fails here).
    problems = []
    for rel in _STATIC_ARTIFACTS:
        if not (folder / rel).is_file():
            problems.append("missing artifact: " + rel)
    for key, block in manifest["blocks"].items():
        if key == "dir" or not isinstance(block, dict) or "path" not in block:
            continue
        path = folder / block["path"]
        if path.is_file() and file_hash(path) != block["sha256"]:
            problems.append("sha256 mismatch: " + block["path"])
    record("artifact_integrity", problems)

    # B. include graph of the top-level deck.
    problems = []
    inp = folder / "physical.inp"
    includes = _parse_includes(inp.read_text(encoding="utf-8")) if inp.is_file() else []
    expected_includes = [path for _, path in _STATIC_INCLUDE_ORDER]
    if includes != expected_includes:
        problems.append("include sequence mismatch, got: " + repr(includes))
    if len(set(includes)) != len(includes):
        problems.append("duplicate include entries")
    for target in includes:
        if _is_unsafe_include_path(target):
            problems.append("unsafe include path: " + repr(target))
        elif not (folder / target).is_file():
            problems.append("include target missing: " + target)
    record("include_graph", problems)

    try:
        # Follow the deck's actual include order whenever every target is safe
        # and present, so structural checks see the real assembled model; fall
        # back to the canonical order for missing/unsafe decks.
        if includes and all(not _is_unsafe_include_path(target)
                            and (folder / target).is_file() for target in includes):
            scan_order = includes
        else:
            scan_order = expected_includes
        model = _scan_static_model(folder, scan_order)
    except (OSError, ValueError, IndexError) as exc:
        model = None
        scan_error = "model scan failed: %s: %s" % (type(exc).__name__, exc)
    if model is None:
        for name in ("label_uniqueness", "node_reference_integrity",
                     "element_reference_integrity", "region_integrity",
                     "pbc_reference_integrity", "boundary_contract",
                     "step_pairing", "step_order", "target_consistency",
                     "time_amplitude_consistency", "output_region_integrity"):
            record(name, [scan_error])
        return checks

    # C/D. node and element label contracts.
    problems = []
    for kind, mapping in (("node", model["nodes"]), ("element", model["elements"])):
        duplicates = sorted(label for label, sources in mapping.items() if len(sources) > 1)
        if duplicates:
            problems.append("duplicate %s labels: %s" % (kind, duplicates[:10]))
    rp = {key: int(manifest["labels"][key])
          for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")}
    shell_nodes, shell_elements = int(manifest["shell_nodes"]), int(manifest["shell_elements"])
    if len(set(rp.values())) != len(rp):
        problems.append("control/reference node labels are not distinct")
    if any(value <= shell_nodes for value in rp.values()):
        problems.append("a control/reference label collides with the shell node range")
    plate = manifest["blocks"]["rigid_platens"]
    bottom_nodes, top_nodes = plate["node_ranges"]["bottom"], plate["node_ranges"]["top"]
    bottom_elements, top_elements = plate["element_ranges"]["bottom"], plate["element_ranges"]["top"]
    if not (shell_nodes < bottom_nodes[0] <= bottom_nodes[1] < top_nodes[0] <= top_nodes[1]):
        problems.append("rigid platen node ranges overlap the shell nodes or each other")
    if not (shell_elements < bottom_elements[0] <= bottom_elements[1]
            < top_elements[0] <= top_elements[1]):
        problems.append("rigid platen element ranges overlap the shell elements or each other")
    if any(bottom_nodes[0] <= value <= top_nodes[1] for value in rp.values()):
        problems.append("a control/reference label falls inside the platen node ranges")
    record("label_uniqueness", problems)

    # E. node reference integrity: sets, equations and rigid bodies.
    problems = []
    defined_nodes = set(model["nodes"])
    for name, members in model["nsets"].items():
        missing = sorted(set(members) - defined_nodes)
        if missing:
            problems.append("nset %s references undefined nodes: %s" % (name, missing[:10]))
    for equation in model["equations"]:
        missing = sorted({node for node, _dof, _coef in equation["terms"]} - defined_nodes)
        if missing:
            problems.append("an equation references undefined nodes: %s" % missing[:10])
    for body in model["rigid_bodies"]:
        ref = body["params"].get("ref node")
        if ref is None or not ref.isdigit() or int(ref) not in defined_nodes:
            problems.append("rigid body reference node missing or undefined: " + repr(ref))
    record("node_reference_integrity", problems)

    # F. element reference integrity: connectivity and element sets.
    problems = []
    defined_elements = set(model["elements"])
    for label, entries in model["elements"].items():
        if any(set(entry["conn"]) - defined_nodes for entry in entries):
            problems.append("element %d references an undefined node" % label)
    for name, members in model["elsets"].items():
        missing = sorted(set(members) - defined_elements)
        if missing:
            problems.append("elset %s references undefined elements: %s" % (name, missing[:10]))
    record("element_reference_integrity", problems)

    # G. region existence for the assembled model.
    problems = []
    for name in _MODEL_REGION_NODESETS + tuple(manifest["blocks"]["outputs"]["required_regions"]):
        if not model["nsets"].get(name):
            problems.append("required node set missing or empty: " + name)
    for name in _MODEL_REGION_ELEMENTSETS:
        if not model["elsets"].get(name):
            problems.append("required element set missing or empty: " + name)
    record("region_integrity", problems)

    # H. PBC reference consistency (final referencing only; no re-derivation).
    problems = []
    pbc_map = read_json(folder / "ingredients/pbc_map.json")
    if pbc_map.get("equation_count") != manifest["equation_count"]:
        problems.append("pbc_map equation_count does not match the manifest")
    if pbc_map.get("independent_relations") != len(pbc_map.get("relations", [])):
        problems.append("pbc_map independent_relations does not match its relations list")
    if pbc_map.get("mode") != "lateral_xy_diagonal":
        problems.append("unexpected PBC mode: " + repr(pbc_map.get("mode")))
    pbc_text = (folder / _PBC_SOURCE).read_text(encoding="utf-8").lower()
    if "rp_z" in manifest["labels"] or "rp_z" in pbc_text:
        problems.append("hidden Z macro control found; lateral XY PBC only")
    lateral_equations = [e for e in model["equations"] if e["source"] == _PBC_SOURCE]
    if len(lateral_equations) != pbc_map.get("equation_count"):
        problems.append("rendered equation count does not match pbc_map")
    macro_dofs = {rp["rp_x"]: 1, rp["rp_y"]: 2}
    for equation in lateral_equations:
        for node, dof, _coef in equation["terms"]:
            if node in macro_dofs and dof != macro_dofs[node]:
                problems.append("macro control DOF misuse on node %d" % node)
    dependent = {int(row["node"]) + 1 for row in pbc_map.get("relations", [])}
    referenced = {node for equation in lateral_equations
                  for node, _dof, _coef in equation["terms"]}
    if not dependent <= referenced:
        problems.append("dependent PBC nodes missing from the rendered equations")
    record("pbc_reference_integrity", problems)

    # I. boundary / loading contract.
    problems = []
    step_block = manifest["blocks"]["step_loading"]
    model_dofs = {}
    for boundary in model["boundaries"]:
        if boundary["source"] != _BC_BLOCK_SOURCE:
            continue
        for nset, dof1, dof2, _mag in boundary["rows"]:
            model_dofs.setdefault(nset, set()).update(range(dof1, dof2 + 1))
    if model_dofs.get("RP_BOTTOM") != {1, 2, 3, 4, 5, 6}:
        problems.append("RP_BOTTOM model-level DOFs are not exactly 1-6: "
                        + repr(sorted(model_dofs.get("RP_BOTTOM", ()))))
    if model_dofs.get("RP_TOP") != {1, 2, 4, 5, 6}:
        problems.append("RP_TOP model-level guide DOFs are not exactly 1,2,4,5,6 "
                        "(DOF3 must stay free for the step loading): "
                        + repr(sorted(model_dofs.get("RP_TOP", ()))))
    extra = set(model_dofs) - {"RP_BOTTOM", "RP_TOP"}
    if extra:
        problems.append("unexpected model-level boundary sets: " + repr(sorted(extra)))
    for boundary in model["boundaries"]:
        for nset, _dof1, _dof2, _mag in boundary["rows"]:
            if nset in ("RP_X_CTRL", "RP_Y_CTRL"):
                problems.append("macro control node constrained in %s: %s"
                                % (boundary["source"], nset))
    step_boundaries = [b for b in model["boundaries"] if b["source"] == _STEP_LOADING_SOURCE]
    if len(step_boundaries) != 1 or step_boundaries[0]["params"].get("amplitude") != "AMP_COMPRESSION":
        problems.append("the compression step needs exactly one *Boundary with "
                        "amplitude=AMP_COMPRESSION")
    else:
        rows = step_boundaries[0]["rows"]
        expected_row = (step_block["loading_set"], step_block["loading_dof"],
                        step_block["loading_dof"])
        if len(rows) != 1 or (rows[0][0], rows[0][1], rows[0][2]) != expected_row:
            problems.append("step loading must be exactly RP_TOP DOF3: " + repr(rows))
        elif rows[0][3] is None or float(rows[0][3]) != float(step_block["target_displacement_mm"]):
            problems.append("step U3 magnitude does not match the manifest target")
    record("boundary_contract", problems)

    # J. step pairing and K. step/order structure.
    problems = []
    deck = model["deck"]
    step_count = sum(1 for entry in deck if entry["keyword"] == "*step")
    end_count = sum(1 for entry in deck if entry["keyword"] == "*end step")
    if step_count != 1:
        problems.append("expected exactly one *Step, found %d" % step_count)
    if end_count != 1:
        problems.append("expected exactly one *End Step, found %d" % end_count)
    record("step_pairing", problems)

    problems = []
    step_idx = next((i for i, entry in enumerate(deck) if entry["keyword"] == "*step"), None)
    end_idx = next((i for i, entry in enumerate(deck) if entry["keyword"] == "*end step"), None)
    if step_idx is not None and end_idx is not None and step_idx < end_idx:
        for i, entry in enumerate(deck):
            keyword = entry["keyword"]
            if keyword in _IN_STEP_OUTPUT_KEYWORDS and not (step_idx < i < end_idx):
                problems.append("%s in %s is not inside the step" % (keyword, entry["source"]))
            elif keyword == "*dynamic" and not (step_idx < i < end_idx):
                problems.append("*Dynamic is not inside the step")
            elif keyword == "*amplitude" and not (i < step_idx):
                problems.append("*Amplitude must precede the step open")
            elif keyword == "*boundary":
                inside = step_idx < i < end_idx
                if "amplitude" in entry["params"] and not inside:
                    problems.append("the amplitude-driven step boundary is not inside the step")
                if "amplitude" not in entry["params"] and inside:
                    problems.append("a model-level boundary appears inside the step")
    else:
        problems.append("step open/close not comparable for ordering")
    record("step_order", problems)


    # L. target consistency (validator only checks; it never recomputes/overwrites).
    problems = []
    strain = float(manifest["physics"]["target_compression_strain"])
    expected_target = -strain * float(manifest["L_mm"])
    target = float(manifest["target_displacement_mm"])
    if not math.isclose(expected_target, target, rel_tol=1e-12, abs_tol=0.0):
        problems.append("target_displacement_mm %r != -strain * L_mm %r"
                        % (target, expected_target))
    if float(step_block["target_displacement_mm"]) != target:
        problems.append("step_loading manifest target differs from the model target")
    record("target_consistency", problems)

    # M. time / amplitude consistency.
    problems = []
    period = float(manifest["physics"]["time_period_s"])
    amplitudes = [entry for entry in deck if entry["keyword"] == "*amplitude"
                  and entry["source"] == _STEP_LOADING_SOURCE]
    dynamics = [entry for entry in deck if entry["keyword"] == "*dynamic"]
    if len(amplitudes) != 1 or len(amplitudes[0]["data"]) != 1 or len(amplitudes[0]["data"][0]) != 4:
        problems.append("the compression amplitude definition is missing or malformed")
    else:
        start_time, start_value, end_time, end_value = (
            float(value) for value in amplitudes[0]["data"][0])
        if (start_time, start_value) != (0.0, 0.0) or end_value != 1.0:
            problems.append("the smooth step amplitude must span 0 -> 1")
        if end_time != period:
            problems.append("amplitude endpoint %r != time_period_s %r" % (end_time, period))
    if len(dynamics) != 1 or len(dynamics[0]["data"]) != 1 or len(dynamics[0]["data"][0]) != 4:
        problems.append("the *Dynamic time increments line is missing or malformed")
    else:
        total = float(dynamics[0]["data"][0][1])
        if total != period:
            problems.append("*Dynamic total step time %r != time_period_s %r" % (total, period))
    if ([float(step_block["amplitude_end"][0]), float(step_block["amplitude_end"][1])]
            != [period, 1.0]) or float(step_block["time_period_s"]) != period:
        problems.append("manifest step_loading time/amplitude metadata is inconsistent")
    record("time_amplitude_consistency", problems)

    # N. output region integrity (existence only; variable semantics is M2+).
    problems = []
    rendered_regions = [entry["params"].get("nset") for entry in deck
                        if entry["keyword"] == "*node output"
                        and entry["source"] == _OUTPUTS_SOURCE]
    required_regions = list(manifest["blocks"]["outputs"]["required_regions"])
    if rendered_regions != required_regions:
        problems.append("rendered node output regions %r != manifest required_regions %r"
                        % (rendered_regions, required_regions))
    defined_nsets = set(model["nsets"])
    for name in required_regions:
        if name not in defined_nsets:
            problems.append("output region not defined in the assembled model: " + name)
    record("output_region_integrity", problems)

    return checks



def _run_static_stage(folder, manifest):
    """Assemble physical.inp, validate statically and publish the build evidence.

    On success the build_report.json records PASS with every later Abaqus stage
    as NOT_RUN, and the manifest is finalized as PHYSICAL_INP_STATIC_VALIDATED
    with dataset_eligible=false. On failure the attempt keeps all artifacts, a
    failing build_report.json names the failed checks, the manifest is written
    with a failed status (never a success claim) and STATIC_VALIDATION_FAILED
    is raised.
    """
    folder = Path(folder)
    inp_sha = _assemble_physical_inp(_STATIC_INCLUDE_ORDER, folder / "physical.inp")
    checks = _validate_static_model(folder, manifest)
    includes = [{"path": path, "sha256": (file_hash(folder / path)
                                          if (folder / path).is_file() else None)}
                for _, path in _STATIC_INCLUDE_ORDER]
    failed = sorted(name for name, result in checks.items() if result["status"] != "PASS")
    report = {
        "schema_version": 1,
        "builder": _BUILDER_ID,
        "model_key": manifest["identity"]["model_key"],
        "scaffold_key": manifest["scaffold_key"],
        "build_key": manifest["build_key"],
        "physical_inp": {"path": "physical.inp", "sha256": inp_sha},
        "includes": includes,
        "static_checks": checks,
        "static_validation": "FAILED" if failed else "PASS",
        "abaqus_datacheck": "NOT_RUN",
        "solve": "NOT_RUN",
        "odb_qa": "NOT_RUN",
        "dataset_eligible": False,
        "warning": "Static validation PASS is repository-level internal consistency only: "
                   "it does NOT mean the Abaqus keyword parser accepted the deck, and no "
                   "Physical Data Check, solve, ODB QA or dataset eligibility is claimed.",
    }
    if failed:
        report["status"] = "STATIC_VALIDATION_FAILED"
        report["failed_checks"] = failed
        atomic_json(folder / "build_report.json", report)
        atomic_json(folder / "model_manifest.json", dict(
            manifest, status="PHYSICAL_INP_STATIC_VALIDATION_FAILED",
            dataset_eligible=False, physical_inp=report["physical_inp"],
            warning="Static validation failed; the attempt is retained as evidence and no "
                    "successful build is claimed."))
        raise PipelineError("STATIC_VALIDATION_FAILED",
                            "Static validation failed checks: " + ", ".join(failed))
    report["status"] = "STATIC_VALIDATION_PASSED"
    atomic_json(folder / "build_report.json", report)
    final = dict(
        manifest,
        status="PHYSICAL_INP_STATIC_VALIDATED",
        implemented_stages=list(manifest["implemented_stages"]) + [
            "physical.inp assembly", "static model validation"],
        missing_stages=["physical datacheck", "solve", "ODB QA"],
        physical_inp=report["physical_inp"],
        build_report={"path": "build_report.json",
                      "sha256": file_hash(folder / "build_report.json")},
        dataset_eligible=False,
        warning="physical.inp passed repository static validation only. Abaqus Physical "
                "Data Check, solve, ODB QA and dataset eligibility are NOT validated and "
                "remain future milestones (quasi_static_status stays pending_qa).")
    atomic_json(folder / "model_manifest.json", final)
    return final



def build(npz, report, pairs, physics_path, material_path, numerics_path, outputs_path, output):
    """Validate contracts, reuse prepare-fe ingredients and assemble physical.inp.

    Input and numerics errors are raised before the attempt directory is created,
    so simple mistakes leave no empty attempts. Failures inside the real
    ingredient preparation or the M1-7 static validation keep the attempt as
    evidence (see _run_static_stage).
    """
    _require_inputs((npz, report, pairs, physics_path, material_path, numerics_path, outputs_path))
    numerics = _load_numerics(numerics_path)
    outputs = _load_outputs(outputs_path)
    required_regions = []
    requested_variables = []
    for group in outputs["history_groups"]:
        for request in group.get("requests", []):
            if request["region"]["type"] == "node_set":
                required_regions.append(request["region"]["name"])
            requested_variables.append({"region": request["region"].get("name", request["region"]["type"]),
                                        "kind": request["kind"],
                                        "variables": list(request["variables"])})
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
    atomic_text(blocks_dir / _BC_BLOCK, _render_boundary_conditions(model_inputs["physics"], model_inputs))
    bc_block_sha = file_hash(blocks_dir / _BC_BLOCK)
    atomic_text(blocks_dir / _CONTACT_BLOCK, _render_contact(model_inputs["physics"], model_inputs))
    contact_block_sha = file_hash(blocks_dir / _CONTACT_BLOCK)
    atomic_text(blocks_dir / _STEP_LOADING_BLOCK,
                _render_step_and_loading(model_inputs["physics"], numerics, model_inputs))
    step_loading_sha = file_hash(blocks_dir / _STEP_LOADING_BLOCK)
    atomic_text(blocks_dir / _STEP_END_BLOCK, _render_step_end())
    step_end_sha = file_hash(blocks_dir / _STEP_END_BLOCK)
    atomic_text(blocks_dir / _OUTPUTS_BLOCK, _render_outputs(outputs))
    outputs_block_sha = file_hash(blocks_dir / _OUTPUTS_BLOCK)
    scaffold_key = digest({"model_key": model_inputs["model_key"], "numerics": numerics,
                           "numerics_sha256": file_hash(numerics_path), "builder": _BUILDER_ID})
    manifest = {
        "schema_version": 1,
        "builder": _BUILDER_ID,
        "scaffold_key": scaffold_key,
        "build_key": digest({"scaffold_key": scaffold_key, "builder": _BUILDER_ID,
                             "blocks": {"material_section": material_block_sha,
                                        "rigid_platens": rigid_block_sha,
                                        "boundary_conditions": bc_block_sha,
                                        "contact": contact_block_sha,
                                        "step_loading": step_loading_sha,
                                        "step_end": step_end_sha,
                                        "outputs": outputs_block_sha}}),
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
        "outputs": outputs,
        "outputs_config_sha256": file_hash(outputs_path),
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
                "normal_policy_status": "baseline_contact_definition_reproduced_pending_datacheck"},
            "boundary_conditions": {
                "path": "blocks/" + _BC_BLOCK, "sha256": bc_block_sha,
                "boundary_mode": model_inputs["physics"]["boundary_mode"],
                "bottom_fixed_dofs": [1, 2, 3, 4, 5, 6],
                "top_guide_dofs": [1, 2, 4, 5, 6],
                "top_loading_dof": 3,
                "rp_x_boundary": "none", "rp_y_boundary": "none",
                "source_policy": "baseline_lateral_xy_platens"},
            "contact": {
                "path": "blocks/" + _CONTACT_BLOCK, "sha256": contact_block_sha,
                "property_name": "ContactProp",
                "algorithm": "general_contact_standard",
                "domain": "all_exterior_self",
                "normal": model_inputs["physics"]["contact"]["normal"],
                "allow_separation": model_inputs["physics"]["contact"]["allow_separation"],
                "tangential_policy": "penalty_default",
                "friction": model_inputs["physics"]["contact"]["friction"],
                "slip_tolerance": model_inputs["physics"]["contact"]["slip_tolerance"],
                "shell_self_contact": model_inputs["physics"]["contact"]["shell_self_contact"],
                "explicit_surfaces": False,
                "explicit_contact_initialization": False,
                "initialization_policy": "abaqus_standard_default_pending_datacheck",
                "source_policy": "hand_baseline_all_exterior_general_contact"},
            "step_loading": {
                "path": "blocks/" + _STEP_LOADING_BLOCK, "sha256": step_loading_sha,
                "step_name": "Compression",
                "procedure": numerics["procedure"],
                "application": numerics["application"],
                "nlgeom": numerics["nlgeom"],
                "maximum_increments": numerics["maximum_increments"],
                "initial_acceleration_policy": numerics["initial_acceleration_policy"],
                "initial_increment_s": numerics["initial_increment_s"],
                "minimum_increment_s": numerics["minimum_increment_s"],
                "maximum_increment_s": numerics["maximum_increment_s"],
                "time_period_s": model_inputs["physics"]["time_period_s"],
                "amplitude_name": "AMP_COMPRESSION",
                "amplitude_type": "smooth_step",
                "amplitude_time_span": "step",
                "amplitude_start": [0.0, 0.0],
                "amplitude_end": [model_inputs["physics"]["time_period_s"], 1.0],
                "loading_set": "RP_TOP",
                "loading_dof": 3,
                "target_displacement_mm": model_inputs["target_displacement_mm"],
                "target_compression_strain": model_inputs["physics"]["target_compression_strain"],
                "step_reapplies_guide_dofs": False,
                "quasi_static_status": "pending_qa"},
            "step_end": {
                "path": "blocks/" + _STEP_END_BLOCK, "sha256": step_end_sha,
                "keyword": "*End Step"},
            "outputs": {
                "path": "blocks/" + _OUTPUTS_BLOCK, "sha256": outputs_block_sha,
                "profile_id": outputs["profile_id"],
                "restart_policy": outputs["restart"]["policy"],
                "field_group_count": len(outputs["field_groups"]),
                "history_group_count": len(outputs["history_groups"]),
                "schedule_policy": "every_n_increments",
                "required_regions": required_regions,
                "requested_variables": requested_variables,
                "source_policy": "fig1 hand baseline output policy; the Dynamic omitted history "
                                 "PRESELECT frequency is rendered explicitly as 10 based on the "
                                 "Abaqus/Standard direct-INP documented default. Keyword semantics "
                                 "reproduced only; automatic-model ODB sampling is validated by the "
                                 "M2 physical data check."}},
        "implemented_stages": ["input contract checks", "numerics contract checks",
                               "ingredient reuse from prepare-fe", "model manifest",
                               "material/section block rendering",
                               "rigid platens/reference points block rendering",
                               "boundary conditions block rendering",
                               "contact block rendering",
                               "step and loading block rendering",
                               "output request block rendering"],
        "missing_stages": ["physical.inp assembly", "static model validation",
                           "physical datacheck", "solve", "ODB QA"],
        "dataset_eligible": False,
    }
    return _run_static_stage(folder, manifest)