# -*- coding: utf-8 -*-

"""Step 01 — Build the periodic topology scaffold.

Purpose
-------
Sample the configured implicit surface on an exactly periodic scalar grid, run
Marching Cubes only as a topology extractor, and verify opposite-face node/edge
periodicity.  This mesh is NOT the final FE mesh.

Inputs:  config/case.json
Outputs: cases/<case>/periodic_topology.npz, topology_report.json
Stop if: internal cracks, non-manifold edges, periodic node/edge mismatch, or
         disconnected glued topology is detected.
"""
import json

import numpy as np
from scipy.spatial import cKDTree
from skimage import measure


# ============================================================
# Central configuration / surface definition
# ============================================================

from meshlib.config import CFG
from meshlib.surface import implicit_xyz, gradient_points, periodic_scalar_field
from meshlib.flags import X0, XL, Y0, YL, Z0, ZL

CASE_ID = CFG.case_id
L = CFG.L
N_INTERVALS = CFG.n_intervals
LEVEL = CFG.level
SNAP_TOL = float(CFG.tol["snap_mm"])
PAIR_TOL = float(CFG.tol["topology_pair_mm"])
OUT_DIR = CFG.case_dir
OUT_NPZ = OUT_DIR / "periodic_topology.npz"
OUT_JSON = OUT_DIR / "topology_report.json"

def implicit_function(x, y, z):
    return implicit_xyz(x, y, z)

def gradient_function(x, y, z):
    p = np.column_stack((np.asarray(x), np.asarray(y), np.asarray(z)))
    return gradient_points(p)


# ============================================================
# Union-Find / Disjoint Set
# ============================================================

class DSU:

    def __init__(self, n):
        self.parent = np.arange(n, dtype=np.int64)
        self.rank = np.zeros(n, dtype=np.int8)

    def find(self, x):

        p = self.parent[x]

        if p != x:
            self.parent[x] = self.find(p)

        return self.parent[x]

    def union(self, a, b):

        ra = self.find(a)
        rb = self.find(b)

        if ra == rb:
            return

        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra

        self.parent[rb] = ra

        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


# ============================================================
# Generate an EXACTLY periodic scalar grid
#
# Important:
# We do NOT evaluate x=L independently.
# The last sample is copied from x=0.
#
# Thus opposite scalar-grid planes are bitwise identical.
# ============================================================

def generate_periodic_field():
    """Build a bitwise-periodic scalar grid from config/case.json."""
    return periodic_scalar_field(N_INTERVALS)


# ============================================================
# Snap vertices exactly onto the six cell planes
# ============================================================

def snap_boundaries(vertices):

    v = vertices.copy()

    for axis in range(3):

        near_min = (
            np.abs(v[:, axis]) < SNAP_TOL
        )

        near_max = (
            np.abs(v[:, axis] - L) < SNAP_TOL
        )

        v[near_min, axis] = 0.0
        v[near_max, axis] = L

    return v


# Boundary flags are imported from meshlib.flags.

def build_boundary_flags(vertices):

    flags = np.zeros(
        len(vertices),
        dtype=np.uint8
    )

    flags[
        np.abs(vertices[:, 0]) < SNAP_TOL
    ] |= X0

    flags[
        np.abs(vertices[:, 0] - L) < SNAP_TOL
    ] |= XL

    flags[
        np.abs(vertices[:, 1]) < SNAP_TOL
    ] |= Y0

    flags[
        np.abs(vertices[:, 1] - L) < SNAP_TOL
    ] |= YL

    flags[
        np.abs(vertices[:, 2]) < SNAP_TOL
    ] |= Z0

    flags[
        np.abs(vertices[:, 2] - L) < SNAP_TOL
    ] |= ZL

    return flags


# ============================================================
# Create node pairing for one pair of periodic faces
# ============================================================

def pair_periodic_nodes(
    vertices,
    flags,
    flag_minus,
    flag_plus,
    complementary_axes,
    name
):

    ids_minus = np.where(
        (flags & flag_minus) != 0
    )[0]

    ids_plus = np.where(
        (flags & flag_plus) != 0
    )[0]

    print("")
    print(name)
    print("  minus nodes =", len(ids_minus))
    print("  plus nodes  =", len(ids_plus))

    if len(ids_minus) != len(ids_plus):

        raise RuntimeError(
            f"{name}: opposite face node counts differ."
        )

    if len(ids_minus) == 0:

        return np.empty(
            (0, 2),
            dtype=np.int64
        )

    A = vertices[
        ids_minus
    ][:, complementary_axes]

    B = vertices[
        ids_plus
    ][:, complementary_axes]

    tree = cKDTree(B)

    dist, index = tree.query(
        A,
        k=1
    )

    if np.max(dist) > PAIR_TOL:

        raise RuntimeError(
            f"{name}: pairing tolerance exceeded. "
            f"max mismatch = {np.max(dist)}"
        )

    if len(np.unique(index)) != len(index):

        raise RuntimeError(
            f"{name}: pairing is not one-to-one."
        )

    pair = np.column_stack(
        [
            ids_minus,
            ids_plus[index]
        ]
    )

    print(
        "  max coordinate mismatch =",
        float(np.max(dist))
    )

    print(
        "  one-to-one pairs =",
        len(pair)
    )

    return pair.astype(np.int64)


# ============================================================
# Extract unique mesh edges
# ============================================================

def build_edges(faces):

    edges = np.vstack(
        [
            faces[:, [0, 1]],
            faces[:, [1, 2]],
            faces[:, [2, 0]]
        ]
    )

    edges = np.sort(
        edges,
        axis=1
    )

    unique_edges, counts = np.unique(
        edges,
        axis=0,
        return_counts=True
    )

    return unique_edges, counts


# ============================================================
# Verify boundary EDGE topology is periodic
#
# This is stronger than checking nodes only.
# ============================================================

def boundary_edges_for_flag(
    edges,
    flags,
    flag
):

    mask = (
        ((flags[edges[:, 0]] & flag) != 0)
        &
        ((flags[edges[:, 1]] & flag) != 0)
    )

    return edges[mask]


def verify_periodic_edge_topology(
    edges,
    flags,
    pair,
    flag_minus,
    flag_plus,
    name
):

    e_minus = boundary_edges_for_flag(
        edges,
        flags,
        flag_minus
    )

    e_plus = boundary_edges_for_flag(
        edges,
        flags,
        flag_plus
    )

    node_map = {
        int(a): int(b)
        for a, b in pair
    }

    mapped_minus = []

    for a, b in e_minus:

        if int(a) not in node_map:
            return False, len(e_minus), len(e_plus)

        if int(b) not in node_map:
            return False, len(e_minus), len(e_plus)

        aa = node_map[int(a)]
        bb = node_map[int(b)]

        mapped_minus.append(
            tuple(sorted((aa, bb)))
        )

    set_mapped = set(mapped_minus)

    set_plus = {
        tuple(sorted((int(a), int(b))))
        for a, b in e_plus
    }

    ok = (
        set_mapped == set_plus
    )

    print("")
    print(name)
    print("  minus boundary edges =", len(e_minus))
    print("  plus boundary edges  =", len(e_plus))
    print("  topology identical   =", ok)

    return ok, len(e_minus), len(e_plus)


# ============================================================
# Build periodic equivalence classes
#
# Example:
# (0,0,z), (L,0,z), (0,L,z), (L,L,z)
# should belong to the same class.
# ============================================================

def build_periodic_classes(
    n_vertices,
    pairs
):

    dsu = DSU(n_vertices)

    for pair in pairs:

        for a, b in pair:
            dsu.union(int(a), int(b))

    roots = np.array(
        [
            dsu.find(i)
            for i in range(n_vertices)
        ],
        dtype=np.int64
    )

    unique_roots, inverse = np.unique(
        roots,
        return_inverse=True
    )

    return (
        inverse.astype(np.int64),
        len(unique_roots)
    )


# ============================================================
# Connectivity
# ============================================================

def count_components(
    n_vertices,
    edges,
    extra_pairs=None
):

    dsu = DSU(n_vertices)

    for a, b in edges:
        dsu.union(int(a), int(b))

    if extra_pairs is not None:

        for pair in extra_pairs:
            for a, b in pair:
                dsu.union(int(a), int(b))

    roots = {
        dsu.find(i)
        for i in range(n_vertices)
    }

    return len(roots)


# ============================================================
# Geometric statistics
# ============================================================

def surface_area(
    vertices,
    faces
):

    p0 = vertices[faces[:, 0]]
    p1 = vertices[faces[:, 1]]
    p2 = vertices[faces[:, 2]]

    cross = np.cross(
        p1 - p0,
        p2 - p0
    )

    area_each = (
        0.5
        * np.linalg.norm(
            cross,
            axis=1
        )
    )

    return (
        float(np.sum(area_each)),
        area_each
    )


# ============================================================
# Main
# ============================================================

def main():

    print("")
    print("================================================")
    print("PERIODIC TOPOLOGY BUILDER")
    print("================================================")
    print("Case =", CASE_ID)

    dx = L / N_INTERVALS

    print("Cell size =", L, "mm")
    print("Sampling dx =", dx, "mm")

    # --------------------------------------------------------
    # Periodic scalar field
    # --------------------------------------------------------

    field = generate_periodic_field()

    print("Field shape =", field.shape)

    print(
        "Exact X scalar periodicity =",
        np.array_equal(
            field[0, :, :],
            field[-1, :, :]
        )
    )

    print(
        "Exact Y scalar periodicity =",
        np.array_equal(
            field[:, 0, :],
            field[:, -1, :]
        )
    )

    print(
        "Exact Z scalar periodicity =",
        np.array_equal(
            field[:, :, 0],
            field[:, :, -1]
        )
    )

    # --------------------------------------------------------
    # Marching Cubes
    #
    # Important:
    # MC is ONLY the topology / geometry extractor.
    # It is NOT our final FE mesh.
    # --------------------------------------------------------

    vertices, faces, _, _ = (
        measure.marching_cubes(
            field,
            level=LEVEL,
            spacing=(dx, dx, dx),
            method="lewiner",
            allow_degenerate=False
        )
    )

    faces = faces.astype(np.int64)

    vertices = snap_boundaries(
        vertices
    )

    print("")
    print("Initial topology mesh:")
    print("  vertices  =", len(vertices))
    print("  triangles =", len(faces))

    # --------------------------------------------------------
    # Boundary classification
    # --------------------------------------------------------

    flags = build_boundary_flags(
        vertices
    )

    # --------------------------------------------------------
    # Periodic node pairs
    # --------------------------------------------------------

    pair_x = pair_periodic_nodes(
        vertices,
        flags,
        X0,
        XL,
        [1, 2],
        "X periodic node pairing"
    )

    pair_y = pair_periodic_nodes(
        vertices,
        flags,
        Y0,
        YL,
        [0, 2],
        "Y periodic node pairing"
    )

    pair_z = pair_periodic_nodes(
        vertices,
        flags,
        Z0,
        ZL,
        [0, 1],
        "Z periodic node pairing"
    )

    # --------------------------------------------------------
    # Mesh edges / manifold test
    # --------------------------------------------------------

    edges, edge_counts = build_edges(
        faces
    )

    free_edges = edges[
        edge_counts == 1
    ]

    nonmanifold_edges = edges[
        edge_counts > 2
    ]

    # A legitimate free edge must lie on at least one
    # cell boundary plane.
    common_boundary_flag = (
        flags[free_edges[:, 0]]
        &
        flags[free_edges[:, 1]]
    )

    internal_free_edges = free_edges[
        common_boundary_flag == 0
    ]

    print("")
    print("Mesh topology:")
    print("  unique edges       =", len(edges))
    print("  free edges         =", len(free_edges))
    print("  internal cracks    =", len(internal_free_edges))
    print("  nonmanifold edges  =", len(nonmanifold_edges))

    # --------------------------------------------------------
    # Strong edge-level periodic verification
    # --------------------------------------------------------

    edge_x_ok, _, _ = (
        verify_periodic_edge_topology(
            edges,
            flags,
            pair_x,
            X0,
            XL,
            "X periodic EDGE topology"
        )
    )

    edge_y_ok, _, _ = (
        verify_periodic_edge_topology(
            edges,
            flags,
            pair_y,
            Y0,
            YL,
            "Y periodic EDGE topology"
        )
    )

    edge_z_ok, _, _ = (
        verify_periodic_edge_topology(
            edges,
            flags,
            pair_z,
            Z0,
            ZL,
            "Z periodic EDGE topology"
        )
    )

    # --------------------------------------------------------
    # Periodic equivalence classes
    # --------------------------------------------------------

    periodic_class, n_classes = (
        build_periodic_classes(
            len(vertices),
            [
                pair_x,
                pair_y,
                pair_z
            ]
        )
    )

    print("")
    print(
        "Periodic equivalence classes =",
        n_classes
    )

    # --------------------------------------------------------
    # Connectivity
    # --------------------------------------------------------

    cut_components = count_components(
        len(vertices),
        edges
    )

    periodic_components = (
        count_components(
            len(vertices),
            edges,
            extra_pairs=[
                pair_x,
                pair_y,
                pair_z
            ]
        )
    )

    print("")
    print(
        "Components in cut cell       =",
        cut_components
    )

    print(
        "Components with periodic glue =",
        periodic_components
    )

    # --------------------------------------------------------
    # Geometry
    # --------------------------------------------------------

    area, area_each = surface_area(
        vertices,
        faces
    )

    grad = gradient_function(
        vertices[:, 0],
        vertices[:, 1],
        vertices[:, 2]
    )

    grad_norm = np.linalg.norm(
        grad,
        axis=1
    )

    residual = np.abs(
        implicit_function(
            vertices[:, 0],
            vertices[:, 1],
            vertices[:, 2]
        )
    )

    print("")
    print("Geometry:")
    print("  surface area =", area, "mm^2")
    print(
        "  max |f(vertex)| =",
        float(np.max(residual))
    )

    print(
        "  min |grad f| =",
        float(np.min(grad_norm))
    )

    print(
        "  1% |grad f| quantile =",
        float(np.quantile(
            grad_norm,
            0.01
        ))
    )

    # --------------------------------------------------------
    # Topology acceptance
    # --------------------------------------------------------

    topology_ok = bool(
        len(internal_free_edges) == 0
        and len(nonmanifold_edges) == 0
        and edge_x_ok
        and edge_y_ok
        and edge_z_ok
        and periodic_components == 1
    )

    # --------------------------------------------------------
    # Save canonical topology file
    # --------------------------------------------------------

    np.savez_compressed(
        OUT_NPZ,

        vertices=vertices.astype(
            np.float64
        ),

        faces=faces.astype(
            np.int64
        ),

        boundary_flags=flags,

        pair_x=pair_x,
        pair_y=pair_y,
        pair_z=pair_z,

        periodic_class=periodic_class,

        free_edges=free_edges.astype(
            np.int64
        )
    )

    report = {

        "case_id": CASE_ID,

        "cell_size_mm": L,

        "n_intervals": N_INTERVALS,

        "sampling_dx_mm": dx,

        "n_vertices": int(
            len(vertices)
        ),

        "n_triangles": int(
            len(faces)
        ),

        "n_edges": int(
            len(edges)
        ),

        "surface_area_mm2": area,

        "n_pair_x": int(
            len(pair_x)
        ),

        "n_pair_y": int(
            len(pair_y)
        ),

        "n_pair_z": int(
            len(pair_z)
        ),

        "x_edge_topology_ok":
            bool(edge_x_ok),

        "y_edge_topology_ok":
            bool(edge_y_ok),

        "z_edge_topology_ok":
            bool(edge_z_ok),

        "internal_free_edges":
            int(
                len(
                    internal_free_edges
                )
            ),

        "nonmanifold_edges":
            int(
                len(
                    nonmanifold_edges
                )
            ),

        "cut_components":
            int(cut_components),

        "periodic_components":
            int(periodic_components),

        "periodic_classes":
            int(n_classes),

        "max_abs_f_at_vertices":
            float(
                np.max(residual)
            ),

        "min_gradient_norm":
            float(
                np.min(grad_norm)
            ),

        "gradient_norm_q01":
            float(
                np.quantile(
                    grad_norm,
                    0.01
                )
            ),

        "topology_ok":
            topology_ok
    }

    with OUT_JSON.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("")
    print("Saved:")
    print(" ", OUT_NPZ)
    print(" ", OUT_JSON)

    print("")
    print("================================================")

    if topology_ok:

        print("TOPOLOGY STATUS: PASS")

    else:

        print("TOPOLOGY STATUS: FAIL")

    print("================================================")

    # In future batch operation:
    # nonzero exit code means this sample stops here,
    # but the entire batch controller can continue.

    if not topology_ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()