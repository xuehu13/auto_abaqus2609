"""para_aly：24 组参数敏感性实验的计算时长总览表（单张表格图）。

只读 work/para_aly/<mesh>/<T>/<MS>/<case>/status.json（六阶段耗时求和），
输出 09_runtime_summary_table 的 PNG/SVG/CSV 与 readme。不重跑、不修改任何结果。

    pixi run -e geo -- python -B scripts/make_para_aly_runtime_table.py
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
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "work" / "para_aly"
OUT_DIR = ROOT / "work" / f"figures_para_aly_runtime_{datetime.now():%Y%m%dT%H%M%S%f}"

SURFACES = (("diverse_05", "构型1"), ("diverse_04", "构型2"), ("diverse_28", "构型3"))

MESH_LABEL = {
    "Fine": ("细网格", "0.18 / 0.18 / 0.15 mm"),
    "Coarse": ("粗网格", "0.25 / 0.25 / 0.25 mm"),
}
T_LABEL = {"T0p02": "0.02", "T0p01": "0.01"}
MS_LABEL = {"MS0": "关闭（不进行质量缩放）", "MS9": "9 倍"}

#: 表格行序（用户指定）：内部键 -> (行号, 网格, 时间, 质量缩放, 是否基准行)
TABLE_ROWS = [
    ("Fine", "T0p02", "MS0", True),
    ("Fine", "T0p02", "MS9", False),
    ("Fine", "T0p01", "MS0", False),
    ("Fine", "T0p01", "MS9", False),
    ("Coarse", "T0p02", "MS0", False),
    ("Coarse", "T0p02", "MS9", False),
    ("Coarse", "T0p01", "MS0", False),
    ("Coarse", "T0p01", "MS9", False),
]

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "Arial"],
    "axes.unicode_minus": False,
})


def collect() -> dict:
    """读取 24 个 case 的六阶段总耗时（min）。全部 DONE 才返回，否则抛错。"""
    data = {}
    for mesh in ("Fine", "Coarse"):
        for t in ("T0p01", "T0p02"):
            for ms in ("MS0", "MS9"):
                for case, config in SURFACES:
                    case_dir = DATA_ROOT / mesh / t / ms / case
                    status_path = case_dir / "status.json"
                    if not status_path.is_file():
                        raise RuntimeError(f"缺少 status.json：{status_path}")
                    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
                    if status.get("status") != "DONE":
                        raise RuntimeError(f"算例不是 DONE：{mesh}/{t}/{ms}/{case} "
                                           f"-> {status.get('status')}")
                    seconds = sum((entry or {}).get("seconds") or 0
                                  for entry in (status.get("stages") or {}).values())
                    if seconds <= 0:
                        raise RuntimeError(f"无法读取可靠耗时：{mesh}/{t}/{ms}/{case}")
                    data[(mesh, t, ms, case)] = seconds / 60.0
    return data


def main():
    # Windows/Pixi：先加载 linalg，避免 Matplotlib 排版时延迟加载 DLL 失败。
    np.linalg.inv(np.eye(2))
    OUT_DIR.mkdir(parents=True, exist_ok=False)
    data = collect()
    print(f"已核对：24/24 个算例均为 DONE，耗时全部可读。")

    # ---- 聚合 8 行 ----
    rows = []
    for mesh, t, ms, is_base in TABLE_ROWS:
        values = [data[(mesh, t, ms, case)] for case, _ in SURFACES]
        rows.append({
            "mesh": mesh, "t": t, "ms": ms, "is_base": is_base,
            "per_config": values,
            "avg": sum(values) / 3.0,
            "total": sum(values),
        })
    baseline_avg = rows[0]["avg"]
    for row in rows:
        row["speedup"] = baseline_avg / row["avg"]

    # ---- 配对参数影响（其他两个参数相同）----
    def pair_effect(dim, before_value, after_value):
        """在另外两个参数相同的配对组合间，计算 before → after 的平均加速倍数
        （= before 组平均时长 ÷ after 组平均时长），以及两组各自的平均时长。"""
        ratios, before_vals, after_vals = [], [], []
        for row_a in rows:
            for row_b in rows:
                same = sum([row_a["mesh"] == row_b["mesh"],
                            row_a["t"] == row_b["t"],
                            row_a["ms"] == row_b["ms"]])
                if same != 2:
                    continue
                if row_a[dim] != before_value or row_b[dim] != after_value:
                    continue
                ratios.append(row_a["avg"] / row_b["avg"])
                before_vals.append(row_a["avg"])
                after_vals.append(row_b["avg"])
        return (float(np.mean(ratios)), float(min(ratios)), float(max(ratios)),
                float(np.mean(before_vals)), float(np.mean(after_vals)))

    mesh_eff = pair_effect("mesh", "Fine", "Coarse")
    t_eff = pair_effect("t", "T0p02", "T0p01")
    ms_eff = pair_effect("ms", "MS0", "MS9")

    # ---- 输出 CSV（24 行真实参数与时长）----
    csv_path = OUT_DIR / "09_runtime_summary_table.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["网格密度及尺寸（mm）", "分析步时间 T（s）", "质量缩放系数",
                         "构型", "总计算时长（min，六阶段之和）"])
        for mesh, t, ms, _ in TABLE_ROWS:
            mesh_name, mesh_size = MESH_LABEL[mesh]
            for case, config in SURFACES:
                writer.writerow([f"{mesh_name}（{mesh_size}）", T_LABEL[t], MS_LABEL[ms],
                                 config, f"{data[(mesh, t, ms, case)]:.2f}"])
    print(f"写出 {csv_path}")

    # ---- 绘表 ----
    fig = plt.figure(figsize=(16, 9))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    fig.text(0.5, 0.965, "24组参数敏感性实验：计算时长总览",
             ha="center", fontsize=19, fontweight="bold")
    fig.text(0.5, 0.928, "3种构型 × 2种网格密度 × 2个分析步时间 × 2种质量缩放设置",
             ha="center", fontsize=12, color="0.3")

    # 列布局（9 列，10 个边界）
    col_x = [0.020, 0.155, 0.255, 0.400, 0.505, 0.610, 0.715, 0.825, 0.935, 0.990]
    col_c = [(col_x[i] + col_x[i + 1]) / 2 for i in range(9)]
    headers = ["网格密度及尺寸（mm）", "分析步时间\nT（s）", "质量缩放系数",
               "构型1\n（min）", "构型2\n（min）", "构型3\n（min）",
               "平均时长\n（min/例）", "三构型总时长\n（min）", "相对基准\n加速倍数"]
    row_y = [0.775 - 0.068 * i for i in range(8)]
    row_h = 0.058

    # 表头
    ax.add_patch(plt.Rectangle((col_x[0], row_y[0] + row_h / 2 + 0.010),
                               col_x[-1] - col_x[0], 0.062, fc="#2f4f6f", ec="none"))
    for cx, head in zip(col_c, headers):
        ax.text(cx, row_y[0] + row_h / 2 + 0.041, head, ha="center", va="center",
                fontsize=11.5, fontweight="bold", color="white", linespacing=1.25)

    # 热力色阶（浅绿 = 短，浅橙红 = 长）
    all_values = [v for row in rows for v in row["per_config"]]
    vmin, vmax = min(all_values), max(all_values)
    cmap = LinearSegmentedColormap.from_list("time_heat", ["#dff2d8", "#fde8c8", "#f5b09a"])
    norm = plt.Normalize(vmin=vmin, vmax=vmax)

    for index, row in enumerate(rows):
        y = row_y[index]
        mesh_name, mesh_size = MESH_LABEL[row["mesh"]]
        row_face = "#fffbe6" if row["is_base"] else "white"
        ax.add_patch(plt.Rectangle((col_x[0], y - row_h / 2 - 0.006),
                                   col_x[-1] - col_x[0], row_h + 0.012,
                                   fc=row_face, ec="0.85", lw=0.6, zorder=1))
        for offset, value in zip((3, 4, 5), row["per_config"]):
            ax.add_patch(plt.Rectangle((col_x[offset] + 0.003, y - row_h / 2 - 0.004),
                                       col_x[offset + 1] - col_x[offset] - 0.006,
                                       row_h + 0.008, fc=cmap(norm(value)),
                                       ec="0.8", lw=0.4, zorder=2))
        mesh_text = f"{mesh_name}\n{mesh_size}"
        if row["is_base"]:
            mesh_text += "\n（基准组）"
        ax.text(col_c[0], y, mesh_text, ha="center", va="center",
                fontsize=10.5, fontweight="bold" if row["is_base"] else "normal",
                linespacing=1.35, zorder=3)
        ax.text(col_c[1], y, T_LABEL[row["t"]], ha="center", va="center",
                fontsize=12, zorder=3)
        ax.text(col_c[2], y, MS_LABEL[row["ms"]], ha="center", va="center",
                fontsize=10.5, zorder=3)
        for offset, value in zip((3, 4, 5), row["per_config"]):
            ax.text(col_c[offset], y, f"{value:.2f}", ha="center", va="center",
                    fontsize=11.5, zorder=3)
        ax.text(col_c[6], y, f"{row['avg']:.2f}", ha="center", va="center",
                fontsize=12, fontweight="bold", zorder=3)
        ax.text(col_c[7], y, f"{row['total']:.2f}", ha="center", va="center",
                fontsize=11.5, zorder=3)
        speed_text = "1.00×" if row["is_base"] else f"{row['speedup']:.2f}×"
        ax.text(col_c[8], y, speed_text, ha="center", va="center",
                fontsize=12, fontweight="bold", zorder=3)

    # 细/粗两组之间的分隔线
    sep_y = (row_y[3] + row_y[4]) / 2
    ax.plot([col_x[0], col_x[-1]], [sep_y, sep_y], color="#4a6a8a", lw=2.2,
            solid_capstyle="butt", zorder=4)

    # 表注
    fig.text(0.020, 0.245,
             "注：网格尺寸依次为 周期边界目标间距 / CGAL 边缘网格尺寸 / CGAL 表面网格目标尺寸；"
             "耗时 = mesh → mesh数据检查 → 建模 → 数据检查 → 求解 → 提取 六阶段实际耗时之和。",
             fontsize=9, color="0.35")

    # ---- 三条结论 ----
    conclusions = [
        ("网格密度影响",
         f"其他参数相同时，细网格（0.18 / 0.18 / 0.15 mm）→ 粗网格（0.25 / 0.25 / 0.25 mm）："
         f"平均总时长 {mesh_eff[3]:.1f} → {mesh_eff[4]:.1f} min，"
         f"平均加速 {mesh_eff[0]:.2f}×（{mesh_eff[1]:.2f}–{mesh_eff[2]:.2f}×）。"),
        ("分析步时间影响",
         f"其他参数相同时，T = 0.02 s → 0.01 s："
         f"平均总时长 {t_eff[3]:.1f} → {t_eff[4]:.1f} min，"
         f"平均加速 {t_eff[0]:.2f}×（{t_eff[1]:.2f}–{t_eff[2]:.2f}×）。"),
        ("质量缩放影响",
         f"其他参数相同时，质量缩放由关闭 → 9 倍："
         f"平均总时长 {ms_eff[3]:.1f} → {ms_eff[4]:.1f} min，"
         f"平均加速 {ms_eff[0]:.2f}×（{ms_eff[1]:.2f}–{ms_eff[2]:.2f}×）。"),
    ]
    ax.text(0.020, 0.185, "参数对计算时长的影响（基于全部 24 个实际算例的配对比较，其他两个参数保持相同）",
            fontsize=11.5, fontweight="bold")
    y_conc = 0.140
    for name, conc_text in conclusions:
        ax.text(0.020, y_conc, "■", fontsize=10, color="#4a6a8a")
        ax.text(0.033, y_conc, name + "：", fontsize=10.5, fontweight="bold",
                color="#2f4f6f")
        ax.text(0.128, y_conc, conc_text, fontsize=10.5)
        y_conc -= 0.047

    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"09_runtime_summary_table.{ext}", dpi=300)
    plt.close(fig)
    print(f"生成 {OUT_DIR / '09_runtime_summary_table.png'} 与 .svg")

    # ---- readme ----
    lines = [
        "09_runtime_summary_table —— 数据来源与计算方法",
        "=" * 46,
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        "",
        "数据来源：全部 24 个算例（3 构型 × 2 网格 × 2 分析步时间 × 2 质量缩放），",
        "  每个算例的 status.json（work/para_aly/<网格>/<时间>/<缩放>/<构型>/status.json），",
        "  耗时 = mesh → mesh_datacheck → build → datacheck → solve → extract 六阶段",
        "  实际耗时之和（分钟），全部 24 例核对为 DONE。",
        "",
        "基准组：细网格（0.18 / 0.18 / 0.15 mm）+ 分析步时间 0.02 s + 质量缩放关闭。",
        "相对基准加速倍数 = 基准组平均时长 ÷ 当前组平均时长（基准组 = 1.00×）。",
        "",
        "三个参数影响的计算方法：仅在其余两个参数完全相同的配对组合之间计算",
        "平均时长比值，再取 4 组配对的平均值与范围（不做任何估算）。",
        f"  网格密度（细→粗，0.18→0.25 mm）：平均加速 {mesh_eff[0]:.2f}×"
        f"（{mesh_eff[1]:.2f}–{mesh_eff[2]:.2f}×）",
        f"  分析步时间（0.02→0.01 s）：平均加速 {t_eff[0]:.2f}×"
        f"（{t_eff[1]:.2f}–{t_eff[2]:.2f}×）",
        f"  质量缩放（关闭→9 倍）：平均加速 {ms_eff[0]:.2f}×"
        f"（{ms_eff[1]:.2f}–{ms_eff[2]:.2f}×）",
        "",
        "配套文件：09_runtime_summary_table.csv（24 行逐算例真实参数与时长）。",
    ]
    (OUT_DIR / "09_runtime_summary_table_readme.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8")
    print(f"生成 {OUT_DIR / '09_runtime_summary_table_readme.txt'}")

    # ---- 终端摘要 ----
    print()
    for row in rows:
        mesh_name, mesh_size = MESH_LABEL[row["mesh"]]
        speed = "1.00×" if row["is_base"] else f"{row['speedup']:.2f}×"
        print(f"{mesh_name}({mesh_size}) T={T_LABEL[row['t']]} {MS_LABEL[row['ms']]}: "
              f"构型 {['%.2f' % v for v in row['per_config']]} min | "
              f"avg {row['avg']:.2f} | total {row['total']:.2f} | {speed}")
    print(f"参数影响：mesh {mesh_eff[0]:.2f}×({mesh_eff[1]:.2f}-{mesh_eff[2]:.2f}) | "
          f"T {t_eff[0]:.2f}×({t_eff[1]:.2f}-{t_eff[2]:.2f}) | "
          f"MS {ms_eff[0]:.2f}×({ms_eff[1]:.2f}-{ms_eff[2]:.2f})")


if __name__ == "__main__":
    main()
