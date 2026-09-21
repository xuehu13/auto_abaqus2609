"""硬化材料下的 Implicit vs Explicit 求解器对照：diverse_05 两个算例。

目的：在完全相同的物理模型（diverse_05 曲面、0.18mm 细网格、含硬化塑性表、
20% 压缩、friction 0.6、self_contact true）下，对比两种求解器：

  implicit：Abaqus/Standard *Dynamic, application=MODERATE DISSIPATION, T=1.0s
            —— 历史已验证设置（同曲面同网格曾以该设置完整跑完 20%，约 25.7 min），
               求解器块与硬化材料表取自该历史成功快照，不凭记忆重填。
  explicit：Abaqus/Explicit T=0.02s，无质量缩放
            —— 与 para_aly Explicit 基线同参数，仅塑性表换成同一套硬化表。

    pixi run -- python -B scripts/run_hardening_compare.py --check-only  # 不启动 Abaqus
    pixi run -- python -B scripts/run_hardening_compare.py               # 顺序跑两个算例
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
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

from pipeline.run_case import run_case   # noqa: E402

OUTPUT_ROOT = (REPO_ROOT / "work"
               / f"hardening_compare_{datetime.now():%Y%m%dT%H%M%S%f}")
CASES_REFERENCE = REPO_ROOT / "work" / "para_aly" / "_control" / "cases_3.jsonl"
HISTORICAL_SIM = (REPO_ROOT / "work" / "exp_ref30_2to5_20260918" / "implicit"
                  / "ref30_05" / "simulation_used.json")
BASELINE_CASE_USED = (REPO_ROOT / "work" / "para_aly" / "Fine" / "T0p02" / "MS0"
                      / "diverse_05" / "case_used.json")
BASELINE_SIM = (REPO_ROOT / "work" / "para_aly" / "Fine" / "T0p02" / "MS0"
                / "diverse_05" / "simulation_used.json")
BASELINE_RUNTIME = (REPO_ROOT / "work" / "para_aly" / "Fine" / "T0p02" / "MS0"
                    / "runtime.json")

SURFACE = "diverse_05"
CASES_FILE = OUTPUT_ROOT / "case_diverse_05.json"
RUNTIME_PATH = OUTPUT_ROOT / "runtime_hardening.json"

#: 两个算例：（batch 子目录名，simulation 配置文件名，说明）
BATCHES = (
    ("implicit", "simulation_implicit.json", "Standard *Dynamic moderate dissipation, T=1.0s"),
    ("explicit", "simulation_explicit.json", "Explicit, T=0.02s"),
)


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, document: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, ensure_ascii=False,
                               allow_nan=False) + "\n", encoding="utf-8")


def prepare() -> dict:
    """生成两份 simulation 配置、cases 文件与 runtime；全部来自已核对的来源。"""
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=False)
    historical = read_json(HISTORICAL_SIM)
    if (historical["solver"]["type"] != "standard_dynamic_implicit"
            or historical["solver"]["standard_dynamic_implicit"].get("application")
            != "moderate_dissipation"):
        raise RuntimeError("历史快照 Standard 设置与预期不符，请人工核对。")
    hardening_table = historical["material"]["plastic_table"]

    # cases：复用 Explicit 基准的 case_used.json（完整已合并 case 配置），
    # surface_expression 与 cases_3.jsonl 中 diverse_05 逐字交叉核对。
    case_used = read_json(BASELINE_CASE_USED)
    reference = None
    for line in CASES_REFERENCE.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line)
            if row["case_id"] == SURFACE:
                reference = row["surface_expression"]
    if reference is None:
        raise RuntimeError(f"{CASES_REFERENCE} 中找不到 {SURFACE}")
    if case_used.get("surface_expression") != reference:
        raise RuntimeError("基准 case_used 的曲面方程与参考表不一致，请人工核对。")
    write_json(CASES_FILE, case_used)

    # implicit：历史已验证配置原样使用（硬化材料 + Standard 求解器块均来自该成功算例）
    implicit_sim = json.loads(json.dumps(historical))
    # explicit：para_aly 显式基线，仅塑性表换成同一套硬化表（其余原样）
    explicit_sim = json.loads(json.dumps(read_json(BASELINE_SIM)))
    explicit_sim["material"]["plastic_table"] = hardening_table

    # runtime：cpus=8 + all（历史隐式成功组合），solve 上限 4h，保留 ODB；
    # launcher / cgal 路径沿用本机基准 runtime（已配置）。
    base_runtime = read_json(BASELINE_RUNTIME)
    runtime = {
        "abaqus": dict(base_runtime.get("abaqus") or {}),
        "cgal": dict(base_runtime.get("cgal") or {}),
        "results": {"keep_odb": True, "curve_qa_policy": None},
        "datacheck": {"cpus": 8, "standard_parallel": "all", "mp_mode": None,
                      "timeout_s": 600},
        "solve": {"cpus": 8, "standard_parallel": "all", "mp_mode": None,
                  "timeout_s": 14400},
    }
    if not runtime["abaqus"].get("launcher"):
        raise RuntimeError("基准 runtime 中没有 launcher，无法定位 Abaqus。")

    write_json(OUTPUT_ROOT / "simulation_implicit.json", implicit_sim)
    write_json(OUTPUT_ROOT / "simulation_explicit.json", explicit_sim)
    write_json(CASES_FILE, case_used)
    write_json(RUNTIME_PATH, runtime)

    print("配置核对通过：")
    print(f"  工作目录：{OUTPUT_ROOT}")
    print(f"  implicit：{implicit_sim['solver']['standard_dynamic_implicit']['application']} "
          f"T={implicit_sim['solver']['standard_dynamic_implicit']['time_period_s']}s | "
          f"塑性表 {len(implicit_sim['material']['plastic_table'])} 行")
    print(f"  explicit：T={explicit_sim['solver']['explicit_dynamic']['time_period_s']}s | "
          f"塑性表 {len(explicit_sim['material']['plastic_table'])} 行（同一套硬化表）")
    print(f"  runtime：cpus=8/all，solve 上限 14400s，保留 ODB")
    return {"implicit_sim": implicit_sim, "explicit_sim": explicit_sim,
            "runtime": runtime, "case_used": case_used}


def run_one(name: str, simulation_name: str, index: int, total: int,
            runtime_path: Path):
    print()
    print("#" * 78)
    print(f"[{index}/{total}] {name}")
    print(f"simulation：{simulation_name}")
    print(f"结果：{OUTPUT_ROOT / name / SURFACE}")
    print("#" * 78)

    started = time.monotonic()
    run_case(
        case_path=str(CASES_FILE),
        simulation_path=str(OUTPUT_ROOT / simulation_name),
        work_root=str(OUTPUT_ROOT / name),
        runtime_path=str(runtime_path),
        log=print,
    )
    elapsed = time.monotonic() - started
    status = read_json(OUTPUT_ROOT / name / SURFACE / "status.json")
    summary = read_json(OUTPUT_ROOT / name / SURFACE / "results" / "summary.json")
    print(f"[{index}/{total}] {name} 完成：status={status.get('status')} "
          f"wall={elapsed / 60:.1f} min | final_strain={summary['final_strain']:.5f} "
          f"max_stress={summary['max_stress_MPa']:.4f} MPa "
          f"KE/IE={summary['max_ke_ie_ratio']}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="diverse_05 硬化材料 Implicit/Explicit 求解器对照")
    parser.add_argument("--check-only", action="store_true",
                        help="只生成并核对配置，不启动 Abaqus")
    args = parser.parse_args()

    prepared = prepare()
    if args.check_only:
        print()
        print("check-only 结束：配置已生成并核对，未启动 Abaqus。")
        return

    started = time.monotonic()
    for index, (name, simulation_name, _) in enumerate(BATCHES, 1):
        run_one(name, simulation_name, index, len(BATCHES), RUNTIME_PATH)
    print()
    print(f"两个算例全部完成，总耗时 {(time.monotonic() - started) / 60:.1f} min。")


if __name__ == "__main__":
    main()
