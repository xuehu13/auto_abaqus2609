"""diverse_05 硬化材料 Implicit vs Explicit 对比图（含增强版信息框）。

数据（只读）：work/hardening_compare/{implicit,explicit}/diverse_05/
图例放坐标轴右侧外部；信息框放图内右上角空白区（曲线在右侧持续下降，
右上角为安全区，不遮挡曲线）。

    pixi run -e geo -- python -B scripts/make_hardening_compare_figure.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "Arial"],
    "axes.unicode_minus": False,
    "font.size": 11,
})

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "work" / "hardening_compare"
OUT = ROOT / "work" / f"figures_hardening_compare_{datetime.now():%Y%m%dT%H%M%S%f}"


def _case(solver: str) -> Path:
    return BASE / solver / "diverse_05"


def curve(solver: str):
    data = np.loadtxt(_case(solver) / "results" / "stress_strain.csv",
                      delimiter=",", skiprows=1)
    return data[:, 0], data[:, 1]


def status(solver: str) -> dict:
    return json.loads((_case(solver) / "status.json").read_text(encoding="utf-8-sig"))


def summary(solver: str) -> dict:
    return json.loads((_case(solver) / "results" / "summary.json").read_text(encoding="utf-8-sig"))


def total_minutes(st: dict) -> float:
    """完整总计算时长 = 六个 stage 实际耗时之和（min）。"""
    return sum(entry.get("seconds") or 0 for entry in st["stages"].values()) / 60.0


def avg_error(implicit_xy, explicit_xy) -> float:
    """共同应变区间（≥ 0.01，200 点插值）内 Implicit 相对 Explicit 的平均相对误差（%）。"""
    xi, yi = implicit_xy
    xe, ye = explicit_xy
    grid = np.linspace(max(xi.min(), xe.min(), 0.01), min(xi.max(), xe.max()), 200)
    si = np.interp(grid, xi, yi)
    se = np.interp(grid, xe, ye)
    return float(np.mean(np.abs(si - se) / np.maximum(np.abs(se), 1e-6)) * 100.0)


def main() -> None:
    # Windows/Pixi：先加载 linalg，避免 Matplotlib 排版时延迟加载 DLL 失败。
    np.linalg.inv(np.eye(2))
    OUT.mkdir(parents=True, exist_ok=False)

    implicit_xy, explicit_xy = curve("implicit"), curve("explicit")
    st_i, st_e = status("implicit"), status("explicit")
    sm_i, sm_e = summary("implicit"), summary("explicit")

    err = avg_error(implicit_xy, explicit_xy)
    minutes_e = total_minutes(st_e)
    minutes_i = total_minutes(st_i)
    peak_e = float(explicit_xy[1].max())
    peak_i = float(implicit_xy[1].max())
    peak_diff = abs(peak_i - peak_e) / peak_e * 100.0
    solve_e = st_e["stages"]["solve"]["seconds"]
    solve_i = st_i["stages"]["solve"]["seconds"]

    fig, ax = plt.subplots(figsize=(13.5, 7.5))
    ax.plot(implicit_xy[0], implicit_xy[1], "-", color="#d62728", lw=2.6,
            label=("Implicit（Standard *Dynamic, T=1.0 s，硬化材料）\n"
                   f"solve {solve_i:.0f} s，总时长 {minutes_i:.2f} min，"
                   f"KE/IE={sm_i['max_ke_ie_ratio']:.4f}"))
    ax.plot(explicit_xy[0], explicit_xy[1], "--", color="#1f77b4", lw=2.0,
            label=("Explicit（*Dynamic Explicit, T=0.02 s，硬化材料）\n"
                   f"solve {solve_e:.0f} s，总时长 {minutes_e:.2f} min，"
                   f"KE/IE={sm_e['max_ke_ie_ratio']:.4f}"))

    ax.set_title("diverse_05：Implicit（T=1.0 s）与 Explicit（T=0.02 s）"
                 "工程应力–应变对比\n同一硬化材料，20% 压缩，cpus=8",
                 fontsize=13.5, fontweight="bold")
    ax.set_xlabel("工程应变", fontsize=12.5)
    ax.set_ylabel("工程应力 (MPa)", fontsize=12.5)
    ax.set_xlim(-0.005, 0.215)
    ax.set_ylim(-0.012, 0.30)
    ax.grid(True, alpha=0.25, linewidth=0.6)

    # ---- 增强版信息框（图内右上角；曲线在右侧持续下降，右上为空白安全区）----
    box = "\n".join([
        "对比摘要",
        f"平均误差 = {err:.2f}%",
        "",
        "计算时长",
        f"Explicit = {minutes_e:.2f} min",
        f"Implicit = {minutes_i:.2f} min",
        f"耗时比（Implicit / Explicit） = {minutes_i / minutes_e:.2f}×",
        "",
        "峰值应力",
        f"Explicit = {peak_e:.4f} MPa",
        f"Implicit = {peak_i:.4f} MPa",
        f"差异 = {peak_diff:.2f}%",
        "",
        "最终应变",
        f"Explicit = {float(explicit_xy[0][-1]):.4f}",
        f"Implicit = {float(implicit_xy[0][-1]):.4f}",
    ])
    ax.text(0.545, 0.975, box, transform=ax.transAxes, ha="left", va="top",
            fontsize=9, linespacing=1.35, zorder=5,
            bbox=dict(boxstyle="round,pad=0.5", fc="white", ec="#9db4cc",
                      lw=1.1, alpha=0.96))

    fig.text(0.5, 0.012,
             "平均误差 = 应变 ≥ 0.01 区间内 Implicit 相对 Explicit 的平均相对误差；"
             "耗时比 = Implicit 总时长 ÷ Explicit 总时长",
             ha="center", fontsize=9, color="0.35")
    # 图例放图内右下角：该区域曲线已降至 y < 0.09 MPa，完全空白，不遮挡曲线
    ax.legend(loc="lower right", fontsize=10, framealpha=0.95, borderaxespad=0.8)
    fig.tight_layout(rect=(0, 0.035, 1, 1))

    for ext in ("png", "svg"):
        fig.savefig(OUT / f"13_hardening_compare.{ext}", dpi=300)
    plt.close(fig)
    print(f"生成 {OUT / '13_hardening_compare.png'} / .svg")
    print(f"平均误差={err:.2f}% | 总时长 I={minutes_i:.2f} E={minutes_e:.2f} min | "
          f"耗时比={minutes_i / minutes_e:.2f}× | 峰值差={peak_diff:.2f}%")


if __name__ == "__main__":
    main()
