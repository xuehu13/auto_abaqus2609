"""para_aly 单 case 试跑：diverse_04 / Coarse / T=0.02s / MS9（完整六 stage）。

用途：在重跑剩余 17 个 case 之前，先用一个最困难的代表 case 验证修复后的
mesh Stage 03/04（0.25mm）与 *Fixed Mass Scaling keyword 位置（MS9）能否完整走通
mesh → mesh_datacheck → build → datacheck → solve → extract。

配置直接使用昨晚留在 batch 目录里的快照（不从 production.json 重新生成）：
    work/para_aly/Coarse/T0p02/MS9/{case_defaults,simulation,runtime}.json
cases 只含 diverse_04 一行，表达式原样取自 _control/cases_3.jsonl。

    pixi run python scripts/run_para_aly_smoke_one.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
candidate = SCRIPT_PATH.parents[1]
if (candidate / "run.py").is_file() and (candidate / "pipeline").is_dir():
    REPO_ROOT = candidate
elif (Path.cwd() / "run.py").is_file() and (Path.cwd() / "pipeline").is_dir():
    REPO_ROOT = Path.cwd().resolve()
else:
    raise RuntimeError("找不到 auto_abaqus 仓库根目录。请从仓库根目录运行本脚本。")

sys.path.insert(0, str(REPO_ROOT))

from pipeline.batch import run_batch                     # noqa: E402
from pipeline.common import read_json                    # noqa: E402

SURFACE = "diverse_04"
OUTPUT_ROOT = REPO_ROOT / "work" / "para_aly"
BATCH_DIR = OUTPUT_ROOT / "Coarse" / "T0p02" / "MS9"
CASES_FILE = OUTPUT_ROOT / "_control" / "cases_3.jsonl"
SMOKE_CASES = OUTPUT_ROOT / "_control" / "smoke_diverse_04.jsonl"


def fail(message: str):
    raise RuntimeError("试跑前核对失败：" + message)


def prepare_smoke_cases_file() -> None:
    """从 cases_3.jsonl 原样取出 diverse_04 那一行，写成单行 cases 文件。"""
    matched = [line for line in CASES_FILE.read_text(encoding="utf-8-sig").splitlines()
               if line.strip() and json.loads(line)["case_id"] == SURFACE]
    if len(matched) != 1:
        fail(f"{CASES_FILE} 中 {SURFACE} 应恰好出现 1 次，实际 {len(matched)} 次")
    expression = json.loads(matched[0])["surface_expression"]
    if not expression.strip():
        fail("diverse_04 的 surface_expression 为空")
    SMOKE_CASES.parent.mkdir(parents=True, exist_ok=True)
    SMOKE_CASES.write_text(matched[0] + "\n", encoding="utf-8", newline="\n")
    print(f"smoke cases 文件：{SMOKE_CASES}")
    print(f"  表面方程（原样复制）：{expression}")


def check_config() -> None:
    """逐项核对 batch 快照，确认与本次实验设计完全一致（不一致直接停止）。"""
    if not CASES_FILE.is_file():
        fail(f"缺少 {CASES_FILE}")
    for name in ("case_defaults.json", "simulation.json", "runtime.json"):
        if not (BATCH_DIR / name).is_file():
            fail(f"缺少配置快照：{BATCH_DIR / name}")

    sim = read_json(BATCH_DIR / "simulation.json")
    defaults = read_json(BATCH_DIR / "case_defaults.json")
    runtime = read_json(BATCH_DIR / "runtime.json")
    exp = sim["solver"]["explicit_dynamic"]
    mesh = defaults["mesh"]
    checks = {
        "solver=explicit_dynamic": sim["solver"]["type"] == "explicit_dynamic",
        "boundary=0.25": mesh["boundary_target_spacing_mm"] == 0.25,
        "edge=0.25": mesh["cgal"]["edge_size_mm"] == 0.25,
        "facet=0.25": mesh["cgal"]["facet_size_mm"] == 0.25,
        "T=0.02": exp["time_period_s"] == 0.02,
        "history=0.0002": abs(exp["history_time_interval_s"] - 0.0002) < 1e-15,
        "mass_scaling=on/factor9": (exp["mass_scaling"]["enabled"] is True
                                    and exp["mass_scaling"].get("factor") == 9.0),
        "E=484": sim["material"]["youngs_modulus_MPa"] == 484.0,
        "nu=0.4": sim["material"]["poisson_ratio"] == 0.4,
        "rho=1.1e-9": sim["material"]["density_tonne_mm3"] == 1.1e-9,
        "ideal_plastic": sim["material"]["plastic_table"] == [[8.0, 0.0]],
        "strain=0.2": sim["loading"]["target_compression_strain"] == 0.2,
        "amplitude=smooth_step": sim["loading"]["amplitude"] == "smooth_step",
        "shell=S3R/5/rd0.1": (
            sim["shell"]["element_type"], sim["shell"]["integration_points"],
            sim["shell"]["thickness_mode"],
            sim["shell"]["target_relative_density"]) == ("S3R", 5, "relative_density", 0.1),
        "friction=0.6": sim["contact"]["friction"] == 0.6,
        "self_contact=true": sim["contact"]["self_contact"] is True,
        "datacheck_cpus=8": runtime["datacheck"]["cpus"] == 8,
        "solve_cpus=8": runtime["solve"]["cpus"] == 8,
        "L=10/iso=0": (defaults["unit_cell_size_mm"] == 10.0
                       and defaults["iso_level"] == 0.0),
    }
    bad = [name for name, ok in checks.items() if not ok]
    if bad:
        fail("配置快照与实验设计不符：" + repr(bad))
    print(f"配置快照核对：全部 {len(checks)} 项与实验设计一致")


def main() -> None:
    print("== para_aly 单 case 试跑：diverse_04 / Coarse / T=0.02s / MS9 ==")
    prepare_smoke_cases_file()
    check_config()

    print()
    print("开始完整六 stage：mesh → mesh_datacheck → build → datacheck → solve → extract")
    started = time.monotonic()
    result = run_batch(
        cases_path=SMOKE_CASES,
        simulation_path=BATCH_DIR / "simulation.json",
        defaults_path=BATCH_DIR / "case_defaults.json",
        runtime_path=BATCH_DIR / "runtime.json",
        work_root=BATCH_DIR,
        workers=1,
        retry_failed=False,
        max_retries=0,
        force=False,
        log=print,
    )
    wall = time.monotonic() - started

    print()
    print("=" * 78)
    print(f"试跑结束：DONE={result.get('DONE')} FAILED={result.get('FAILED')} "
          f"REMAINING={result.get('REMAINING')} wall={wall / 60:.1f} min")
    summary_path = BATCH_DIR / SURFACE / "results" / "summary.json"
    status_path = BATCH_DIR / SURFACE / "status.json"
    if summary_path.is_file():
        summary = read_json(summary_path)
        print(f"  final_strain  = {summary['final_strain']}")
        print(f"  max_stress    = {summary['max_stress_MPa']} MPa")
        print(f"  max_ke_ie     = {summary['max_ke_ie_ratio']}")
        print(f"  points        = {summary['points']}")
        print(f"  solve_wall_s  = "
              f"{read_json(status_path)['stages'].get('solve', {}).get('seconds')} s")
    print(f"  status.json   = {status_path}")
    print(f"  results       = {BATCH_DIR / SURFACE / 'results'}")
    print("=" * 78)


if __name__ == "__main__":
    main()
