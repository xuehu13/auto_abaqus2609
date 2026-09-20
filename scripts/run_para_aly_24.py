"""
24 组 Abaqus/Explicit 参数敏感性实验
==================================

曲面：
    diverse_05  早峰值 + 强软化
    diverse_04  单调硬化
    diverse_28  多转折 / 振荡

固定：
    Abaqus/Explicit
    理想弹塑性：E=484 MPa, nu=0.4, rho=1.1e-9 tonne/mm^3, yield=8 MPa
    cpus=8
    workers=1
    目标压缩应变=20%
    相对密度=0.1
    S3R, integration_points=5
    friction=0.6, self_contact=true
    smooth_step

变量：
    Fine   : boundary=0.18, edge=0.18, facet=0.15 mm
    Coarse : boundary=0.25, edge=0.25, facet=0.25 mm

    T = 0.01 s / 0.02 s
    history_time_interval = T / 100  -> 两组均约 101 个 history 点

    mass scaling OFF / factor=9

共：
    3 surfaces × 2 mesh × 2 T × 2 mass scaling = 24 cases

输出：
    F:/auto_abaqus/work/para_aly/
        Fine/
            T0p02/
                MS0/
                    diverse_05/
                    diverse_04/
                    diverse_28/
                MS9/
                    ...
            T0p01/
                ...
        Coarse/
            ...

运行：
    在仓库根目录执行：
        pixi run python scripts/run_para_aly_24.py

说明：
    本脚本只负责生成 8 份 experiment 配置并顺序调用项目现有 start_experiment()。
    不复制 mesh/build/solve/extract 逻辑。
"""

from __future__ import annotations

import copy
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path


# -----------------------------------------------------------------------------
# 路径
# -----------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()

# 正常情况：脚本放在 <repo>/scripts/ 下。
candidate = SCRIPT_PATH.parents[1]
if (candidate / "run.py").is_file() and (candidate / "pipeline").is_dir():
    REPO_ROOT = candidate
elif (Path.cwd() / "run.py").is_file() and (Path.cwd() / "pipeline").is_dir():
    REPO_ROOT = Path.cwd().resolve()
else:
    raise RuntimeError(
        "找不到 auto_abaqus 仓库根目录。请把本文件放到仓库 scripts/ 下，"
        "并从仓库根目录运行。"
    )

sys.path.insert(0, str(REPO_ROOT))

from pipeline.common import PipelineError  # noqa: E402
from pipeline.experiment import start_experiment  # noqa: E402


BASE_CONFIG = REPO_ROOT / "config" / "experiments" / "production.json"
LOCAL_RUNTIME = REPO_ROOT / "config" / "runtime.json"

OUTPUT_ROOT = Path(r"F:\auto_abaqus\work\para_aly")
CONTROL_ROOT = OUTPUT_ROOT / "_control"
CONFIG_ROOT = CONTROL_ROOT / "configs"
CASES_FILE = CONTROL_ROOT / "cases_3.jsonl"

# 这两个路径来自仓库里此前已经实际跑过的 Explicit 实验。
# 如果 config/runtime.json 已配置 launcher / cgal.executable，则优先使用 runtime.json。
KNOWN_ABAQUS_LAUNCHER = Path(r"E:\ABAQUS\2026\Commands\abaqus.bat")
KNOWN_CGAL_EXE = Path(
    r"F:\auto_abaqus\work\cgal_build_pixi_20260914_01\build\periodic_surface_mesher.exe"
)


# -----------------------------------------------------------------------------
# 3 个曲面
# -----------------------------------------------------------------------------

SURFACES = [
    {
        "case_id": "diverse_05",
        "surface_expression":
            "0.6*sin(2*Z)-4.6*cos(Y)*sin(Z)+0.8*sin(X)*sin(X)-0.4",
    },
    {
        "case_id": "diverse_04",
        "surface_expression":
            "-2.6*sin(Z)-4.5*sin(X)*cos(Y)-0.1*cos(Z)*cos(Z)+1.8",
    },
    {
        "case_id": "diverse_28",
        "surface_expression":
            "-3.4*cos(X)*cos(Z)+4.6*sin(X)*sin(Y)*sin(Z)+2.0",
    },
]


# -----------------------------------------------------------------------------
# 参数设计
# -----------------------------------------------------------------------------

MESH_LEVELS = {
    "Fine": {
        "boundary_target_spacing_mm": 0.18,
        "edge_size_mm": 0.18,
        "facet_size_mm": 0.15,
    },
    "Coarse": {
        "boundary_target_spacing_mm": 0.25,
        "edge_size_mm": 0.25,
        "facet_size_mm": 0.25,
    },
}

TIME_LEVELS = {
    "T0p01": 0.01,
    "T0p02": 0.02,
}

MASS_LEVELS = {
    "MS0": {"enabled": False, "factor": 1.0},
    "MS9": {"enabled": True, "factor": 9.0},
}

# 优先跑最重要的参考组，防止整夜未全部完成时没有高可信基线。
RUN_ORDER = [
    ("Fine",   "T0p02", "MS0"),  # 每个曲面的参考组
    ("Fine",   "T0p01", "MS0"),
    ("Fine",   "T0p02", "MS9"),
    ("Fine",   "T0p01", "MS9"),
    ("Coarse", "T0p02", "MS0"),
    ("Coarse", "T0p01", "MS0"),
    ("Coarse", "T0p02", "MS9"),
    ("Coarse", "T0p01", "MS9"),
]


# -----------------------------------------------------------------------------
# 小工具
# -----------------------------------------------------------------------------

def load_commented_json(path: Path) -> dict:
    """读取项目约定的 production.json：只去掉整行 // 注释。"""
    text = path.read_text(encoding="utf-8-sig")
    clean = "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("//")
    )
    return json.loads(clean)


def read_local_runtime() -> dict:
    if not LOCAL_RUNTIME.is_file():
        return {}
    return json.loads(LOCAL_RUNTIME.read_text(encoding="utf-8-sig"))


def write_json(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def prepare_cases_file() -> None:
    CASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CASES_FILE.open("w", encoding="utf-8", newline="\n") as f:
        for case in SURFACES:
            f.write(json.dumps(case, ensure_ascii=False) + "\n")


def resolve_machine_paths(doc: dict) -> None:
    """
    优先复用本机 config/runtime.json 的机器路径；
    若没有，再尝试仓库历史实验中已经验证过的路径。
    """
    local = read_local_runtime()

    launcher = (
        (local.get("abaqus") or {}).get("launcher")
        or (doc["runtime"].get("abaqus") or {}).get("launcher")
    )
    if not launcher and KNOWN_ABAQUS_LAUNCHER.is_file():
        launcher = str(KNOWN_ABAQUS_LAUNCHER)

    if not launcher:
        raise RuntimeError(
            "没有找到 Abaqus launcher。请先在 config/runtime.json 中设置 "
            'runtime.abaqus.launcher，或修改本脚本的 KNOWN_ABAQUS_LAUNCHER。'
        )

    doc["runtime"]["abaqus"]["launcher"] = str(Path(launcher))

    cgal = (
        (local.get("cgal") or {}).get("executable")
        or (doc["runtime"].get("cgal") or {}).get("executable")
    )
    if not cgal and KNOWN_CGAL_EXE.is_file():
        cgal = str(KNOWN_CGAL_EXE)

    # cgal=null 时项目本身会自动寻找最新本地 build，因此找不到固定路径也不强制失败。
    doc["runtime"]["cgal"]["executable"] = cgal


def make_config(mesh_name: str, time_name: str, mass_name: str) -> tuple[Path, Path]:
    doc = copy.deepcopy(BASE_DOCUMENT)

    mesh = MESH_LEVELS[mesh_name]
    T = TIME_LEVELS[time_name]
    mass = MASS_LEVELS[mass_name]

    # ---- 批次与输出目录 ----
    # 最终目录：
    # F:/auto_abaqus/work/para_aly/<mesh>/<T>/<MS>/<case_id>/
    combo_work_root = OUTPUT_ROOT / mesh_name / time_name
    doc["experiment"]["experiment_id"] = mass_name
    doc["experiment"]["cases_file"] = str(CASES_FILE)
    doc["experiment"]["work_root"] = str(combo_work_root)
    doc["experiment"]["workers"] = 1
    doc["experiment"]["retry_failed"] = False
    doc["experiment"]["max_retries"] = 0
    doc["experiment"]["force"] = False

    # ---- 网格：只同步调整前面确定的三项 ----
    doc["mesh"]["boundary_target_spacing_mm"] = mesh["boundary_target_spacing_mm"]
    doc["mesh"]["cgal"]["edge_size_mm"] = mesh["edge_size_mm"]
    doc["mesh"]["cgal"]["facet_size_mm"] = mesh["facet_size_mm"]

    # 其他网格参数保持 production baseline：
    # topology_sampling_intervals=100
    # facet_angle_deg=25
    # facet_distance_mm=0.03
    # cell_radius_edge_ratio=2.0
    # cell_size_mm=0.50
    # random_seed=20260911

    # ---- 理想弹塑性 ----
    doc["material"]["density_tonne_mm3"] = 1.1e-9
    doc["material"]["youngs_modulus_MPa"] = 484.0
    doc["material"]["poisson_ratio"] = 0.4
    doc["material"]["plastic_table"] = [[8.0, 0.0]]

    # ---- 固定物理模型 ----
    doc["shell"]["element_type"] = "S3R"
    doc["shell"]["integration_points"] = 5
    doc["shell"]["thickness_mode"] = "relative_density"
    doc["shell"]["target_relative_density"] = 0.1
    doc["shell"]["thickness_mm"] = None

    doc["contact"]["normal"] = "hard"
    doc["contact"]["allow_separation"] = True
    doc["contact"]["friction"] = 0.6
    doc["contact"]["self_contact"] = True

    doc["loading"]["target_compression_strain"] = 0.2
    doc["loading"]["amplitude"] = "smooth_step"

    # ---- Explicit ----
    doc["solver"]["type"] = "explicit_dynamic"
    explicit = doc["solver"]["explicit_dynamic"]
    explicit["time_period_s"] = T
    explicit["field_number_interval"] = 10
    explicit["history_time_interval_s"] = T / 100.0  # 约 101 个 history 点
    explicit["field_time_marks"] = False
    explicit["mass_scaling"] = {
        "enabled": mass["enabled"],
        "factor": mass["factor"],
    }

    # ---- 运行资源 ----
    resolve_machine_paths(doc)

    doc["runtime"]["results"]["keep_odb"] = True
    doc["runtime"]["results"]["curve_qa_policy"] = None

    # 用户要求 cpus=8；Data Check 和 Solve 都固定 8。
    doc["runtime"]["datacheck"]["cpus"] = 8
    doc["runtime"]["datacheck"]["standard_parallel"] = "solver"
    doc["runtime"]["datacheck"]["mp_mode"] = None
    doc["runtime"]["datacheck"]["timeout_s"] = 600

    doc["runtime"]["solve"]["cpus"] = 8
    doc["runtime"]["solve"]["standard_parallel"] = "solver"
    doc["runtime"]["solve"]["mp_mode"] = None
    # 夜间无人值守给足墙钟预算；超时后现有 pipeline 会杀完整 Abaqus 进程树。
    doc["runtime"]["solve"]["timeout_s"] = 14400

    config_path = CONFIG_ROOT / f"{mesh_name}_{time_name}_{mass_name}.json"
    write_json(config_path, doc)

    result_dir = combo_work_root / mass_name
    return config_path, result_dir


def write_manifest() -> None:
    manifest = OUTPUT_ROOT / "sweep_manifest.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    order = 0
    for mesh_name, time_name, mass_name in RUN_ORDER:
        mesh = MESH_LEVELS[mesh_name]
        T = TIME_LEVELS[time_name]
        mass = MASS_LEVELS[mass_name]
        for case in SURFACES:
            order += 1
            rows.append({
                "order": order,
                "case_id": case["case_id"],
                "mesh": mesh_name,
                "boundary_mm": mesh["boundary_target_spacing_mm"],
                "edge_mm": mesh["edge_size_mm"],
                "facet_mm": mesh["facet_size_mm"],
                "T_s": T,
                "history_interval_s": T / 100.0,
                "mass_scaling": mass["enabled"],
                "mass_factor": mass["factor"],
                "cpus": 8,
                "output_dir": str(
                    OUTPUT_ROOT / mesh_name / time_name / mass_name / case["case_id"]
                ),
            })

    with manifest.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def append_progress(
    run_index: int,
    mesh_name: str,
    time_name: str,
    mass_name: str,
    elapsed_s: float,
    status: str,
    message: str,
) -> None:
    path = OUTPUT_ROOT / "sweep_progress.csv"
    new_file = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        fields = [
            "timestamp",
            "run_index",
            "mesh",
            "T",
            "mass_scaling",
            "elapsed_s",
            "status",
            "message",
        ]
        writer = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            writer.writeheader()
        writer.writerow({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "run_index": run_index,
            "mesh": mesh_name,
            "T": time_name,
            "mass_scaling": mass_name,
            "elapsed_s": round(elapsed_s, 1),
            "status": status,
            "message": message,
        })


# -----------------------------------------------------------------------------
# 主程序
# -----------------------------------------------------------------------------

if not BASE_CONFIG.is_file():
    raise RuntimeError(f"找不到总配置模板：{BASE_CONFIG}")

BASE_DOCUMENT = load_commented_json(BASE_CONFIG)

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
CONFIG_ROOT.mkdir(parents=True, exist_ok=True)

prepare_cases_file()
write_manifest()

print("=" * 78)
print("Abaqus/Explicit 24 组参数实验")
print(f"仓库：{REPO_ROOT}")
print(f"输出：{OUTPUT_ROOT}")
print("曲面：diverse_05 / diverse_04 / diverse_28")
print("变量：2 mesh × 2 T × 2 mass scaling = 8 组配置，每组 3 个曲面")
print("总计：24 个 case，顺序运行，workers=1，cpus=8")
print("=" * 78)

for index, (mesh_name, time_name, mass_name) in enumerate(RUN_ORDER, 1):
    config_path, result_dir = make_config(mesh_name, time_name, mass_name)

    print()
    print("#" * 78)
    print(f"[{index}/8] {mesh_name} | {time_name} | {mass_name}")
    print(f"配置：{config_path}")
    print(f"结果：{result_dir}")
    print("#" * 78)

    started = time.monotonic()

    try:
        result = start_experiment(config_path, root=REPO_ROOT, log=print)
        elapsed = time.monotonic() - started

        shown = result
        if isinstance(result, dict) and "rows" in result:
            shown = {k: v for k, v in result.items() if k != "rows"}

        print(json.dumps(shown, indent=2, ensure_ascii=False, default=str))

        failed = 0
        if isinstance(result, dict):
            failed = int(result.get("FAILED") or 0)

        status = "DONE" if failed == 0 else "COMPLETED_WITH_FAILURES"
        append_progress(
            index, mesh_name, time_name, mass_name,
            elapsed, status,
            f"failed_cases={failed}",
        )

        # 普通 case 失败/超时不阻止其他参数组继续。
        print(f"[{index}/8] 完成，耗时 {elapsed/60:.1f} min，状态：{status}")

    except KeyboardInterrupt:
        elapsed = time.monotonic() - started
        append_progress(
            index, mesh_name, time_name, mass_name,
            elapsed, "INTERRUPTED", "KeyboardInterrupt",
        )
        print("\n用户中断。已经完成的 case 会保留，之后重新运行本脚本可按现有 pipeline 续跑。")
        raise

    except PipelineError as exc:
        elapsed = time.monotonic() - started
        code = getattr(exc, "code", "PIPELINE_ERROR")
        append_progress(
            index, mesh_name, time_name, mass_name,
            elapsed, "PIPELINE_ERROR", f"{code}: {exc}",
        )
        print(f"\n[{index}/8] PipelineError: {code}: {exc}")

        # 这类错误可能意味着进程树没有被可靠清干净，不能继续启动下一批。
        if code == "ABAQUS_TREE_NOT_TERMINATED":
            print("检测到 Abaqus 进程树未完全终止。为避免叠加作业，停止整个参数扫描。")
            raise

        # 其他配置/基础设施错误通常继续跑也没有意义。
        print("这是 pipeline/config 级错误，不是普通 case 求解失败；停止扫描以免整夜重复报错。")
        raise

    except Exception as exc:
        elapsed = time.monotonic() - started
        append_progress(
            index, mesh_name, time_name, mass_name,
            elapsed, "ERROR", repr(exc),
        )
        print(f"\n[{index}/8] 未预期错误：{exc!r}")
        raise

print()
print("=" * 78)
print("24 组参数实验全部提交完成。")
print(f"结果根目录：{OUTPUT_ROOT}")
print(f"实验设计表：{OUTPUT_ROOT / 'sweep_manifest.csv'}")
print(f"运行进度表：{OUTPUT_ROOT / 'sweep_progress.csv'}")
print("=" * 78)
