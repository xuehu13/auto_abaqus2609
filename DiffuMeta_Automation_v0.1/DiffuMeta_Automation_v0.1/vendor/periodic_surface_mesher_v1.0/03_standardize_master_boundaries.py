# -*- coding: utf-8 -*-

"""Step 03 — Standardize and project the master cut curves.

Purpose
-------
Replace irregular Marching-Cubes boundary segmentation by nearly uniform
arc-length samples, solve exact cube-edge endpoints, and project all curve points
back to f=0.  These curves become protected CGAL features.

Inputs : periodic_topology.npz, master_boundary_curves.npz
Outputs: standard_boundary_curves.npz, standard_boundary_report.json
"""
import json

import numpy as np
from scipy.optimize import brentq


# ============================================================
# Central configuration / surface definition
# ============================================================

from meshlib.config import CFG
from meshlib.surface import implicit_points, gradient_points
from meshlib.flags import X0, XL, Y0, YL, Z0, ZL, MASTER_FACE_NAMES, MASTER_FIXED_AXIS

CASE_ID = CFG.case_id
L = CFG.L
CASE_DIR = CFG.case_dir
TOPOLOGY_FILE = CASE_DIR / "periodic_topology.npz"
CURVE_FILE = CASE_DIR / "master_boundary_curves.npz"
OUTPUT_NPZ = CASE_DIR / "standard_boundary_curves.npz"
OUTPUT_JSON = CASE_DIR / "standard_boundary_report.json"
TARGET_MAX_SPACING = CFG.boundary_spacing
REDISTRIBUTE_ITERS = 3
F_TOL = 1.0e-11
MAX_PROJECTION_ITERS = 30
MAX_STEP = 0.05
BOUNDARY_TOL = float(CFG.tol["boundary_mm"])

def implicit_function(p):
    return float(np.asarray(implicit_points(np.asarray(p, dtype=np.float64))))

def gradient_function(p):
    return np.asarray(gradient_points(np.asarray(p, dtype=np.float64)), dtype=np.float64)


# ============================================================
# Boundary flag helpers
# ============================================================

def boundary_axes_from_flag(flag_value):

    axes = set()

    if (
        (flag_value & X0) != 0
        or
        (flag_value & XL) != 0
    ):
        axes.add(0)

    if (
        (flag_value & Y0) != 0
        or
        (flag_value & YL) != 0
    ):
        axes.add(1)

    if (
        (flag_value & Z0) != 0
        or
        (flag_value & ZL) != 0
    ):
        axes.add(2)

    return axes


def canonicalize_periodic_point(p):

    q = np.asarray(
        p,
        dtype=np.float64
    ).copy()

    for axis in range(3):

        if (
            abs(q[axis]) < BOUNDARY_TOL
            or
            abs(q[axis] - L)
            < BOUNDARY_TOL
        ):
            q[axis] = 0.0

    return q


def lift_endpoint_to_original_edge(
    canonical,
    flag_value
):

    q = canonical.copy()

    if (flag_value & X0) != 0:
        q[0] = 0.0

    if (flag_value & XL) != 0:
        q[0] = L

    if (flag_value & Y0) != 0:
        q[1] = 0.0

    if (flag_value & YL) != 0:
        q[1] = L

    if (flag_value & Z0) != 0:
        q[2] = 0.0

    if (flag_value & ZL) != 0:
        q[2] = L

    return q


# ============================================================
# Exact cube-edge root
#
# Every open boundary curve endpoint lies on
# intersection of two cube faces.
#
# We solve f=0 along the remaining free coordinate.
# ============================================================

def solve_edge_root(
    initial_point,
    fixed_axes
):

    fixed_axes = sorted(
        list(fixed_axes)
    )

    if len(fixed_axes) == 3:

        q = canonicalize_periodic_point(
            initial_point
        )

        residual = abs(
            implicit_function(q)
        )

        if residual > 1.0e-8:
            raise RuntimeError(
                "Cube-corner endpoint does not "
                "satisfy f=0."
            )

        return q

    if len(fixed_axes) != 2:

        raise RuntimeError(
            "Expected endpoint to lie on exactly "
            "two cube-boundary axes."
        )

    free_axis = list(
        {0, 1, 2}
        - set(fixed_axes)
    )[0]

    q0 = canonicalize_periodic_point(
        initial_point
    )

    guess = float(
        q0[free_axis]
    )

    # --------------------------------------------------------
    # First try local Newton
    # --------------------------------------------------------

    q = q0.copy()

    converged = False

    for _ in range(
        MAX_PROJECTION_ITERS
    ):

        f = implicit_function(q)

        if abs(f) < F_TOL:

            converged = True
            break

        g = gradient_function(q)

        deriv = g[free_axis]

        if abs(deriv) < 1.0e-12:
            break

        step = -f / deriv

        step = float(
            np.clip(
                step,
                -MAX_STEP,
                MAX_STEP
            )
        )

        q[free_axis] += step

        q[free_axis] = float(
            np.clip(
                q[free_axis],
                0.0,
                L
            )
        )

    if converged:

        q[fixed_axes] = 0.0

        return q

    # --------------------------------------------------------
    # Robust fallback:
    # scan entire cube edge and use Brent roots.
    # Choose root nearest original MC endpoint.
    # --------------------------------------------------------

    sample = np.linspace(
        0.0,
        L,
        4001
    )

    values = []

    for t in sample:

        qq = q0.copy()

        qq[fixed_axes] = 0.0
        qq[free_axis] = t

        values.append(
            implicit_function(qq)
        )

    values = np.asarray(
        values
    )

    roots = []

    for i in range(
        len(sample) - 1
    ):

        f0 = values[i]
        f1 = values[i + 1]

        if abs(f0) < F_TOL:

            roots.append(
                sample[i]
            )

            continue

        if f0 * f1 < 0.0:

            def scalar_func(t):

                qq = q0.copy()

                qq[fixed_axes] = 0.0
                qq[free_axis] = t

                return implicit_function(
                    qq
                )

            root = brentq(
                scalar_func,
                sample[i],
                sample[i + 1],
                xtol=1.0e-13
            )

            roots.append(root)

    if len(roots) == 0:

        raise RuntimeError(
            "Could not locate exact cube-edge "
            "intersection root."
        )

    roots = np.asarray(
        roots,
        dtype=np.float64
    )

    # periodic distance
    d = np.abs(
        roots - guess
    )

    d = np.minimum(
        d,
        L - d
    )

    root = roots[
        np.argmin(d)
    ]

    q = q0.copy()

    q[fixed_axes] = 0.0
    q[free_axis] = root

    if abs(
        implicit_function(q)
    ) > 1.0e-9:

        raise RuntimeError(
            "Edge root projection residual "
            "too large."
        )

    return q


# ============================================================
# Projection onto one master-face curve
#
# Example X0:
# x stays exactly 0,
# only y,z are moved.
# ============================================================

def project_to_master_face(
    point,
    face_id
):

    q = np.asarray(
        point,
        dtype=np.float64
    ).copy()

    fixed_axis = (
        MASTER_FIXED_AXIS[
            face_id
        ]
    )

    q[fixed_axis] = 0.0

    free_axes = [
        a
        for a in range(3)
        if a != fixed_axis
    ]

    total_move = 0.0

    for _ in range(
        MAX_PROJECTION_ITERS
    ):

        f = implicit_function(q)

        if abs(f) < F_TOL:

            break

        g = gradient_function(q)

        gt = np.zeros(3)

        gt[free_axes] = (
            g[free_axes]
        )

        denom = float(
            np.dot(gt, gt)
        )

        if denom < 1.0e-14:

            raise RuntimeError(
                "Boundary projection encountered "
                "near-zero in-plane gradient."
            )

        delta = (
            -f / denom
        ) * gt

        length = float(
            np.linalg.norm(delta)
        )

        if length > MAX_STEP:

            delta *= (
                MAX_STEP
                / length
            )

            length = MAX_STEP

        q += delta

        q[fixed_axis] = 0.0

        total_move += length

        # Large movement suggests wrong branch
        if total_move > 0.25:

            raise RuntimeError(
                "Boundary projection moved too far "
                "from initial curve."
            )

        for axis in free_axes:

            if (
                q[axis]
                < -1.0e-7
                or
                q[axis]
                > L + 1.0e-7
            ):

                raise RuntimeError(
                    "Projection escaped master "
                    "face domain."
                )

            q[axis] = float(
                np.clip(
                    q[axis],
                    0.0,
                    L
                )
            )

    residual = abs(
        implicit_function(q)
    )

    if residual > 1.0e-9:

        raise RuntimeError(
            "Master-face projection failed: "
            f"|f| = {residual}"
        )

    return q


# ============================================================
# Polyline resampling
# ============================================================

def cumulative_lengths(
    coords,
    closed
):

    if closed:

        extended = np.vstack(
            [
                coords,
                coords[0]
            ]
        )

    else:

        extended = coords

    seg = np.linalg.norm(
        extended[1:]
        -
        extended[:-1],
        axis=1
    )

    s = np.concatenate(
        [
            [0.0],
            np.cumsum(seg)
        ]
    )

    return extended, s


def interpolate_polyline(
    coords,
    n_segments,
    closed
):

    extended, s = (
        cumulative_lengths(
            coords,
            closed
        )
    )

    total = float(
        s[-1]
    )

    if total <= 0.0:

        raise RuntimeError(
            "Zero-length boundary curve."
        )

    if closed:

        targets = np.linspace(
            0.0,
            total,
            n_segments,
            endpoint=False
        )

    else:

        targets = np.linspace(
            0.0,
            total,
            n_segments + 1
        )

    result = np.empty(
        (len(targets), 3),
        dtype=np.float64
    )

    for axis in range(3):

        result[:, axis] = np.interp(
            targets,
            s,
            extended[:, axis]
        )

    return result


# ============================================================
# Build endpoint classes once
# ============================================================

def build_endpoint_class_data(
    vertices,
    boundary_flags,
    periodic_class,
    curve_ids,
    offsets,
    curve_closed
):

    endpoint_records = {}

    n_curves = len(
        offsets
    ) - 1

    for i in range(n_curves):

        if curve_closed[i]:
            continue

        ids = curve_ids[
            offsets[i]:
            offsets[i + 1]
        ]

        for node_id in (
            int(ids[0]),
            int(ids[-1])
        ):

            pclass = int(
                periodic_class[
                    node_id
                ]
            )

            endpoint_records.setdefault(
                pclass,
                []
            ).append(node_id)

    canonical = {}

    for pclass, nodes in (
        endpoint_records.items()
    ):

        # Determine which coordinate axes define
        # the cube edge.
        axis_sets = [
            boundary_axes_from_flag(
                boundary_flags[node]
            )
            for node in nodes
        ]

        reference_axes = axis_sets[0]

        for axes in axis_sets[1:]:

            if axes != reference_axes:

                raise RuntimeError(
                    "Periodic endpoint class has "
                    "inconsistent cube-edge axes. "
                    f"class={pclass}"
                )

        # Use all representatives to estimate
        # the free coordinate robustly.
        representatives = []

        for node in nodes:

            q = canonicalize_periodic_point(
                vertices[node]
            )

            representatives.append(q)

        representatives = np.asarray(
            representatives
        )

        initial = np.median(
            representatives,
            axis=0
        )

        for axis in reference_axes:
            initial[axis] = 0.0

        exact = solve_edge_root(
            initial,
            reference_axes
        )

        canonical[pclass] = exact

    return canonical


# ============================================================
# Main
# ============================================================

def main():

    print()
    print(
        "================================================"
    )
    print(
        "STANDARDIZE MASTER PERIODIC BOUNDARIES"
    )
    print(
        "================================================"
    )

    topo = np.load(
        TOPOLOGY_FILE
    )

    curves = np.load(
        CURVE_FILE
    )

    vertices = topo[
        "vertices"
    ].astype(np.float64)

    boundary_flags = topo[
        "boundary_flags"
    ]

    periodic_class = topo[
        "periodic_class"
    ]

    curve_ids = curves[
        "curve_vertex_ids"
    ]

    offsets = curves[
        "curve_offsets"
    ]

    curve_face_id = curves[
        "curve_face_id"
    ]

    curve_closed = curves[
        "curve_closed"
    ]

    n_curves = (
        len(offsets) - 1
    )

    # --------------------------------------------------------
    # Solve every shared cube-edge endpoint once
    # --------------------------------------------------------

    canonical_endpoints = (
        build_endpoint_class_data(
            vertices,
            boundary_flags,
            periodic_class,
            curve_ids,
            offsets,
            curve_closed
        )
    )

    print()
    print(
        "Canonical endpoint classes =",
        len(canonical_endpoints)
    )

    for pclass in sorted(
        canonical_endpoints
    ):

        q = canonical_endpoints[
            pclass
        ]

        print(
            " class",
            pclass,
            "->",
            q,
            "|f| =",
            abs(
                implicit_function(q)
            )
        )

    # --------------------------------------------------------
    # Standardize each master curve
    # --------------------------------------------------------

    packed_points = []
    new_offsets = [0]

    out_face_ids = []
    out_closed = []

    start_classes = []
    end_classes = []

    curve_reports = []

    for i in range(n_curves):

        ids = curve_ids[
            offsets[i]:
            offsets[i + 1]
        ]

        old_coords = vertices[
            ids
        ].copy()

        face_id = int(
            curve_face_id[i]
        )

        closed = bool(
            curve_closed[i]
        )

        face_name = (
            MASTER_FACE_NAMES[
                face_id
            ]
        )

        curve_name = (
            f"{face_name}_curve_"
            f"{sum(curve_face_id[:i] == face_id):03d}"
        )

        # -----------------------------------------------
        # Replace old open endpoints by exact,
        # shared cube-edge roots
        # -----------------------------------------------

        if not closed:

            start_node = int(
                ids[0]
            )

            end_node = int(
                ids[-1]
            )

            start_class = int(
                periodic_class[
                    start_node
                ]
            )

            end_class = int(
                periodic_class[
                    end_node
                ]
            )

            old_coords[0] = (
                lift_endpoint_to_original_edge(
                    canonical_endpoints[
                        start_class
                    ],
                    boundary_flags[
                        start_node
                    ]
                )
            )

            old_coords[-1] = (
                lift_endpoint_to_original_edge(
                    canonical_endpoints[
                        end_class
                    ],
                    boundary_flags[
                        end_node
                    ]
                )
            )

        else:

            start_class = -1
            end_class = -1

        # -----------------------------------------------
        # Determine number of new segments
        # from old geometric arc length
        # -----------------------------------------------

        _, s_old = (
            cumulative_lengths(
                old_coords,
                closed
            )
        )

        old_length = float(
            s_old[-1]
        )

        n_segments = max(
            3 if closed else 1,
            int(
                np.ceil(
                    old_length
                    /
                    TARGET_MAX_SPACING
                )
            )
        )

        # -----------------------------------------------
        # Initial equal-arc resampling
        # -----------------------------------------------

        new_coords = (
            interpolate_polyline(
                old_coords,
                n_segments,
                closed
            )
        )

        # -----------------------------------------------
        # Project to exact implicit intersection
        # -----------------------------------------------

        for j in range(
            len(new_coords)
        ):

            # exact open-curve endpoints
            # are handled separately
            if (
                not closed
                and
                (
                    j == 0
                    or
                    j == len(
                        new_coords
                    ) - 1
                )
            ):
                continue

            new_coords[j] = (
                project_to_master_face(
                    new_coords[j],
                    face_id
                )
            )

        if not closed:

            new_coords[0] = (
                old_coords[0]
            )

            new_coords[-1] = (
                old_coords[-1]
            )

        # -----------------------------------------------
        # A few equalization iterations:
        # resample -> reproject
        # -----------------------------------------------

        for _ in range(
            REDISTRIBUTE_ITERS
        ):

            new_coords = (
                interpolate_polyline(
                    new_coords,
                    n_segments,
                    closed
                )
            )

            for j in range(
                len(new_coords)
            ):

                if (
                    not closed
                    and
                    (
                        j == 0
                        or
                        j == len(
                            new_coords
                        ) - 1
                    )
                ):
                    continue

                new_coords[j] = (
                    project_to_master_face(
                        new_coords[j],
                        face_id
                    )
                )

            if not closed:

                new_coords[0] = (
                    old_coords[0]
                )

                new_coords[-1] = (
                    old_coords[-1]
                )

        # -----------------------------------------------
        # Final metrics
        # -----------------------------------------------

        extended, s_new = (
            cumulative_lengths(
                new_coords,
                closed
            )
        )

        seg = np.linalg.norm(
            extended[1:]
            -
            extended[:-1],
            axis=1
        )

        new_length = float(
            np.sum(seg)
        )

        residuals = np.array(
            [
                abs(
                    implicit_function(p)
                )
                for p in new_coords
            ]
        )

        print()
        print(
            "---------------------------------------------"
        )
        print(curve_name)
        print(
            "---------------------------------------------"
        )

        print(
            "face             =",
            face_name
        )

        print(
            "closed           =",
            closed
        )

        print(
            "old nodes        =",
            len(ids)
        )

        print(
            "new nodes        =",
            len(new_coords)
        )

        print(
            "new segments     =",
            len(seg)
        )

        print(
            "old length       =",
            old_length
        )

        print(
            "new length       =",
            new_length
        )

        print(
            "segment min      =",
            float(seg.min())
        )

        print(
            "segment mean     =",
            float(seg.mean())
        )

        print(
            "segment max      =",
            float(seg.max())
        )

        print(
            "max |f|          =",
            float(
                residuals.max()
            )
        )

        if not closed:

            print(
                "start pclass     =",
                start_class
            )

            print(
                "end pclass       =",
                end_class
            )

        packed_points.extend(
            new_coords.tolist()
        )

        new_offsets.append(
            len(packed_points)
        )

        out_face_ids.append(
            face_id
        )

        out_closed.append(
            closed
        )

        start_classes.append(
            start_class
        )

        end_classes.append(
            end_class
        )

        curve_reports.append(
            {
                "curve_index":
                    i,

                "name":
                    curve_name,

                "master_face":
                    face_name,

                "closed":
                    closed,

                "old_nodes":
                    int(len(ids)),

                "new_nodes":
                    int(
                        len(new_coords)
                    ),

                "n_segments":
                    int(len(seg)),

                "old_length_mm":
                    old_length,

                "new_length_mm":
                    new_length,

                "segment_min_mm":
                    float(seg.min()),

                "segment_mean_mm":
                    float(seg.mean()),

                "segment_median_mm":
                    float(
                        np.median(seg)
                    ),

                "segment_max_mm":
                    float(seg.max()),

                "max_abs_f":
                    float(
                        residuals.max()
                    ),

                "start_periodic_class":
                    start_class,

                "end_periodic_class":
                    end_class,
            }
        )

    packed_points = np.asarray(
        packed_points,
        dtype=np.float64
    )

    # --------------------------------------------------------
    # Strong final endpoint consistency test
    #
    # For each periodic class, all representatives
    # mapped back to canonical [0,L) coordinates
    # must be identical.
    # --------------------------------------------------------

    class_representatives = {}

    for i in range(n_curves):

        if out_closed[i]:
            continue

        pts = packed_points[
            new_offsets[i]:
            new_offsets[i + 1]
        ]

        for pclass, point in [
            (
                start_classes[i],
                pts[0]
            ),
            (
                end_classes[i],
                pts[-1]
            ),
        ]:

            q = canonicalize_periodic_point(
                point
            )

            class_representatives.setdefault(
                pclass,
                []
            ).append(q)

    max_endpoint_mismatch = 0.0

    for pclass, reps in (
        class_representatives.items()
    ):

        reps = np.asarray(reps)

        ref = reps[0]

        mismatch = np.max(
            np.linalg.norm(
                reps - ref,
                axis=1
            )
        )

        max_endpoint_mismatch = max(
            max_endpoint_mismatch,
            float(mismatch)
        )

    # --------------------------------------------------------
    # Global boundary quality summary
    # --------------------------------------------------------

    all_segments = []

    max_f = 0.0

    for i in range(n_curves):

        pts = packed_points[
            new_offsets[i]:
            new_offsets[i + 1]
        ]

        extended, _ = (
            cumulative_lengths(
                pts,
                out_closed[i]
            )
        )

        seg = np.linalg.norm(
            extended[1:]
            -
            extended[:-1],
            axis=1
        )

        all_segments.extend(
            seg.tolist()
        )

        for p in pts:

            max_f = max(
                max_f,
                abs(
                    implicit_function(p)
                )
            )

    all_segments = np.asarray(
        all_segments
    )

    print()
    print(
        "================================================"
    )
    print(
        "STANDARDIZED BOUNDARY SUMMARY"
    )
    print(
        "================================================"
    )

    print(
        "Total master curves =",
        n_curves
    )

    print(
        "Total new points    =",
        len(packed_points)
    )

    print(
        "Segment minimum     =",
        all_segments.min()
    )

    print(
        "Segment q05         =",
        np.quantile(
            all_segments,
            0.05
        )
    )

    print(
        "Segment mean        =",
        all_segments.mean()
    )

    print(
        "Segment median      =",
        np.median(
            all_segments
        )
    )

    print(
        "Segment q95         =",
        np.quantile(
            all_segments,
            0.95
        )
    )

    print(
        "Segment maximum     =",
        all_segments.max()
    )

    print(
        "Segments < 0.05     =",
        np.count_nonzero(
            all_segments < 0.05
        )
    )

    print(
        "Segments < 0.10     =",
        np.count_nonzero(
            all_segments < 0.10
        )
    )

    print(
        "Segments > 0.20     =",
        np.count_nonzero(
            all_segments > 0.20
        )
    )

    print(
        "Max |f|             =",
        max_f
    )

    print(
        "Endpoint periodic mismatch =",
        max_endpoint_mismatch
    )

    # --------------------------------------------------------
    # Save canonical endpoint table
    # --------------------------------------------------------

    endpoint_classes = np.array(
        sorted(
            canonical_endpoints.keys()
        ),
        dtype=np.int64
    )

    endpoint_coords = np.array(
        [
            canonical_endpoints[
                int(k)
            ]
            for k
            in endpoint_classes
        ],
        dtype=np.float64
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    np.savez_compressed(
        OUTPUT_NPZ,

        curve_points=
            packed_points,

        curve_offsets=
            np.asarray(
                new_offsets,
                dtype=np.int64
            ),

        curve_face_id=
            np.asarray(
                out_face_ids,
                dtype=np.int8
            ),

        curve_closed=
            np.asarray(
                out_closed,
                dtype=bool
            ),

        curve_start_class=
            np.asarray(
                start_classes,
                dtype=np.int64
            ),

        curve_end_class=
            np.asarray(
                end_classes,
                dtype=np.int64
            ),

        endpoint_classes=
            endpoint_classes,

        endpoint_canonical_coords=
            endpoint_coords,

        master_face_names=
            np.asarray(
                MASTER_FACE_NAMES
            )
    )

    report = {

        "case_id":
            CASE_ID,

        "target_max_spacing_mm":
            TARGET_MAX_SPACING,

        "redistribution_iterations":
            REDISTRIBUTE_ITERS,

        "n_master_curves":
            n_curves,

        "n_master_points":
            int(
                len(packed_points)
            ),

        "segment_min_mm":
            float(
                all_segments.min()
            ),

        "segment_q05_mm":
            float(
                np.quantile(
                    all_segments,
                    0.05
                )
            ),

        "segment_mean_mm":
            float(
                all_segments.mean()
            ),

        "segment_median_mm":
            float(
                np.median(
                    all_segments
                )
            ),

        "segment_q95_mm":
            float(
                np.quantile(
                    all_segments,
                    0.95
                )
            ),

        "segment_max_mm":
            float(
                all_segments.max()
            ),

        "n_segment_lt_005":
            int(
                np.count_nonzero(
                    all_segments
                    < 0.05
                )
            ),

        "n_segment_lt_010":
            int(
                np.count_nonzero(
                    all_segments
                    < 0.10
                )
            ),

        "n_segment_gt_020":
            int(
                np.count_nonzero(
                    all_segments
                    > 0.20
                )
            ),

        "max_abs_f":
            float(max_f),

        "max_endpoint_periodic_mismatch":
            float(
                max_endpoint_mismatch
            ),

        "curves":
            curve_reports,
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    print()
    print("Saved:")
    print(" ", OUTPUT_NPZ)
    print(" ", OUTPUT_JSON)

    # --------------------------------------------------------
    # Conservative acceptance
    #
    # We deliberately keep acceptance mild here.
    # Final FE quality belongs to later validator.
    # --------------------------------------------------------

    pass_status = bool(
        max_f < 1.0e-8
        and
        max_endpoint_mismatch
        < 1.0e-10
        and
        np.count_nonzero(
            all_segments < 0.05
        ) == 0
        and
        np.count_nonzero(
            all_segments > 0.20
        ) == 0
    )

    print()
    print(
        "================================================"
    )

    if pass_status:

        print(
            "STANDARD BOUNDARY STATUS: PASS"
        )

    else:

        print(
            "STANDARD BOUNDARY STATUS: FAIL"
        )

    print(
        "================================================"
    )

    if not pass_status:
        raise SystemExit(3)


if __name__ == "__main__":
    main()