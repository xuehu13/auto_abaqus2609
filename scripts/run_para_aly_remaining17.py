"""重跑 para_aly 剩余 17 个 case（7 个 DONE 自动跳过）。

6 个 batch 全部使用原 cases_3.jsonl 与昨晚留在 batch 目录里的配置快照，
调用现有 pipeline.batch.run_batch()；DONE 的 case 由 batch 自动跳过：
  - Fine/T0p01/MS0、Fine/T0p02/MS0 的 6 个 DONE 不属于这 6 个 batch；
  - Coarse/T0p02/MS9/diverse_04（smoke）会被该 batch 自动 skip，
    且仍出现在该 batch 的 batch_summary.csv 中。

    pixi run python scripts/run_para_aly_remaining17.py --dry-run   # 只打印
    pixi run python scripts/run_para_aly_remaining17.py             # 正式运行
"""
from __future__ import annotations

import argparse
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

from pipeline.batch import run_batch                       # noqa: E402

OUTPUT_ROOT = REPO_ROOT / "work" / "para_aly"
CASES_FILE = OUTPUT_ROOT / "_control" / "cases_3.jsonl"
SURFACES = ("diverse_05", "diverse_04", "diverse_28")

#: 必须保持 DONE、绝不重算的 7 个 case。
KEEP_DONE = tuple(
    [f"Fine/{t}/MS0/{case}" for t in ("T0p01", "T0p02") for case in SURFACES]
    + ["Coarse/T0p02/MS9/diverse_04"]
)

#: 今晚的 6 个 batch（顺序：先 Fine/MS9 验证修复，再 Coarse）。
RUN_ORDER = (
    ("Fine", "T0p02", "MS9"),
    ("Fine", "T0p01", "MS9"),
    ("Coarse", "T0p02", "MS0"),
    ("Coarse", "T0p01", "MS0"),
    ("Coarse", "T0p02", "MS9"),
    ("Coarse", "T0p01", "MS9"),
)

#: 每个 batch 快照必须吻合的科学参数（昨晚实验的原始设计）。
EXPECTED = {
    ("Fine", "T0p02", "MS9"): dict(b=0.18, edge=0.18, facet=0.15, T=0.02, ms=(True, 9.0)),
    ("Fine", "T0p01", "MS9"): dict(b=0.18, edge=0.18, facet=0.15, T=0.01, ms=(True, 9.0)),
    ("Coarse", "T0p02", "MS0"): dict(b=0.25, edge=0.25, facet=0.25, T=0.02, ms=(False, 1.0)),
    ("Coarse", "T0p01", "MS0"): dict(b=0.25, edge=0.25, facet=0.25, T=0.01, ms=(False, 1.0)),
    ("Coarse", "T0p02", "MS9"): dict(b=0.25, edge=0.25, facet=0.25, T=0.02, ms=(True, 9.0)),
    ("Coarse", "T0p01", "MS9"): dict(b=0.25, edge=0.25, facet=0.25, T=0.01, ms=(True, 9.0)),
}


def read_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def batch_dir(mesh: str, t: str, ms: str) -> Path:
    return OUTPUT_ROOT / mesh / t / ms


def case_status(rel: str):
    path = OUTPUT_ROOT / rel / "status.json"
    if not path.is_file():
        return None
    return read_json(path).get("status")


def preflight() -> None:
    if not CASES_FILE.is_file():
        raise RuntimeError(f"缺少 cases 文件：{CASES_FILE}")
    case_ids = [json.loads(line)["case_id"]
                for line in CASES_FILE.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()]
    if sorted(case_ids) != sorted(SURFACES):
        raise RuntimeError(f"{CASES_FILE} 的 case_id 应为 {SURFACES}，实际 {case_ids}")

    print("== 必须保持 DONE 的 7 个 case ==")
    for rel in KEEP_DONE:
        status = case_status(rel)
        if status != "DONE":
            raise RuntimeError(f"该 case 应为 DONE，实际 {status}：{rel}")
        print(f"  KEEP  {rel}  (DONE)")

    print("== 6 个 batch 配置快照核对 ==")
    for mesh, t, ms in RUN_ORDER:
        bdir = batch_dir(mesh, t, ms)
        for name in ("case_defaults.json", "simulation.json", "runtime.json"):
            if not (bdir / name).is_file():
                raise RuntimeError(f"配置快照缺失：{bdir / name}")
        sim = read_json(bdir / "simulation.json")
        defaults = read_json(bdir / "case_defaults.json")
        runtime = read_json(bdir / "runtime.json")
        want = EXPECTED[(mesh, t, ms)]
        exp = sim["solver"]["explicit_dynamic"]
        checks = {
            "solver=explicit": sim["solver"]["type"] == "explicit_dynamic",
            f"boundary={want['b']}": defaults["mesh"]["boundary_target_spacing_mm"] == want["b"],
            f"edge={want['edge']}": defaults["mesh"]["cgal"]["edge_size_mm"] == want["edge"],
            f"facet={want['facet']}": defaults["mesh"]["cgal"]["facet_size_mm"] == want["facet"],
            f"T={want['T']}": exp["time_period_s"] == want["T"],
            "history=T/100": abs(exp["history_time_interval_s"] - want["T"] / 100) < 1e-15,
            f"mass={want['ms']}": (
                exp["mass_scaling"]["enabled"],
                exp["mass_scaling"].get("factor"),
            ) == want["ms"],
            "ideal_plastic": sim["material"]["plastic_table"] == [[8.0, 0.0]],
            "E=484": sim["material"]["youngs_modulus_MPa"] == 484.0,
            "nu=0.4": sim["material"]["poisson_ratio"] == 0.4,
            "rho=1.1e-9": sim["material"]["density_tonne_mm3"] == 1.1e-9,
            "strain=0.2": sim["loading"]["target_compression_strain"] == 0.2,
            "amplitude=smooth_step": sim["loading"]["amplitude"] == "smooth_step",
            "shell=S3R/5/rd0.1": (
                sim["shell"]["element_type"], sim["shell"]["integration_points"],
                sim["shell"]["thickness_mode"],
                sim["shell"]["target_relative_density"]) == ("S3R", 5, "relative_density", 0.1),
            "friction=0.6/self_contact": (
                sim["contact"]["friction"], sim["contact"]["self_contact"]) == (0.6, True),
            "solve_cpus=8": runtime["solve"]["cpus"] == 8,
            "launcher": bool(runtime["abaqus"]["launcher"]),
        }
        bad = [name for name, ok in checks.items() if not ok]
        if bad:
            raise RuntimeError(f"{mesh}/{t}/{ms} 配置快照与实验设计不符：{bad}")
        print(f"  OK    {mesh}/{t}/{ms}: 全部 {len(checks)} 项参数与设计一致")


def print_plan() -> None:
    """按当前 status 静态列出：将计算的 17 个、将跳过的 7 个 DONE。"""
    run_list, skip_list = [], []
    print("== 本批将计算的 17 个 case ==")
    for mesh, t, ms in RUN_ORDER:
        for case in SURFACES:
            rel = f"{mesh}/{t}/{ms}/{case}"
            if case_status(rel) == "DONE":
                skip_list.append(rel)
            else:
                run_list.append(rel)
                print(f"  RUN   {rel}")
    print("== 将跳过的 7 个 DONE case ==")
    for rel in KEEP_DONE:
        print(f"  SKIP  {rel}  ({'不在本批 6 个 batch 内' if rel.startswith('Fine/') else 'batch 内自动 skip_done'})")
    if len(run_list) != 17 or len(skip_list) != 1:
        raise RuntimeError(f"运行/跳过数量与预期不符：run={len(run_list)} "
                           f"batch 内 skip={len(skip_list)}（应为 17/1，"
                           "另有 6 个 Fine/MS0 DONE 在 batch 之外，preflight 已核对）")
    smoke_runs = [rel for rel in run_list if rel == "Coarse/T0p02/MS9/diverse_04"]
    if smoke_runs:
        raise RuntimeError("Coarse/T0p02/MS9/diverse_04 已 DONE，绝不应再次运行")
    print(f"核对通过：将计算 {len(run_list)} 个，跳过 {len(skip_list)} 个 DONE。")


def run_remaining() -> None:
    for index, (mesh, t, ms) in enumerate(RUN_ORDER, 1):
        bdir = batch_dir(mesh, t, ms)
        print()
        print(f"[{index}/6] {mesh} | {t} | {ms}")
        print(f"batch 目录：{bdir}")
        started = time.monotonic()
        result = run_batch(
            cases_path=CASES_FILE,
            simulation_path=bdir / "simulation.json",
            defaults_path=bdir / "case_defaults.json",
            runtime_path=bdir / "runtime.json",
            work_root=bdir,
            workers=1,
            retry_failed=False,
            max_retries=0,
            force=False,
            log=print,
        )
        wall = time.monotonic() - started
        print(f"[{index}/6] {mesh}/{t}/{ms} 完成：DONE={result.get('DONE')} "
              f"FAILED={result.get('FAILED')} REMAINING={result.get('REMAINING')} "
              f"wall={wall / 60:.1f} min")
    print()
    print("剩余 17 个 case 全部处理完毕。结果仍在 work/para_aly/<mesh>/<T>/<MS>/<case_id>/。")


def main() -> None:
    parser = argparse.ArgumentParser(description="重跑 para_aly 剩余 17 个 case")
    parser.add_argument("--dry-run", action="store_true",
                        help="只打印运行/跳过计划，不启动 Abaqus")
    args = parser.parse_args()

    print("preflight 核对 ...")
    preflight()
    print()
    print_plan()

    if args.dry_run:
        print()
        print("dry-run 结束：未启动 Abaqus。")
        return

    print()
    run_remaining()


if __name__ == "__main__":
    main()
