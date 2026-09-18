"""Build side: config/simulation.json -> a complete, self-checked Abaqus deck.

One command does what used to be two stages (FE ingredients + physical build):

    mesh outputs (npz/report/pairs) + config/simulation.json
        -> ingredients/  (shell mesh, PBC equations, pbc_map.json)
        -> blocks/       (material, platens, boundary, contact, step, outputs)
        -> physical.inp  (fixed include order)
        -> build_report.json (SHAs, checks, provenance)

Everything Abaqus-side that a research user actually changes comes from
config/simulation.json: element types, material, thickness/relative density,
platen size, contact, loading target, step controls and every output request.
Internal names (NSETs, material/section/step/property names, file names) stay
code constants on purpose - renaming them is not a research variable.

The deck is deterministic: identical inputs produce byte-identical files, which
is what the Fig.1 regression fixture pins.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from .common import (PipelineError, atomic_text, boolean, file_hash, finite,
                     git_provenance, positive_int, read_json, require_keys,
                     reserve_directory, write_json)
from .mesh import prepare_ingredients

# --- internal Abaqus names (code constants, NOT user config) -----------------
_MATERIAL = "MAT_SHELL"
_SHELL_ELSET = "SHELL_ALL"
_PLATE_ELSETS = ("PLATE_BOTTOM", "PLATE_TOP")
_CONTACT_PROP = "ContactProp"
_STEP_NAME = "Compression"
_AMPLITUDE = "AMP_COMPRESSION"
#: Region names a history output request may name (rendered by this builder).
NODE_SETS = ("RP_X_CTRL", "RP_Y_CTRL", "RP_BOTTOM", "RP_TOP",
             "PLATE_BOTTOM_NODES", "PLATE_TOP_NODES")
ELEMENT_SETS = (_SHELL_ELSET,) + _PLATE_ELSETS
DECK_ROOT = "physical.inp"
_BLOCKS_DIR = "blocks"
_INGREDIENTS_DIR = "ingredients"
#: Fixed include order of the top-level deck.
INCLUDE_ORDER = (_INGREDIENTS_DIR + "/shell_mesh.inc",
                 _BLOCKS_DIR + "/material_section.inc",
                 _BLOCKS_DIR + "/rigid_platens.inc",
                 _INGREDIENTS_DIR + "/lateral_pbc.inc",
                 _BLOCKS_DIR + "/boundary_conditions.inc",
                 _BLOCKS_DIR + "/contact.inc",
                 _BLOCKS_DIR + "/step_loading.inc",
                 _BLOCKS_DIR + "/outputs.inc",
                 _BLOCKS_DIR + "/step_end.inc")
_BLOCK_FILE = {"material_section": _BLOCKS_DIR + "/material_section.inc",
               "rigid_platens": _BLOCKS_DIR + "/rigid_platens.inc",
               "boundary_conditions": _BLOCKS_DIR + "/boundary_conditions.inc",
               "contact": _BLOCKS_DIR + "/contact.inc",
               "step_loading": _BLOCKS_DIR + "/step_loading.inc",
               "outputs": _BLOCKS_DIR + "/outputs.inc",
               "step_end": _BLOCKS_DIR + "/step_end.inc"}
_ELEMENT_TYPE_RE = re.compile(r"^[A-Za-z0-9_]{1,32}$")
_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")

_SIM_REQUIRED = ("material", "shell", "platen", "contact", "loading", "solver", "output", "pbc")
_MATERIAL_KEYS = ("density_tonne_mm3", "youngs_modulus_MPa", "poisson_ratio", "plastic_table")
_SHELL_KEYS = ("element_type", "integration_points", "target_relative_density")
_PLATEN_KEYS = ("element_type", "width_factor", "mesh_size_mm")
_CONTACT_KEYS = ("normal", "allow_separation", "friction", "self_contact")
_LOADING_KEYS = ("target_compression_strain", "amplitude")
_PBC_KEYS = ("include_rotational_dofs",)
_SOLVER_KEYS = ("type", "standard_dynamic_implicit", "explicit_dynamic")
_STANDARD_KEYS = ("time_period_s", "nlgeom", "application", "initial_acceleration",
                  "initial_increment_s", "minimum_increment_s", "maximum_increment_s",
                  "maximum_increments", "slip_tolerance", "restart_frequency",
                  "field_frequency", "history_frequency", "preselect_history_frequency")
_EXPLICIT_KEYS = ("time_period_s", "field_number_interval", "history_time_interval_s",
                  "field_time_marks", "mass_scaling")
_MASS_SCALING_KEYS = ("enabled", "factor")
_OUTPUT_KEYS = ("requests",)

#: Solver names this repository can actually render.
STANDARD_DYNAMIC_IMPLICIT = "standard_dynamic_implicit"
EXPLICIT_DYNAMIC = "explicit_dynamic"
SOLVER_TYPES = (STANDARD_DYNAMIC_IMPLICIT, EXPLICIT_DYNAMIC)
#: Loading amplitude shapes this repository renders.
SUPPORTED_AMPLITUDES = ("smooth_step", "ramp")
#: Element types compatible with the topology the builder actually generates:
#: the shell mesh is 3-node triangles, the platen mesh is a 4-node quad grid.
#: Anything else would need a different mesh generator, so it is rejected here
#: instead of being written into a deck Abaqus cannot accept.
TRIANGLE_SHELL_TYPES = ("S3", "S3R", "STRI3")
QUAD_RIGID_TYPES = ("R3D4",)



def _element_type(value, name, allowed, reason):
    """Accept only element types compatible with the topology this builder writes.

    The check is a simple topology check, not an Abaqus element database: the shell
    mesh is made of 3-node triangles and the platen grid of 4-node quads, so any
    other element type would need a different mesh generator.
    """
    if not isinstance(value, str) or not _ELEMENT_TYPE_RE.match(value):
        raise PipelineError("CONFIG_INVALID",
                            name + " must be an Abaqus element type string, got " + repr(value))
    if value.upper() not in allowed:
        raise PipelineError("CONFIG_INVALID",
                            name + "=" + repr(value) + " is incompatible with this model: "
                            + reason + ". Supported: " + repr(list(allowed)))
    return value


def _load_output(output, path):
    """Validate the output block: the history/field requests both solvers render.

    Sampling frequencies are solver-specific numerics and live in the solver
    blocks (``field_frequency`` etc. for Standard, ``field_number_interval`` etc.
    for Explicit), so this block only says WHAT to write, not how often.
    """
    output = require_keys(output, path, _OUTPUT_KEYS, (), "simulation.output")
    requests = output["requests"]
    if not isinstance(requests, list) or not requests:
        raise PipelineError("CONFIG_INVALID", "output.requests must be a non-empty list.")
    for number, request in enumerate(requests):
        spot = "output.requests[%d]" % number
        request = require_keys(request, path, ("kind", "variables"), ("region",), spot)
        if request["kind"] == "energy":
            if "region" in request:
                raise PipelineError("CONFIG_INVALID",
                                    spot + ": *Energy Output is whole-model; drop 'region'.")
        elif request["kind"] == "node":
            if request["region"] not in NODE_SETS:
                raise PipelineError("CONFIG_INVALID",
                                    spot + ".region must be one of " + repr(list(NODE_SETS)))
        else:
            raise PipelineError("NOT_IMPLEMENTED",
                                spot + ".kind=" + repr(request["kind"])
                                + " is valid Abaqus usage but this writer only implements "
                                "'energy' and 'node'.")
        if (not isinstance(request["variables"], list) or not request["variables"]
                or not all(isinstance(v, str) and v.strip() for v in request["variables"])):
            raise PipelineError("CONFIG_INVALID",
                                spot + ".variables must be a non-empty list of strings.")
    return output


def _load_solver(sim, path):
    """Validate the solver block: a type plus one parameter block per solver.

    Keeping both blocks is deliberate: switching ``type`` must not require adding
    parameters, and Standard-only numerics (application, increments, slip
    tolerance) must never leak into an Explicit deck.
    """
    solver = require_keys(sim["solver"], path, _SOLVER_KEYS, (), "simulation.solver")
    if solver["type"] not in SOLVER_TYPES:
        raise PipelineError("NOT_IMPLEMENTED",
                            "solver.type=" + repr(solver["type"]) + " is not implemented; "
                            "supported types: " + repr(list(SOLVER_TYPES)))
    standard = require_keys(solver[STANDARD_DYNAMIC_IMPLICIT], path, _STANDARD_KEYS, (),
                            "solver.standard_dynamic_implicit")
    finite(standard["time_period_s"], "solver.standard_dynamic_implicit.time_period_s",
           positive=True)
    boolean(standard["nlgeom"], "solver.standard_dynamic_implicit.nlgeom")
    if (not isinstance(standard["application"], str)
            or not _NAME_RE.match(standard["application"])):
        raise PipelineError("CONFIG_INVALID",
                            "solver.standard_dynamic_implicit.application must be an Abaqus "
                            "application name.")
    boolean(standard["initial_acceleration"],
            "solver.standard_dynamic_implicit.initial_acceleration")
    initial = finite(standard["initial_increment_s"],
                     "solver.standard_dynamic_implicit.initial_increment_s", positive=True)
    minimum = finite(standard["minimum_increment_s"],
                     "solver.standard_dynamic_implicit.minimum_increment_s", positive=True)
    maximum = finite(standard["maximum_increment_s"],
                     "solver.standard_dynamic_implicit.maximum_increment_s", positive=True)
    if not minimum <= initial <= maximum:
        raise PipelineError("CONFIG_INVALID",
                            "Standard increments must satisfy 0 < minimum <= initial <= maximum.")
    positive_int(standard["maximum_increments"],
                 "solver.standard_dynamic_implicit.maximum_increments")
    finite(standard["slip_tolerance"], "solver.standard_dynamic_implicit.slip_tolerance",
           positive=True)
    # restart_frequency=0 switches restart writing off; any value >= 0 is accepted.
    positive_int(standard["restart_frequency"] + 1,
                 "solver.standard_dynamic_implicit.restart_frequency")
    for key in ("field_frequency", "history_frequency"):
        positive_int(standard[key], "solver.standard_dynamic_implicit." + key)
    extra = standard["preselect_history_frequency"]
    if isinstance(extra, bool) or not isinstance(extra, int) or extra < 0:
        raise PipelineError("CONFIG_INVALID",
                            "solver.standard_dynamic_implicit.preselect_history_frequency must be "
                            "an integer >= 0 (0 omits the extra preselected history group)")

    explicit = require_keys(solver[EXPLICIT_DYNAMIC], path, _EXPLICIT_KEYS, (),
                            "solver.explicit_dynamic")
    finite(explicit["time_period_s"], "solver.explicit_dynamic.time_period_s", positive=True)
    positive_int(explicit["field_number_interval"],
                 "solver.explicit_dynamic.field_number_interval")
    finite(explicit["history_time_interval_s"],
           "solver.explicit_dynamic.history_time_interval_s", positive=True)
    boolean(explicit["field_time_marks"], "solver.explicit_dynamic.field_time_marks")
    scaling = require_keys(explicit["mass_scaling"], path, ("enabled",), ("factor",),
                           "solver.explicit_dynamic.mass_scaling")
    boolean(scaling["enabled"], "solver.explicit_dynamic.mass_scaling.enabled")
    if scaling["enabled"]:
        # Mass scaling is a scientific choice and is never applied silently: when it
        # is on, the factor must be written down and it is recorded in the report.
        finite(scaling.get("factor"), "solver.explicit_dynamic.mass_scaling.factor",
               positive=True)
    return solver


def solver_type(simulation):
    return simulation["solver"]["type"]


def solver_block(simulation):
    return simulation["solver"][solver_type(simulation)]


def load_simulation(path):
    """Load and validate config/simulation.json into plain nested dicts."""
    sim = require_keys(read_json(path), path, _SIM_REQUIRED, (), "simulation config")
    material = require_keys(sim["material"], path, _MATERIAL_KEYS, (), "simulation.material")
    finite(material["density_tonne_mm3"], "material.density_tonne_mm3", positive=True)
    finite(material["youngs_modulus_MPa"], "material.youngs_modulus_MPa", positive=True)
    finite(material["poisson_ratio"], "material.poisson_ratio")
    table = material["plastic_table"]
    if not isinstance(table, list) or not table:
        raise PipelineError("CONFIG_INVALID", "material.plastic_table must be a non-empty list.")
    for index, row in enumerate(table):
        if not isinstance(row, list) or len(row) != 2:
            raise PipelineError("CONFIG_INVALID",
                                "material.plastic_table[%d] must be [stress, plastic strain]."
                                % index)
        finite(row[0], "material.plastic_table[%d][0]" % index, positive=True)
        finite(row[1], "material.plastic_table[%d][1]" % index, minimum=0.0)
    shell = require_keys(sim["shell"], path, _SHELL_KEYS, (), "simulation.shell")
    _element_type(shell["element_type"], "shell.element_type", TRIANGLE_SHELL_TYPES,
                  "the shell mesh is 3-node triangles, so only 3-node shell elements fit")
    positive_int(shell["integration_points"], "shell.integration_points", maximum=99)
    finite(shell["target_relative_density"], "shell.target_relative_density", positive=True)
    platen = require_keys(sim["platen"], path, _PLATEN_KEYS, (), "simulation.platen")
    _element_type(platen["element_type"], "platen.element_type", QUAD_RIGID_TYPES,
                  "the platen grid is a 4-node quad grid, so only 4-node rigid elements fit")
    finite(platen["width_factor"], "platen.width_factor", positive=True)
    finite(platen["mesh_size_mm"], "platen.mesh_size_mm", positive=True)
    contact = require_keys(sim["contact"], path, _CONTACT_KEYS, (), "simulation.contact")
    if not isinstance(contact["normal"], str) or not _NAME_RE.match(contact["normal"]):
        raise PipelineError("CONFIG_INVALID",
                            "contact.normal must be an Abaqus pressure-overclosure value.")
    boolean(contact["allow_separation"], "contact.allow_separation")
    finite(contact["friction"], "contact.friction", minimum=0.0)
    boolean(contact["self_contact"], "contact.self_contact")
    loading = require_keys(sim["loading"], path, _LOADING_KEYS, (), "simulation.loading")
    finite(loading["target_compression_strain"], "loading.target_compression_strain", positive=True)
    if loading["amplitude"] not in SUPPORTED_AMPLITUDES:
        raise PipelineError("NOT_IMPLEMENTED",
                            "loading.amplitude=" + repr(loading["amplitude"])
                            + " is valid Abaqus usage but this writer only implements "
                            + repr(list(SUPPORTED_AMPLITUDES)) + ".")
    sim["solver"] = _load_solver(sim, path)
    pbc = require_keys(sim["pbc"], path, _PBC_KEYS, (), "simulation.pbc")
    boolean(pbc["include_rotational_dofs"], "pbc.include_rotational_dofs")
    sim["output"] = _load_output(sim["output"], path)
    return sim


# ---------------------------------------------------------------------------
# Block renderers. Their text is part of the frozen Fig.1 deck, so the
# generation comments are preserved byte-for-byte on purpose: the regression
# fixture compares deck SHAs, and a comment-only change would hide a real one.
# ---------------------------------------------------------------------------

def _fmt(value):
    """Deterministic shortest round-trip float text: identical input, identical block."""
    return repr(float(value))


def render_material_section(simulation, facts):
    """Render *Material/*Density/*Elastic/*Plastic and the homogeneous shell section."""
    material, shell = simulation["material"], simulation["shell"]
    lines = [
        "** Material/section block rendered by physical-builder (M1-2);",
        "** keyword syntax baseline: the validated hand model Fig1_Compression.inp.",
        "*Material, name=" + _MATERIAL,
        "*Density",
        " " + _fmt(material["density_tonne_mm3"]) + ",",
        "*Elastic",
        _fmt(material["youngs_modulus_MPa"]) + ", " + _fmt(material["poisson_ratio"]),
        "*Plastic",
    ]
    lines.extend(_fmt(stress) + ", " + _fmt(strain) for stress, strain in material["plastic_table"])
    lines.extend([
        "*Shell Section, elset=" + _SHELL_ELSET + ", material=" + _MATERIAL,
        _fmt(facts["thickness_mm"]) + ", %d" % shell["integration_points"],
        "** Homogeneous shell section, Simpson integration with %d thickness points;"
        % shell["integration_points"],
        "** this is the current builder baseline, not an immutable research parameter.",
    ])
    return "\n".join(lines) + "\n"


def platen_plan(simulation, facts):
    """Resolve platen geometry and the label-safe assignment plan."""
    platen = simulation["platen"]
    width_factor = platen["width_factor"]
    mesh_size = platen["mesh_size_mm"]
    L = float(facts["L_mm"])
    width = width_factor * L
    intervals = width / mesh_size
    rounded = round(intervals)
    if rounded < 1 or not math.isclose(intervals, rounded, rel_tol=0.0, abs_tol=1e-9):
        raise PipelineError("NOT_IMPLEMENTED",
                            "This builder requires the platen width (" + _fmt(width) + " mm) to be an "
                            "exact integer multiple of mesh_size_mm (" + _fmt(mesh_size) + " mm); it "
                            "will not silently round the mesh size.")
    intervals = int(rounded)
    labels = facts["labels"]
    rp_labels = {key: int(labels[key]) for key in ("rp_x", "rp_y", "rp_bottom", "rp_top")}
    shell_nodes, shell_elements = int(facts["shell_nodes"]), int(facts["shell_elements"])
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
        "element_type": platen["element_type"], "L": L, "width": width,
        "mesh_size": float(mesh_size), "intervals": intervals, "per_side_nodes": per_side,
        "nodes_per_platen": nodes_per_platen, "elements_per_platen": elements_per_platen,
        "x": (L / 2 - width / 2, L / 2 + width / 2), "y": (L / 2 - width / 2, L / 2 + width / 2),
        "rp_labels": rp_labels,
        "rp_coords": {"rp_bottom": (L / 2, L / 2, 0.0), "rp_top": (L / 2, L / 2, L),
                      "rp_x": (1.5 * L, L / 2, L / 2), "rp_y": (L / 2, 1.5 * L, L / 2)},
        "bottom_nodes": bottom_nodes, "top_nodes": top_nodes,
        "bottom_elements": bottom_elements, "top_elements": top_elements,
    }


def render_rigid_platens(simulation, facts):
    """Render control nodes, NSETs, both rigid platens and their *Rigid Body lines."""
    plan = platen_plan(simulation, facts)
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
    lines.append("*Element, type=%s, elset=%s" % (element_type, _PLATE_ELSETS[0]))
    lines.extend(element_lines(plan["bottom_elements"][0], plan["bottom_nodes"][0]))
    lines.extend(["*Nset, nset=PLATE_BOTTOM_NODES, generate",
                  "%d, %d, 1" % plan["bottom_nodes"],
                  "*Node"])
    lines.extend(grid_lines(plan["top_nodes"][0], plan["L"]))
    lines.append("*Element, type=%s, elset=%s" % (element_type, _PLATE_ELSETS[1]))
    lines.extend(element_lines(plan["top_elements"][0], plan["top_nodes"][0]))
    lines.extend(["*Nset, nset=PLATE_TOP_NODES, generate",
                  "%d, %d, 1" % plan["top_nodes"],
                  "*Rigid Body, ref node=%d, elset=%s" % (node_labels["rp_bottom"], _PLATE_ELSETS[0]),
                  "*Rigid Body, ref node=%d, elset=%s" % (node_labels["rp_top"], _PLATE_ELSETS[1])])
    return "\n".join(lines) + "\n"


def render_boundary_conditions(facts):
    """Render the model-level zero-valued platen constraints.

    RP_BOTTOM is fully fixed and RP_TOP is guided in DOF 1,2,4,5,6; the DOF-3
    loading is rendered by the step block. RP_X_CTRL/RP_Y_CTRL receive NO boundary:
    their DOF1/DOF2 are the free lateral PBC macro control DOFs.
    """
    labels = facts["labels"]
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


def render_contact(simulation):
    """Render the General Contact definition from the contact config.

    The physical meaning is the same in both solvers (general contact over the
    model's exterior, hard normal behaviour, friction, optional self-contact);
    only the Standard-only numerical ``slip tolerance`` is left out for Explicit,
    because Abaqus/Explicit rejects it (the Explicit A/B experiment measured
    ``***ERROR: UNKNOWN PARAMETER SLIPTOLERANCE``).

    ``self_contact=false`` cannot be expressed by excluding the all-inclusive
    surface from itself: Abaqus 2026 answers ``The general contact definition is
    empty`` because with ALL EXTERIOR the domain IS that surface's self-contact.
    The domain is therefore written as explicit shell/platen surface pairs, which
    keeps shell-platen contact and drops shell-shell contact.
    """
    contact = simulation["contact"]
    lines = [
        "** Contact definition rendered by physical-builder (M1-4).",
        "** Baseline policy: Abaqus/Standard General Contact with ALL EXTERIOR.",
        "** The hand baseline's optional surface-interaction scalar line (1.0, used only",
        "** for 2D models or node-based contact pairs) is intentionally omitted here:",
        "** this model is 3D element-based, so that default scalar does not apply.",
        "*Surface Interaction, name=" + _CONTACT_PROP,
    ]
    if solver_type(simulation) == STANDARD_DYNAMIC_IMPLICIT:
        lines.append("*Friction, slip tolerance="
                     + _fmt(solver_block(simulation)["slip_tolerance"]))
    else:
        lines.append("*Friction")
    lines.extend([
        _fmt(contact["friction"]) + ",",
        "*Surface Behavior, pressure-overclosure=" + contact["normal"].upper()
        + ("" if contact["allow_separation"] else ", no separation"),
    ])
    if contact["self_contact"]:
        lines.extend(["*Contact", "*Contact Inclusions, ALL EXTERIOR"])
    else:
        lines.extend([
            "** Self-contact is switched off by config: explicit SHELL/PLATE surface pairs",
            "** instead of the all-inclusive surface (a self-contact-only domain is empty).",
            "*Surface, name=SHELL_FACES, type=ELEMENT",
            _SHELL_ELSET + ",",
            "*Surface, name=PLATE_FACES, type=ELEMENT",
        ])
        lines.extend(name + "," for name in _PLATE_ELSETS)
        lines.extend(["*Contact", "*Contact Inclusions", "SHELL_FACES, PLATE_FACES"])
    lines.extend(["*Contact Property Assignment", ", , " + _CONTACT_PROP])
    return "\n".join(lines) + "\n"


def _amplitude_lines(simulation, period):
    """Render the compression amplitude (smooth step or linear ramp).

    ``smooth_step`` uses definition=SMOOTH STEP; ``ramp`` uses the default tabular
    definition, whose linear interpolation between the two points is a linear ramp.
    """
    amplitude = simulation["loading"]["amplitude"]
    if amplitude == "smooth_step":
        head = "*Amplitude, name=" + _AMPLITUDE + ", definition=SMOOTH STEP"
    elif amplitude == "ramp":
        head = "*Amplitude, name=" + _AMPLITUDE
    else:
        raise PipelineError("NOT_IMPLEMENTED", "loading.amplitude=" + repr(amplitude))
    return [head, "0.0, 0.0, " + _fmt(period) + ", 1.0"]


def render_step_and_loading(simulation, facts):
    """Render the compression step opening, its amplitude and the RP_TOP U3 loading.

    Two separate procedures, because the keywords genuinely differ:

    * Standard: ``*Dynamic, application=..., initial=...`` plus the increment
      control line (initial, period, minimum, maximum).
    * Explicit: ``*Dynamic, Explicit`` plus only the time period (``, T``); the
      implicit increment controls have no meaning there.

    The amplitude and the loading are identical in both solvers: same amplitude
    shape over the same period and the same mesh-derived target displacement.
    Explicit mass scaling, when enabled by config, is model data and is written
    before the step.
    """
    kind = solver_type(simulation)
    block = solver_block(simulation)
    period = block["time_period_s"]
    target_u3 = facts["target_displacement_mm"]
    subheading = "Compression: eps=%.6g, U3=%.6g mm, T=%.6g s" % (
        simulation["loading"]["target_compression_strain"], target_u3, period)
    lines = []
    if kind == EXPLICIT_DYNAMIC and block["mass_scaling"]["enabled"]:
        lines.extend(["** Explicit mass scaling is ENABLED in solver.explicit_dynamic: it changes",
                      "** the density field, so these results are not directly comparable with an",
                      "** unscaled explicit (or implicit) solution.",
                      "*Fixed Mass Scaling, factor=" + _fmt(block["mass_scaling"]["factor"])])
    lines.extend(_amplitude_lines(simulation, period))
    if kind == STANDARD_DYNAMIC_IMPLICIT:
        lines.append("*Step, name=%s, nlgeom=%s, inc=%d"
                     % (_STEP_NAME, "YES" if block["nlgeom"] else "NO",
                        block["maximum_increments"]))
        lines.append(subheading)
        lines.append("*Dynamic, application=%s, initial=%s" % (
            block["application"].replace("_", " ").upper(),
            "YES" if block["initial_acceleration"] else "NO"))
        lines.append("%s, %s, %s, %s" % (_fmt(block["initial_increment_s"]), _fmt(period),
                                         _fmt(block["minimum_increment_s"]),
                                         _fmt(block["maximum_increment_s"])))
    elif kind == EXPLICIT_DYNAMIC:
        lines.extend(["*Step, name=" + _STEP_NAME, subheading, "*Dynamic, Explicit",
                      ", " + _fmt(period)])
    else:
        raise PipelineError("NOT_IMPLEMENTED", "solver.type=" + repr(kind))
    lines.extend(["*Boundary, amplitude=" + _AMPLITUDE,
                  "RP_TOP, 3, 3, " + _fmt(target_u3)])
    return "\n".join(lines) + "\n"


def render_step_end():
    """Render the step closing keyword; the outputs block is placed before it."""
    return "*End Step\n"


def render_outputs(simulation):
    """Render the field/history output requests in the current solver's syntax.

    Standard samples by increment (``frequency=n``); Explicit samples by time
    (``number interval=`` / ``time interval=``) and accepts no restart frequency.
    The requested variables and regions are the same in both solvers, so the
    extracted curves have the same shape. ``preselect_history_frequency`` > 0 adds
    the extra preselected history group the Standard baseline always wrote; 0
    omits it.

    Sampling frequency of the ``*Energy Output`` / ``*Node Output`` lines is
    deliberately implicit (documented inheritance, not an oversight): they carry
    no sampling parameter, so they inherit the most recent history output state -
    the ``history_frequency`` line (Standard) or the ``history_time_interval_s``
    line (Explicit) rendered just above. Editing their order or inserting a new
    ``*Output, history`` line therefore changes their sampling rate. With
    ``preselect_history_frequency`` > 0 the same whole-model energy history is
    requested twice at two different frequencies, so the ODB holds duplicate
    history keys; the export worker reports them and prefers the plain one
    (RB-023). Writing an explicit frequency on these lines would change the frozen
    Fig.1 deck bytes, so it must first be validated by a real Data Check.
    """
    kind = solver_type(simulation)
    block = solver_block(simulation)
    lines = []
    if kind == STANDARD_DYNAMIC_IMPLICIT:
        lines.append("*Restart, write, frequency=%d" % block["restart_frequency"])
        lines.append("*Output, field, variable=PRESELECT, frequency=%d"
                     % block["field_frequency"])
        lines.append("*Output, history, frequency=%d" % block["history_frequency"])
    elif kind == EXPLICIT_DYNAMIC:
        lines.append("*Output, field, variable=PRESELECT, number interval=%d, time marks=%s"
                     % (block["field_number_interval"],
                        "YES" if block["field_time_marks"] else "NO"))
        lines.append("*Output, history, time interval=" + _fmt(block["history_time_interval_s"]))
    else:
        raise PipelineError("NOT_IMPLEMENTED", "solver.type=" + repr(kind))
    for request in simulation["output"]["requests"]:
        lines.append("*Energy Output" if request["kind"] == "energy"
                     else "*Node Output, nset=%s" % request["region"])
        lines.append(", ".join(request["variables"]))
    if kind == STANDARD_DYNAMIC_IMPLICIT and block["preselect_history_frequency"]:
        lines.append("*Output, history, variable=PRESELECT, frequency=%d"
                     % block["preselect_history_frequency"])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Assembly and the repository-owned static check.
#
# The check understands ONLY the deterministic keyword forms this builder writes.
# It is deliberately not a general Abaqus INP parser and a PASS never claims that
# Abaqus accepted the deck: that judgement belongs to the Data Check stage.
# ---------------------------------------------------------------------------

def _sections(text):
    """Split generated keyword text into (keyword, params, data rows) sections."""
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


def include_paths(text):
    """Ordered *Include input paths of a top-level deck."""
    return [params.get("input", "") for keyword, params, _data in _sections(text)
            if keyword == "*include"]


def _unsafe_include(target):
    if not target or target != target.strip() or "\\" in target or ":" in target:
        return True
    if target.startswith(("/", "~")):
        return True
    parts = target.split("/")
    return ".." in parts or "" in parts or "." in parts


def _defined_regions(texts, order):
    nsets, elsets = set(), set()
    for rel in order:
        for keyword, params, _data in _sections(texts.get(rel, "")):
            if keyword in ("*nset", "*elset", "*element") and "nset" in params:
                nsets.add(params["nset"].upper())
            if keyword in ("*elset", "*element") and "elset" in params:
                elsets.add(params["elset"].upper())
    return nsets, elsets


_OUTPUT_KEYWORDS = ("*restart", "*output", "*energy output", "*node output", "*element output")


def static_checks(folder, files):
    """Run the small static check set over an assembled attempt.

    ``files`` is the deck file map (root + includes) the attempt published. The
    structural checks follow the deck's own include order whenever every include is
    present and safe, so they inspect what Abaqus would actually read.
    Returns {check_name: {"status": "PASS"|"FAILED", "details": [...]}}.
    """
    folder = Path(folder)
    checks = {}

    def record_check(name, problems):
        checks[name] = {"status": "FAILED" if problems else "PASS"}
        if problems:
            checks[name]["details"] = list(problems)

    problems = [rel for rel in (DECK_ROOT,) + INCLUDE_ORDER if not (folder / rel).is_file()]
    record_check("deck_files_present", ["missing file: " + rel for rel in problems])

    problems = []
    for rel, expected in sorted(files.items()):
        path = folder / rel
        if path.is_file() and file_hash(path) != expected:
            problems.append("sha256 changed after assembly: " + rel)
    record_check("deck_sha256", problems)

    texts = {rel: (folder / rel).read_text(encoding="utf-8")
             for rel in (DECK_ROOT,) + INCLUDE_ORDER if (folder / rel).is_file()}
    includes = include_paths(texts.get(DECK_ROOT, ""))
    problems = []
    if includes != list(INCLUDE_ORDER):
        problems.append("include sequence mismatch, got: " + repr(includes))
    for target in includes:
        if _unsafe_include(target):
            problems.append("unsafe include path: " + repr(target))
        elif target not in texts:
            problems.append("include target missing: " + target)
    record_check("include_graph", problems)

    if includes and all(not _unsafe_include(rel) and rel in texts for rel in includes):
        scan_order = includes
    else:
        scan_order = [rel for rel in INCLUDE_ORDER if rel in texts]
    nsets, elsets = _defined_regions(texts, scan_order)
    problems = (["required node set missing: " + name for name in NODE_SETS if name not in nsets]
                + ["required element set missing: " + name for name in ELEMENT_SETS
                   if name not in elsets])
    record_check("region_integrity", problems)

    problems = []
    keywords = []
    for rel in scan_order:
        keywords.extend((rel, keyword) for keyword, _params, _data in _sections(texts[rel]))
    opens = [index for index, (_rel, keyword) in enumerate(keywords) if keyword == "*step"]
    closes = [index for index, (_rel, keyword) in enumerate(keywords) if keyword == "*end step"]
    if len(opens) != 1 or len(closes) != 1 or opens[0] > closes[0]:
        problems.append("expected exactly one *Step before one *End Step, got %d/%d"
                        % (len(opens), len(closes)))
    else:
        for index, (rel, keyword) in enumerate(keywords):
            if keyword in _OUTPUT_KEYWORDS and not opens[0] < index < closes[0]:
                problems.append("%s in %s is not inside the step" % (keyword, rel))
            if keyword == "*amplitude" and index > opens[0]:
                problems.append("*Amplitude must precede the step open")
    record_check("step_structure", problems)
    return checks


def build(npz, report, pairs, simulation_path, output):
    """Build one complete deck from verified mesh outputs and a simulation config.

    The attempt directory is created before any file is written, and a FAILED
    static check keeps the attempt (with a FAILED build_report.json) as evidence
    instead of deleting it. Returns the build report dict.
    """
    simulation = load_simulation(simulation_path)
    folder = reserve_directory(output)
    facts = prepare_ingredients(npz, report, pairs, simulation, folder / _INGREDIENTS_DIR)
    blocks = {
        "material_section": render_material_section(simulation, facts),
        "rigid_platens": render_rigid_platens(simulation, facts),
        "boundary_conditions": render_boundary_conditions(facts),
        "contact": render_contact(simulation),
        "step_loading": render_step_and_loading(simulation, facts),
        "outputs": render_outputs(simulation),
        "step_end": render_step_end(),
    }
    for name, text in blocks.items():
        atomic_text(folder / _BLOCK_FILE[name], text)
    deck_lines = [
        "** physical.inp assembled by physical-builder (M1-7).",
        "** Repository static validation only: this deck proves that the",
        "** deterministic blocks assembled here are internally self-consistent.",
        "** It does NOT claim Abaqus keyword-parser acceptance (that is the M2",
        "** Physical Data Check), solve success, ODB quality or dataset eligibility.",
        "** Fixed assembly order: shell mesh -> material/section -> rigid platens ->",
        "** lateral PBC -> model BCs -> contact -> step/loading -> outputs -> End Step.",
    ]
    deck_lines.extend("*Include, input=" + rel for rel in INCLUDE_ORDER)
    atomic_text(folder / DECK_ROOT, "\n".join(deck_lines) + "\n")
    files = {rel: file_hash(folder / rel) for rel in (DECK_ROOT,) + INCLUDE_ORDER}
    checks = static_checks(folder, files)
    failed = sorted(name for name, result in checks.items() if result["status"] != "PASS")
    document = {
        "stage": "build",
        "status": "STATIC_VALIDATION_FAILED" if failed else "BUILT",
        "case_id": facts["case_id"],
        "deck": {"root": DECK_ROOT,
                 "files": files,
                 "provenance": {_INGREDIENTS_DIR + "/pbc_map.json":
                                file_hash(folder / _INGREDIENTS_DIR / "pbc_map.json")}},
        "model": {"L_mm": facts["L_mm"], "A0_mm2": facts["A0_mm2"],
                  "surface_area_mm2": facts["surface_area_mm2"],
                  "thickness_mm": facts["thickness_mm"],
                  "target_displacement_mm": facts["target_displacement_mm"],
                  "reference_area_mm2": facts["A0_mm2"], "height_mm": facts["L_mm"],
                  "shell_nodes": facts["shell_nodes"], "shell_elements": facts["shell_elements"],
                  "equation_count": facts["equation_count"], "labels": facts["labels"]},
        "solver": {"type": solver_type(simulation),
                   "time_period_s": solver_block(simulation)["time_period_s"],
                   "mass_scaling": (solver_block(simulation)["mass_scaling"]
                                    if solver_type(simulation) == EXPLICIT_DYNAMIC else None)},
        "simulation": simulation,
        "mesh": {"npz": file_hash(npz), "report": file_hash(report), "pairs_csv": file_hash(pairs)},
        "static_checks": checks,
        "static_validation": "FAILED" if failed else "PASS",
        "provenance": {"case_id": facts["case_id"],
                       "config_sha256": file_hash(simulation_path),
                       "physical_inp_sha256": files[DECK_ROOT],
                       **git_provenance(Path(__file__).resolve().parents[1])},
        "claims": {"datacheck": "NOT_RUN", "solve": "NOT_RUN", "dataset_eligible": False},
        "warning": "Static validation only. Abaqus has not been invoked; a PASS here does NOT "
                   "mean Abaqus accepts this deck (that is the datacheck stage) and says nothing "
                   "about solution quality or dataset eligibility.",
    }
    if failed:
        document["failure_reasons"] = ["static check failed: " + name for name in failed]
    write_json(folder / "build_report.json", document)
    if failed:
        raise PipelineError("STATIC_VALIDATION_FAILED",
                            "Static checks failed: " + ", ".join(failed)
                            + "; the attempt was kept for inspection: " + str(folder))
    return document
