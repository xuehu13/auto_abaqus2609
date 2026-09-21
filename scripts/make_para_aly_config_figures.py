"""para_aly：每个构型一张“8 条参数组合曲线”对比图（共 3 张，只读结果）。

基准曲线 = 最密网格（0.18/0.18/0.15 mm）+ T=0.02 s + 质量缩放关闭（黑色粗实线）。
其余 7 条虚线、互不同色；图例放坐标轴右侧外部，含参数、计算时长与相对基准的
平均误差（应变 ≥ 0.01 的共同区间插值对齐后计算）。

    pixi run -e geo -- python -B scripts/make_para_aly_config_figures.py
"""
from __future__ import annotations

import csv
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
DATA_ROOT = ROOT / "work" / "para_aly"
OUT_DIR = ROOT / "work" / f"figures_para_aly_configs_{datetime.now():%Y%m%dT%H%M%S%f}"

SURFACES = (("diverse_05", "构型1"), ("diverse_04", "构型2"), ("diverse_28", "构型3"))
BASELINE = ("Fine", "T0p02", "MS0")
BASELINE_LABEL_MESH = "最密网格（0.18/0.18/0.15 mm）"

#: 8 条曲线：内部 (mesh, T, MS) + 面向读者的网格说明。基准排第一。
VARIANTS = [
    (("Fine", "T0p02", "MS0"), "最密网格（0.18/0.18/0.15 mm）", True),
    (("Fine", "T0p02", "MS9"), "最密网格（0.18/0.18/0.15 mm）", False),
    (("Fine", "T0p01", "MS0"), "最密网格（0.18/0.18/0.15 mm）", False),
    (("Fine", "T0p01", "MS9"), "最密网格（0.18/0.18/0.15 mm）", False),
    (("Coarse", "T0p02", "MS0"), "粗网格（0.25/0.25/0.25 mm）", False),
    (("Coarse", "T0p02", "MS9"), "粗网格（0.25/0.25/0.25 mm）", False),
    (("Coarse", "T0p01", "MS0"), "粗网格（0.25/0.25/0.25 mm）", False),
    (("Coarse", "T0p01", "MS9"), "粗网格（0.25/0.25/0.25 mm）", False),
]
NONBASE_COLORS = ["#d62728", "#2ca02c", "#ff7f0e", "#9467bd",
                  "#8c564b", "#e377c2", "#17becf"]
BASELINE_COLOR = "#1f4e79"
EPS = 1e-6
ERROR_STRAIN_MIN = 0.01
ERROR_GRID_N = 200


def case_dir(mesh, t, ms, case):
    return DATA_ROOT / mesh / t / ms / case


def elapsed_minutes(case_path: Path):
    status_path = case_path / "status.json"
    if not status_path.is_file():
        return None
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    seconds = sum((entry or {}).get("seconds") or 0
                  for entry in (status.get("stages") or {}).values())
    return round(seconds / 60.0, 2) if seconds else None


def stress_curve(case_path: Path):
    data = np.loadtxt(case_path / "results" / "stress_strain.csv",
                      delimiter=",", skiprows=1)
    return data[:, 0], data[:, 1]


def average_error(curve_a, curve_b):
    """共同应变区间（strain ≥ 0.01）插值对齐后的平均相对误差（%）。"""
    xa, ya = curve_a
    xb, yb = curve_b
    lo = max(xa.min(), xb.min(), ERROR_STRAIN_MIN)
    hi = min(xa.max(), xb.max())
    if hi <= lo:
        return None
    grid = np.linspace(lo, hi, ERROR_GRID_N)
    sa = np.interp(grid, xa, ya)
    sb = np.interp(grid, xb, yb)
    return float(np.mean(np.abs(sa - sb) / np.maximum(np.abs(sb), EPS)) * 100.0)


def main():
    # Windows/Pixi：先加载 linalg，避免 Matplotlib 排版时延迟加载 DLL 失败。
    np.linalg.inv(np.eye(2))
    OUT_DIR.mkdir(parents=True, exist_ok=False)

    # ---- 绘图前检查：24 例 DONE、曲线文件齐全、耗时可读 ----
    print("绘图前检查 ...")
    problems = []
    for mesh in ("Fine", "Coarse"):
        for t in ("T0p01", "T0p02"):
            for ms in ("MS0", "MS9"):
                for case, _ in SURFACES:
                    cdir = case_dir(mesh, t, ms, case)
                    status_path = cdir / "status.json"
                    if not status_path.is_file():
                        problems.append(f"缺少 status.json: {cdir}")
                        continue
                    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
                    if status.get("status") != "DONE":
                        problems.append(f"不是 DONE: {mesh}/{t}/{ms}/{case}")
                    if not (cdir / "results" / "stress_strain.csv").is_file():
                        problems.append(f"缺少 stress_strain.csv: {cdir}")
                    if elapsed_minutes(cdir) is None:
                        problems.append(f"无法读取耗时: {cdir}")
    if problems:
        for item in problems:
            print("[问题] " + item)
        raise RuntimeError(f"绘图前检查发现 {len(problems)} 个问题，停止。")
    print("  24/24 个 case 均为 DONE，数据与耗时齐全。")

    manifest_rows = []

    for case, config_name in SURFACES:
        figure_name = {"构型1": "10_config1", "构型2": "11_config2",
                       "构型3": "12_config3"}[config_name]
        fig, ax = plt.subplots(figsize=(13.5, 6.5))
        curves = {}

        for variant_index, ((mesh, t, ms), mesh_desc, is_base) in enumerate(VARIANTS):
            cdir = case_dir(mesh, t, ms, case)
            minutes = elapsed_minutes(cdir)
            x, y = stress_curve(cdir)
            curves[(mesh, t, ms)] = (x, y)
            if is_base:
                continue
            error = average_error(curves[BASELINE], (x, y))
            error_text = f"{error:.2f}%" if error is not None else "N/A"
            color = NONBASE_COLORS[variant_index - 1]
            t_display = {"T0p01": "0.01", "T0p02": "0.02"}[t]
            ms_display = "9倍" if ms == "MS9" else "关闭"
            label = (f"{mesh_desc}，T={t_display} s，质量缩放={ms_display}\n"
                     f"计算时长={minutes:.2f} min，平均误差={error_text}")
            ax.plot(x, y, "--", color=color, lw=1.5, label=label)
            manifest_rows.append({
                "figure_name": figure_name, "case_id": case,
                "构型名称": config_name, "网格说明": mesh_desc,
                "T_s": float(t.replace("T0p", "0.")),
                "mass_scaling": "9倍" if ms == "MS9" else "关闭",
                "elapsed_time_min": minutes,
                "average_error_percent": round(error, 2) if error is not None else None,
                "source_case_path": str(cdir)})

        base_x, base_y = curves[BASELINE]
        base_minutes = elapsed_minutes(case_dir(*BASELINE, case))
        ax.plot(base_x, base_y, "-", color=BASELINE_COLOR, lw=2.8,
                label=(f"基准：{BASELINE_LABEL_MESH}，T=0.02 s\n"
                       f"质量缩放=关闭，计算时长={base_minutes:.2f} min，平均误差=0.00%"))
        manifest_rows.append({
            "figure_name": figure_name, "case_id": case,
            "构型名称": config_name, "网格说明": BASELINE_LABEL_MESH,
            "T_s": 0.02, "mass_scaling": "关闭",
            "elapsed_time_min": base_minutes,
            "average_error_percent": 0.0,
            "source_case_path": str(case_dir(*BASELINE, case))})

        ax.set_title(f"{config_name}：不同参数组合下的工程应力–应变曲线", fontsize=14)
        ax.set_xlabel("工程应变", fontsize=12)
        ax.set_ylabel("工程应力 (MPa)", fontsize=12)
        ax.set_xlim(-0.005, 0.215)
        ax.grid(True, alpha=0.25, linewidth=0.6)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=8.8,
                  framealpha=0.9, borderaxespad=0)
        fig.text(0.5, 0.008,
                 f"基准：{BASELINE_LABEL_MESH}，T = 0.02 s，质量缩放 = 关闭；"
                 "平均误差 = 应变 ≥ 0.01 区间内与基准插值对齐后的平均相对误差",
                 ha="center", fontsize=9, color="0.35")
        fig.tight_layout(rect=(0, 0.03, 0.72, 1))

        for ext in ("png", "svg"):
            fig.savefig(OUT_DIR / f"{figure_name}_all_cases_stress_strain.{ext}", dpi=300)
        plt.close(fig)
        print(f"生成 {figure_name}_all_cases_stress_strain.png / .svg（{config_name}，8 条曲线）")

    # ---- manifest ----
    manifest_path = OUT_DIR / "all_cases_curve_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "figure_name", "case_id", "构型名称", "网格说明", "T_s", "mass_scaling",
            "elapsed_time_min", "average_error_percent", "source_case_path"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    # ---- readme ----
    lines = [
        "all_cases 曲线图说明（10/11/12 三张图）",
        "=" * 46,
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "1. 图与构型对应：10 = 构型1（diverse_05）、11 = 构型2（diverse_04）、",
        "   12 = 构型3（diverse_28）；每张图 8 条曲线 = 该构型全部 8 组参数组合。",
        "2. 基准曲线 = 最密网格（0.18/0.18/0.15 mm）+ T = 0.02 s + 质量缩放关闭，",
        "   深蓝粗实线；其余 7 条为虚线。",
        "3. 平均误差 = 在共同应变区间（应变 ≥ 0.01，200 个插值点）内，",
        "   |当前应力 − 基准应力| / max(基准应力, 1e-6) 的平均值 × 100%。",
        "   基准前期应力接近 0，因此未采用 < 0.01 的区间。",
        "4. 计算时长 = status.json 中 mesh → mesh_datacheck → build → datacheck →",
        "   solve → extract 六阶段实际耗时之和（分钟）。",
        "5. 输出文件：本目录下 10/11/12_configN_all_cases_stress_strain.png/.svg，",
        "   以及 all_cases_curve_manifest.csv（每条曲线的来源与时长/误差）。",
        "6. 数据处理：若 history/stress_strain 缺失或耗时不可读，会在终端与本文件",
        "   报告并停止（本次运行无缺失）；列名按不区分大小写自动匹配。",
    ]
    (OUT_DIR / "all_cases_curve_readme.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")

    print()
    print(f"manifest：{manifest_path}")
    print(f"readme  ：{OUT_DIR / 'all_cases_curve_readme.txt'}")


if __name__ == "__main__":
    main()
