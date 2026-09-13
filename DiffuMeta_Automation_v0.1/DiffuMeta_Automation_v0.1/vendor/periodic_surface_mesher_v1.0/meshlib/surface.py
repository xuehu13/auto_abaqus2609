"""Single source of truth for the implicit surface in Python.

The user writes the dimensionless periodic expression once in ``config/case.json``
using X, Y, Z (each has period 2*pi).  SymPy builds both f and its analytical
physical-coordinate gradient automatically, so the equation/gradient cannot drift
apart between stages.
"""
from __future__ import annotations

import numpy as np
import sympy as sp
from .config import CFG

X, Y, Z = sp.symbols("X Y Z", real=True)
_ALLOWED = {
    "X": X, "Y": Y, "Z": Z,
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
    "exp": sp.exp, "sqrt": sp.sqrt, "Abs": sp.Abs, "abs": sp.Abs,
    "pi": sp.pi,
}

_EXPR = sp.sympify(CFG.expression, locals=_ALLOWED)
_DX = sp.diff(_EXPR, X)
_DY = sp.diff(_EXPR, Y)
_DZ = sp.diff(_EXPR, Z)

_F = sp.lambdify((X, Y, Z), _EXPR, modules="numpy")
_GX = sp.lambdify((X, Y, Z), _DX, modules="numpy")
_GY = sp.lambdify((X, Y, Z), _DY, modules="numpy")
_GZ = sp.lambdify((X, Y, Z), _DZ, modules="numpy")


def _angles(x, y, z):
    s = 2.0 * np.pi / CFG.L
    return s * np.asarray(x), s * np.asarray(y), s * np.asarray(z)


def implicit_xyz(x, y, z):
    """Evaluate f(x,y,z) in physical millimetre coordinates."""
    a, b, c = _angles(x, y, z)
    return np.asarray(_F(a, b, c), dtype=np.float64)


def implicit_points(points):
    """Evaluate f at [...,3] points."""
    p = np.asarray(points, dtype=np.float64)
    return implicit_xyz(p[..., 0], p[..., 1], p[..., 2])


def gradient_points(points):
    """Analytical gradient df/d(x,y,z) in physical coordinates."""
    p = np.asarray(points, dtype=np.float64)
    a, b, c = _angles(p[..., 0], p[..., 1], p[..., 2])
    scale = 2.0 * np.pi / CFG.L
    gx = np.asarray(_GX(a, b, c), dtype=np.float64) * scale
    gy = np.asarray(_GY(a, b, c), dtype=np.float64) * scale
    gz = np.asarray(_GZ(a, b, c), dtype=np.float64) * scale
    gx, gy, gz = np.broadcast_arrays(gx, gy, gz)
    return np.stack((gx, gy, gz), axis=-1)


def gradient_magnitude(points):
    return np.linalg.norm(gradient_points(points), axis=-1)


def periodic_scalar_field(n_intervals: int | None = None):
    """Build a bitwise-periodic (n+1)^3 scalar grid for Marching Cubes.

    The final plane in every direction is copied from the first plane instead of
    evaluating 2*pi independently.  That exact copy is essential for exact
    opposite-face topology.
    """
    n = int(n_intervals or CFG.n_intervals)
    theta = 2.0 * np.pi * np.arange(n, dtype=np.float64) / n
    a = theta[:, None, None]
    b = theta[None, :, None]
    c = theta[None, None, :]
    base = np.asarray(_F(a, b, c), dtype=np.float64)
    base = np.broadcast_to(base, (n, n, n)).copy()
    fx = np.concatenate((base, base[:1, :, :]), axis=0)
    fxy = np.concatenate((fx, fx[:, :1, :]), axis=1)
    fxyz = np.concatenate((fxy, fxy[:, :, :1]), axis=2)
    return fxyz


def describe() -> str:
    return f"f(X,Y,Z) = {sp.sstr(_EXPR)}; L = {CFG.L} mm"
