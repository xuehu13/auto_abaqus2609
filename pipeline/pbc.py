"""Lateral diagonal macro-strain PBC using one representative per equivalence class.

Internal node indices are zero based. Coefficients store signed integer cell jumps.
Every dependent DOF appears only in its own equation. No eliminated DOF is reused.
"""
from collections import defaultdict, deque

from .common import PipelineError


def relations(x_pairs, y_pairs, rotations=True):
    graph = defaultdict(list)
    edges = []
    for axis, pairs in enumerate((x_pairs, y_pairs)):
        step = (1, 0) if axis == 0 else (0, 1)
        for low, high in pairs:
            low, high = int(low), int(high)
            if low == high:
                raise PipelineError("PBC_INVALID", "Pair references the same node.")
            edges.append((low, high, step))
            graph[low].append((high, step))
            graph[high].append((low, tuple(-n for n in step)))
    potentials, representatives = {}, {}
    rows = []
    components = 0
    for root in sorted(graph):
        if root in potentials:
            continue
        components += 1
        potentials[root] = (0, 0)
        representatives[root] = root
        queue = deque([root])
        members = []
        while queue:
            parent = queue.popleft()
            members.append(parent)
            for child, delta in sorted(graph[parent]):
                candidate = tuple(a + b for a, b in zip(potentials[parent], delta))
                if child in potentials:
                    if potentials[child] != candidate:
                        raise PipelineError("PBC_CYCLE_INCONSISTENT", "Periodic jumps do not close around a cycle.")
                else:
                    potentials[child] = candidate
                    representatives[child] = root
                    queue.append(child)
        for node in sorted(members):
            if node != root:
                rows.append({"node": node, "root": root, "shift": list(potentials[node])})
    for low, high, delta in edges:
        if tuple(b - a for a, b in zip(potentials[low], potentials[high])) != delta:
            raise PipelineError("PBC_INVALID", "An original pair is not represented.")
    dependent = {row["node"] for row in rows}
    if dependent & {row["root"] for row in rows}:
        raise PipelineError("PBC_ELIMINATION_CONFLICT", "Dependent node reused as representative.")
    return {"mode": "lateral_xy_diagonal", "index_base": 0,
            "rotations": bool(rotations), "raw_pairs": len(edges),
            "boundary_nodes": len(graph), "classes": components,
            "independent_relations": len(rows), "removed_relations": len(edges) - len(rows),
            "equation_count": len(rows) * (6 if rotations else 3), "relations": rows}


def render_include(mapping, rp_x, rp_y):
    node_ids = {r[k] + 1 for r in mapping["relations"] for k in ("node", "root")}
    if rp_x == rp_y or rp_x in node_ids or rp_y in node_ids:
        raise PipelineError("PBC_LABEL_COLLISION", "Macro control labels overlap shell nodes.")
    lines = ["** Lateral PBC. Flat-model global labels; include AFTER node definitions.",
             "** RP_X uses DOF 1 only; RP_Y uses DOF 2 only; do not constrain these free macro DOFs."]
    for row in mapping["relations"]:
        for dof in range(1, 7 if mapping["rotations"] else 4):
            terms = [(row["node"] + 1, dof, 1), (row["root"] + 1, dof, -1)]
            if dof in (1, 2) and row["shift"][dof - 1]:
                terms.append((rp_x if dof == 1 else rp_y, dof, -row["shift"][dof - 1]))
            lines.extend(["*Equation", str(len(terms)),
                          ", ".join(str(v) for term in terms for v in term)])
    return "\n".join(lines) + "\n"
