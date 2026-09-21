"""para_aly 结果绘图：8 张 PPT 曲线图（只读结果，不改任何计算产物）。

数据源：work/para_aly/<mesh>/<T>/<MS>/<case>/results/
输出：  work/figures_para_aly_ppt_<时间戳>/（PNG 300dpi + SVG + manifest + readme）。

每条曲线旁标注该 case 的总计算耗时（status.json 各 stage 秒数之和，单位 min）。
Implicit 对照在 work/para_aly/implicit 下自动搜索（diverse_05，20% 压缩）。

    pixi run -e geo -- python -B scripts/make_para_aly_ppt_figures.py
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "work" / "para_aly"
OUT_DIR = ROOT / "work" / f"figures_para_aly_ppt_{datetime.now():%Y%m%dT%H%M%S%f}"

SURFACES = ("diverse_05", "diverse_04", "diverse_28")
CONFIG_NAMES = {"diverse_05": "构型1", "diverse_04": "构型2", "diverse_28": "构型3"}
COLORS = {"diverse_05": "#1f77b4", "diverse_04": "#d62728", "diverse_28": "#2ca02c"}

plt.rcParams.update({
    "font.family": ["Microsoft YaHei", "Arial"],
    "axes.unicode_minus": False,
    "font.size": 11,
})

#: 三张参数对比图的定义：(tag, 固定条件说明, 标题前缀, 变体列表)
#: 变体 = (variant_key, 线型, 图例后缀, mesh, T, MS)
FIGURE_SPECS = [
    ("01_T_effect", "mesh=Fine，MS0", "分析步时间 T 的影响", [
        ("T0p01", "实线", "T=0.01 s", "Fine", "T0p01", "MS0"),
        ("T0p02", "虚线", "T=0.02 s", "Fine", "T0p02", "MS0"),
    ]),
    ("03_MS_effect", "mesh=Fine，T=0.02 s", "质量缩放的影响", [
        ("MS0", "实线", "MS0", "Fine", "T0p02", "MS0"),
        ("MS9", "虚线", "MS9", "Fine", "T0p02", "MS9"),
    ]),
    ("05_mesh_effect", "T=0.02 s，MS0", "网格密度的影响", [
        ("Fine", "实线", "Fine", "Fine", "T0p02", "MS0"),
        ("Coarse", "虚线", "Coarse", "Coarse", "T0p02", "MS0"),
    ]),
]


def case_dir(mesh, t, ms, case):
    return DATA_ROOT / mesh / t / ms / case


def implicit_elapsed_minutes(parent_dir: Path):
    """隐式 case 被 1500s 墙钟截断后由 orphan 分析跑完：status.json 不含 solve 时长。
    改用 run.log 的 solve 起点到 solve ODB 最终写入时间的差值（真实 solve 墙钟，分钟）。"""
    import re as _re
    run_log = parent_dir / "run.log"
    odbs = sorted((parent_dir / "abaqus").glob("*_solve.odb"))
    if not run_log.is_file() or not odbs:
        return None
    start = None
    for line in run_log.read_text(encoding="utf-8", errors="replace").splitlines():
        match = _re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\+00:00 \| solve\s+start", line)
        if match:
            start = match.group(1)
    if start is None:
        return None
    start = datetime.fromisoformat(start + "+00:00")
    end = datetime.fromtimestamp(odbs[-1].stat().st_mtime, tz=timezone.utc)
    return round((end - start).total_seconds() / 60.0, 2)


def elapsed_minutes(case_path: Path):
    """总耗时 = status.json 各 stage 秒数之和（mesh/build/datacheck/solve/extract）。"""
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


def _find_column(fieldnames, *names):
    lowered = {name.strip().lower(): name for name in fieldnames}
    for name in names:
        if name.lower() in lowered:
            return lowered[name.lower()]
    return None


def quasi_static_curve(case_path: Path):
    """(strain, KE/IE)；strain = -U3/10；ALLIE≈0 或非有限值时置 NaN。缺列返回 None。"""
    path = case_path / "results" / "history.csv"
    if not path.is_file():
        return None
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        u3_col = _find_column(fields, "U3_mm", "U3")
        ke_col = _find_column(fields, "ALLKE")
        ie_col = _find_column(fields, "ALLIE")
        if u3_col is None or ke_col is None or ie_col is None:
            return None
        strains, ratios = [], []
        for row in reader:
            try:
                strain = -float(row[u3_col]) / 10.0
                ke, ie = float(row[ke_col]), float(row[ie_col])
            except (TypeError, ValueError):
                continue
            ratio = ke / ie if abs(ie) > 1e-9 else np.nan
            strains.append(strain)
            ratios.append(ratio if np.isfinite(ratio) else np.nan)
    return np.asarray(strains), np.asarray(ratios)


def annotate_times(ax, items, y_span):
    """在曲线末端右侧标注耗时；按 y 排序并上下错开避免重叠。items: (x,y,text,color)。"""
    if not items:
        return
    min_gap = y_span * 0.055
    placed_y = []
    for x_end, y_end, text, color in sorted(items, key=lambda item: item[1]):
        y_text = y_end
        while any(abs(y_text - other) < min_gap for other in placed_y):
            y_text += min_gap
        placed_y.append(y_text)
        ax.annotate(text, xy=(x_end, y_end), xytext=(x_end + 0.004, y_text),
                    fontsize=8.5, color=color, va="center", ha="left",
                    arrowprops=dict(arrowstyle="-", color=color, lw=0.6,
                                    alpha=0.5, shrinkA=0, shrinkB=2))


def finish_figure(fig, ax, title, fixed_note, legend_loc):
    ax.set_title(title, fontsize=13)
    ax.set_xlabel("工程应变")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    fig.text(0.5, 0.008, "固定条件：" + fixed_note,
             ha="center", fontsize=9, color="0.35")
    ax.legend(loc=legend_loc, framealpha=0.88, fontsize=10)
    fig.tight_layout(rect=(0, 0.035, 1, 1))


def save_figure(fig, name):
    for ext in ("png", "svg"):
        fig.savefig(OUT_DIR / f"{name}.{ext}", dpi=300)
    plt.close(fig)
    print(f"生成 {name}.png / .svg")


def main():
    # Windows/Pixi：先加载 linalg，避免 Matplotlib 排版时延迟加载 DLL 失败。
    np.linalg.inv(np.eye(2))
    OUT_DIR.mkdir(parents=True, exist_ok=False)
    manifest_rows, readme_lines = [], [
        "para_aly PPT 曲线图说明",
        "=" * 40,
        "每条曲线旁的数字 = 该 case 总计算耗时（status.json 各 stage 秒数之和，分钟）。",
        f"生成时间：{datetime.now():%Y-%m-%d %H:%M}",
        "",
    ]
    missing = []

    def note_missing(what):
        missing.append(what)
        print("[缺失] " + what)

    # ------------------------------------------------ 6 张参数影响图 --------

    for tag, fixed_note, title_prefix, variants in FIGURE_SPECS:
        fig_stress, ax_stress = plt.subplots(figsize=(10, 6))
        fig_qs, ax_qs = plt.subplots(figsize=(10, 6))
        ann_stress, ann_qs, qs_curves = [], [], []

        for variant_key, style, style_label, mesh, t, ms in variants:
            for case in SURFACES:
                cdir = case_dir(mesh, t, ms, case)
                label = f"{CONFIG_NAMES[case]}，{style_label}"
                if not (cdir / "results" / "stress_strain.csv").is_file():
                    note_missing(f"{tag}: 缺少 stress_strain.csv -> {cdir}")
                    continue
                x, y = stress_curve(cdir)
                minutes = elapsed_minutes(cdir)
                time_text = f"{minutes:.2f} min" if minutes is not None else "耗时未知"
                if minutes is None:
                    note_missing(f"{tag}: status.json 无可靠耗时 -> {cdir}")
                ax_stress.plot(x, y, linestyle=("-" if style == "实线" else "--"),
                               color=COLORS[case], lw=1.8, label=label)
                ann_stress.append((x[-1], y[-1], time_text, COLORS[case]))
                manifest_rows.append({
                    "figure_name": f"{tag}_stress_strain", "curve_label": label,
                    "source_case_path": str(cdir), "elapsed_time_min": minutes,
                    "line_style": style, "color_group": CONFIG_NAMES[case]})
                readme_lines.append(f"{tag}: {label}（{style}） <- {cdir}  [{time_text}]")

                qs = quasi_static_curve(cdir)
                if qs is None:
                    note_missing(f"{tag}: 缺少/无法解析 history.csv -> {cdir}")
                    continue
                qs_curves.append((qs, style, COLORS[case], label, cdir, minutes))

        ax_stress.set_xlim(-0.005, 0.235)
        ax_stress.set_ylabel("工程应力 (MPa)")
        y_lo, y_hi = ax_stress.get_ylim()
        annotate_times(ax_stress, ann_stress, y_hi - y_lo)
        finish_figure(fig_stress, ax_stress,
                      f"{title_prefix}：工程应力–应变曲线（{fixed_note}）",
                      f"Explicit；理想弹塑性；ε=0.2；固定 {fixed_note}；cpus=8",
                      "upper left")
        save_figure(fig_stress, f"{tag}_stress_strain")

        # KE/IE：y 上限按应变 ≥0.05 区间的 98 分位自适应，避免起始瞬态拉爆坐标轴
        tops = []
        for (strains, ratios), *_ in qs_curves:
            mask = np.isfinite(ratios) & (strains >= 0.05)
            if mask.any():
                tops.append(np.nanpercentile(ratios[mask], 98) * 1.35)
        y_top = max(1.5, min(max(tops, default=1.5), 60.0))
        for (strains, ratios), style, color, label, cdir, minutes in qs_curves:
            ax_qs.plot(strains, ratios, linestyle=("-" if style == "实线" else "--"),
                       color=color, lw=1.8, label=label)
            finite = np.isfinite(ratios)
            if finite.any():
                last = np.where(finite)[0][-1]
                ann_qs.append((strains[last], ratios[last],
                               f"{minutes:.2f} min" if minutes is not None else "耗时未知",
                               color))
            manifest_rows.append({
                "figure_name": f"{tag}_quasi_static", "curve_label": label,
                "source_case_path": str(cdir), "elapsed_time_min": minutes,
                "line_style": style, "color_group": label.split("，")[0]})
            readme_lines.append(f"{tag}(KE/IE): {label}（{style}） <- {cdir}  "
                                f"[{minutes} min]")
        ax_qs.set_xlim(-0.005, 0.235)
        ax_qs.set_ylim(-0.02, y_top)
        ax_qs.axhline(0.01, color="0.45", ls=":", lw=1)
        ax_qs.axhline(0.10, color="0.45", ls="--", lw=1)
        ax_qs.text(0.006, 0.01 + y_top * 0.02, "KE/IE = 0.01（1%）",
                   fontsize=8.5, color="0.35")
        ax_qs.text(0.006, 0.10 + y_top * 0.02, "KE/IE = 0.10（10%）",
                   fontsize=8.5, color="0.35")
        ax_qs.set_ylabel("KE/IE（动能/内能，无量纲）")
        y_lo, y_hi = ax_qs.get_ylim()
        annotate_times(ax_qs, ann_qs, y_hi - y_lo)
        finish_figure(fig_qs, ax_qs,
                      f"{title_prefix}：准静态程度曲线 KE/IE（{fixed_note}）",
                      f"Explicit；理想弹塑性；ε=0.2；固定 {fixed_note}；cpus=8",
                      "center left")
        save_figure(fig_qs, f"{tag}_quasi_static")

    # ------------------------------------------------ Implicit vs Explicit --

    implicit_roots = [DATA_ROOT / "implicit",
                      DATA_ROOT.parents[0] / "exp_ref30_2to5_20260918" / "implicit"]
    implicit_candidates = []
    for root_dir in implicit_roots:
        if not root_dir.is_dir():
            continue
        for path in root_dir.rglob("results/stress_strain.csv"):
            summary_path = path.parent / "summary.json"
            if not summary_path.is_file():
                continue
            summary = json.loads(summary_path.read_text(encoding="utf-8-sig"))
            if summary.get("success") and abs(summary.get("final_strain", 0) - 0.2) < 0.005:
                # path = .../results/stress_strain.csv -> case 目录是 results 的上级
                implicit_candidates.append(path.parent.parent)

    explicit_dir = case_dir("Fine", "T0p02", "MS0", "diverse_05")
    implicit_dir = None
    if implicit_candidates:
        implicit_dir = max(implicit_candidates,
                           key=lambda d: len(np.loadtxt(
                               d / "results" / "stress_strain.csv",
                               delimiter=",", skiprows=1)))
        # 隐式 case 的管道状态在上一级目录（implicit/ref30_05/status.json）
        elapsed_implicit = elapsed_minutes(implicit_dir.parents[1])

    if implicit_dir is None:
        message = "未找到合适的 implicit 数据（diverse_05、20% 压缩、success=true）"
        print("[缺失] " + message)
        readme_lines += ["图 07/08：未找到合适 implicit 数据，未绘制。"]
        note_missing("implicit 对照数据")
    else:
        fig_stress, ax_stress = plt.subplots(figsize=(10, 6))
        x_imp, y_imp = stress_curve(implicit_dir)
        x_exp, y_exp = stress_curve(explicit_dir)
        ax_stress.plot(x_imp, y_imp, "-", color="#7f4fc9", lw=2.0, label="构型1，Implicit")
        ax_stress.plot(x_exp, y_exp, "--", color="#1f77b4", lw=2.0, label="构型1，Explicit")
        ax_stress.set_xlim(-0.005, 0.235)
        ax_stress.set_ylabel("工程应力 (MPa)")
        # 恢复提取目录（..._recovered_from_timeout）的 run.log/ODB 在原始 attempt 目录里
        original_attempt = Path(str(implicit_dir).replace("_recovered_from_timeout", ""))
        log_source = original_attempt if (original_attempt / "run.log").is_file()             else implicit_dir
        imp_minutes = implicit_elapsed_minutes(log_source)
        exp_minutes = elapsed_minutes(explicit_dir)
        annotate_times(ax_stress, [
            (x_imp[-1], y_imp[-1],
             f"{imp_minutes:.2f} min" if imp_minutes else "耗时未知", "#7f4fc9"),
            (x_exp[-1], y_exp[-1],
             f"{exp_minutes:.2f} min" if exp_minutes else "耗时未知", "#1f77b4"),
        ], ax_stress.get_ylim()[1] - ax_stress.get_ylim()[0])
        finish_figure(fig_stress, ax_stress,
                      "Implicit 与 Explicit 对比：构型1 工程应力–应变曲线",
                      "Implicit：Standard T=1.0s（含硬化塑性表）；Explicit：Fine T=0.02s MS0"
                      "（理想弹塑性）——两者材料表不同，详见 readme", "upper left")
        save_figure(fig_stress, "07_implicit_vs_explicit_stress_strain")

        fig_qs, ax_qs = plt.subplots(figsize=(10, 6))
        qs_imp = quasi_static_curve(implicit_dir)
        qs_exp = quasi_static_curve(explicit_dir)
        if qs_imp is not None:
            ax_qs.plot(qs_imp[0], qs_imp[1], "-", color="#7f4fc9", lw=2.0,
                       label="构型1，Implicit")
        if qs_exp is not None:
            ax_qs.plot(qs_exp[0], qs_exp[1], "--", color="#1f77b4", lw=2.0,
                       label="构型1，Explicit")
        ax_qs.set_xlim(-0.005, 0.235)
        ax_qs.set_ylim(-0.02, 1.6)
        ax_qs.axhline(0.01, color="0.45", ls=":", lw=1)
        ax_qs.axhline(0.10, color="0.45", ls="--", lw=1)
        ax_qs.text(0.006, 0.03, "KE/IE = 0.01（1%）", fontsize=8.5, color="0.35")
        ax_qs.text(0.006, 0.115, "KE/IE = 0.10（10%）", fontsize=8.5, color="0.35")
        ax_qs.set_ylabel("KE/IE（动能/内能，无量纲）")
        ann_imp_qs = ann_exp_qs = None
        if qs_imp is not None:
            finite = np.isfinite(qs_imp[1])
            last = np.where(finite)[0][-1]
            ann_imp_qs = (qs_imp[0][last], qs_imp[1][last],
                          f"{imp_minutes:.2f} min" if imp_minutes else "耗时未知", "#7f4fc9")
        if qs_exp is not None:
            finite = np.isfinite(qs_exp[1])
            last = np.where(finite)[0][-1]
            ann_exp_qs = (qs_exp[0][last], qs_exp[1][last],
                          f"{exp_minutes:.2f} min" if exp_minutes else "耗时未知", "#1f77b4")
        annotate_times(ax_qs, [item for item in (ann_imp_qs, ann_exp_qs) if item], 1.62)
        finish_figure(fig_qs, ax_qs,
                      "Implicit 与 Explicit 对比：构型1 准静态程度曲线 KE/IE",
                      "Implicit：Standard T=1.0s（含硬化塑性表）；Explicit：Fine T=0.02s MS0"
                      "（理想弹塑性）——两者材料表不同，详见 readme", "center left")
        save_figure(fig_qs, "08_implicit_vs_explicit_quasi_static")

        readme_lines.append(
            f"图 07/08 implicit 数据源：{implicit_dir}"
            "（diverse_05/ref30_05，Standard T=1.0s，20% 压缩；注意其材料为含硬化"
            "塑性表，与显式组的理想弹塑性不同；该隐式 case 管道状态为 SOLVE_TIMEOUT"
            " 后由 orphan 分析完成并从 ODB 恢复提取，其标注时长 = run.log solve 起点"
            " 到 ODB 最终写入的真实 solve 墙钟，不含 mesh/datacheck 约 2.2 min）")
        for label, style, cdir, minutes in (
                ("构型1，Implicit", "实线", implicit_dir, imp_minutes),
                ("构型1，Explicit", "虚线", explicit_dir, exp_minutes)):
            readme_lines.append(f"07/08: {label}（{style}） <- {cdir}  [{minutes} min]")
            manifest_rows.append({
                "figure_name": "07_08_implicit_vs_explicit", "curve_label": label,
                "source_case_path": str(cdir), "elapsed_time_min": minutes,
                "line_style": style, "color_group": "构型1"})
        print("生成 07_implicit_vs_explicit_stress_strain / 08_implicit_vs_explicit_quasi_static")

    # ------------------------------------------------ 汇总输出 --------------

    manifest_path = OUT_DIR / "figure_manifest.csv"
    with manifest_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[
            "figure_name", "curve_label", "source_case_path",
            "elapsed_time_min", "line_style", "color_group"])
        writer.writeheader()
        writer.writerows(manifest_rows)

    if missing:
        readme_lines += ["", "缺失项："] + ["  - " + item for item in missing]
    (OUT_DIR / "readme.txt").write_text("\n".join(readme_lines) + "\n", encoding="utf-8")

    print()
    print("=" * 70)
    print(f"输出目录：{OUT_DIR}")
    print(f"图数量：{len(list(OUT_DIR.glob('*.png')))} PNG / "
          f"{len(list(OUT_DIR.glob('*.svg')))} SVG")
    print(f"manifest：{manifest_path}")
    print(f"implicit 数据：{'已找到 ' + str(implicit_dir) if implicit_dir else '未找到'}")
    if missing:
        print("缺失项：")
        for item in missing:
            print("  - " + item)
    else:
        print("无缺失。")
    print("=" * 70)


if __name__ == "__main__":
    main()
