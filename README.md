# auto_abaqus

周期性曲面 → 自动网格 → Abaqus 建模 → Data Check → Solve → 结果提取 的科研自用流水线。

**这不是产品**：没有插件体系、兼容层、调度框架或数据库。目标是"改一个 JSON 就能算一个新曲面"，
并且"我自己能看懂、能改参数、能运行、出错能定位"。

一条命令跑完一个 case：

```powershell
pixi run cli run-case --case config/cases/fig1.json --simulation config/simulation.json
```

## 快速开始

```powershell
# 整个单 case：mesh → mesh datacheck → build → datacheck → solve → extract
pixi run cli run-case `
    --case config/cases/fig1.json `
    --simulation config/simulation.json `
    [--work-root work] [--runtime config/runtime.json] [--force]

# 调试用的单 stage 命令（都在 <work-root>/<case_id>/ 里活动）
pixi run cli mesh           --case config/cases/fig1.json
pixi run cli mesh-datacheck --case config/cases/fig1.json
pixi run cli build          --case config/cases/fig1.json --simulation config/simulation.json [--force]
pixi run cli datacheck      --case config/cases/fig1.json
pixi run cli solve          --case config/cases/fig1.json
pixi run cli extract        --case config/cases/fig1.json [--odb <已有 ODB>]
pixi run cli plan

# 批量：一个 JSONL 里每行一个曲面，逐个跑 run_case()
pixi run cli run-batch `
    --cases config/cases.jsonl `
    --case-defaults config/case_defaults.json `
    --simulation config/simulation.json `
    [--work-root work/batch_001] [--workers 1] [--retry-failed] [--max-retries 0] [--force]
pixi run cli summarize-batch --work-root work/batch_001   # 从各 case 目录重建总表
```

- `run-case` 会**续跑**：已成功的 stage 直接跳过；`--force` 重新跑全部。
- `config/simulation.json` 或 case 配置改了，旧结果自动失效（比对 SHA256）：
  case 配置变 → 全部重跑；simulation 变 → build 起重跑（网格保留）。
- 旧结果不会被删除：被替换的 `mesh/ abaqus/ results/` 会改名为 `*.previous_<时间戳>` 保留证据。
- **Abaqus solve 只有你显式调用时才会跑**（`run-case` 也会跑 solve，长时间求解前请自行确认）。

## Standard / Explicit 怎么选

`solver.type` 一个字段切换，两个 block 参数各自独立存在：

```json
"solver": { "type": "standard_dynamic_implicit" }      // Abaqus/Standard Dynamic Implicit
"solver": { "type": "explicit_dynamic" }               // Abaqus/Explicit
```

同一份 `config/simulation.json` 同时保存两个 block，改 `type` 不需要补参数：

```json
"solver": {
  "type": "standard_dynamic_implicit",
  "standard_dynamic_implicit": {
    "time_period_s": 1.0, "nlgeom": true, "application": "moderate_dissipation",
    "initial_acceleration": false, "initial_increment_s": 0.001,
    "minimum_increment_s": 1e-08, "maximum_increment_s": 0.02,
    "maximum_increments": 10000, "slip_tolerance": 0.005,
    "restart_frequency": 0, "field_frequency": 50, "history_frequency": 1,
    "preselect_history_frequency": 10
  },
  "explicit_dynamic": {
    "time_period_s": 1.0, "field_number_interval": 100,
    "history_time_interval_s": 0.001, "field_time_marks": false,
    "mass_scaling": { "enabled": false }
  }
}
```

Standard 与 Explicit 是**不同数值算法**：切求解器不代表结果一致。Explicit 做准静态压缩时
请自己关注 `summary.json` 的 `max_ke_ie_ratio`（动能/内能），程序只报告、不自动修复。

## 批量运行（20,000+ cases）

批量的本质就是一句话：**逐个 case 调用同一个 `run_case()`**。Batch 不重写 mesh/build/solve，
也不认识 solver；它只负责选哪些 case 要跑、并发多少、以及把每个 case 的状态汇总成表。

### 输入：cases.jsonl + case_defaults.json

`config/cases.jsonl` 每行一个 case（`#` 是注释）：

```json
{"case_id": "fig1", "surface_expression": "2.3*cos(X)*sin(Z) + 1.9*cos(Y)*cos(Z) - 0.6"}
{"case_id": "diverse_01", "surface_expression": "-0.3*sin(2*X)+3.9*sin(Y)*sin(Z)+0.6*sin(Y)*sin(Y)-0.2"}
{"case_id": "diverse_02", "surface_expression": "2.9*sin(2*Y)+4.0*sin(Y)*cos(Z)+1.5*sin(X)*sin(X)-0.7"}
```

共享网格参数放 `config/case_defaults.json`（`iso_level`、`unit_cell_size_mm`、`mesh.*`），
所以每行**不需要重复** mesh 配置。合并规则只有一层：defaults + 这一行（嵌套 dict 递归合并）。
个别 case 要特殊设置时，直接写同名字段，或放进 `overrides`：

```json
{"case_id": "case_001234", "surface_expression": "...", "overrides": {"unit_cell_size_mm": 12.0}}
{"case_id": "case_001235", "surface_expression": "...", "mesh": {"boundary_target_spacing_mm": 0.25}}
```

- `case_id` 必须唯一且是安全目录名（字母开头，`A-Za-z0-9_-`）；重复会**直接停止整个 batch**。
- 一个 case 的配置解析失败（表达式非法、mesh 参数非法）只会让这个 case `MESH_STAGE_FAILED`，不影响其他 case。
- `surface_expression` 由 mesh 系统原样解释，batch 不做任何数学处理。

### 工作目录与产出

```
work/batch_001/
├─ fig1/                 ← 每个 case 与单 case 完全一样的结构（mesh/ abaqus/ results/ status.json run.log）
├─ diverse_01/
├─ diverse_02/
├─ batch_summary.csv     一行一个 case 的总表
├─ results_index.jsonl   只有成功 case（给以后的 ML 数据构建脚本用）
├─ failed_cases.jsonl    只有失败 case（方便以后只重跑失败的）
├─ batch_config.json     这次 batch 的输入文件、workers、solver 来源、simulation SHA
└─ batch.log             每个 case 一行事件（含 skip/settle 原因）
```

`batch_summary.csv` 的列：

```
case_id, surface_expression, solver, status, failed_stage, message,
mesh_wall_time_s, mesh_datacheck_wall_time_s, build_wall_time_s,
datacheck_wall_time_s, solve_wall_time_s, extract_wall_time_s, total_wall_time_s,
points, final_strain, max_stress_MPa, max_ke_ie_ratio, result_path
```

不存在的值**留空**（不填 0 冒充结果）；`max_ke_ie_ratio` 对 Explicit 是诊断值，
程序不会因为 KE/IE 高就判失败。`results_index.jsonl` 的每行：

```json
{"case_id": "fig1", "surface_expression": "...", "solver": "explicit_dynamic",
 "stress_strain_csv": "fig1\\results\\stress_strain.csv",
 "history_csv": "fig1\\results\\history.csv", "summary_json": "fig1\\results\\summary.json"}
```

`failed_cases.jsonl` 的每行：`case_id`、`surface_expression`、`stage`、`status`、`message`
（单行、截断到 300 字符）、`status_json`（完整细节在 case 自己的 status.json 里）。

### workers（并发）

```powershell
pixi run cli run-batch ... --workers 2
```

- 默认 `1`。**程序不会自动按 CPU 核数提高 workers**：Abaqus 有 license/内存/IO 限制，
  而每个 solve 自己还会用 `runtime.json` 的 `solve.cpus`。
- 一个 worker 负责**一个 case 的完整流程**（不是按 stage 拆开的流水线）。
- 并发前已确认：每个 case 有独立目录、独立 Abaqus job name（`<case_id>_dc` / `<case_id>_solve`）、
  独立 CGAL 输入/输出路径；共享的 4 个 batch 文件只由主进程写（worker 把结果交回主进程）。
- 启动时会打印 `workers × solve cpus` 的潜在 CPU 用量提示；本机 20 逻辑核，2 个 worker × 4 CPU 没问题。
- 本机未并发实测（本轮真实 batch 用 workers=1）；建议先从 1 开始，确认 license/内存后再加。

### resume：DONE 跳过、FAILED 跳过、RUNNING 恢复

再跑同一个 batch（同一 `--work-root`）时：

| 上次状态 | 这次行为 |
|---|---|
| `DONE`（含结果文件齐全） | skip |
| 各种 `*_FAILED` | skip（除非 `--retry-failed`） |
| `PENDING`（没跑过） | 正常运行 |
| `INTERRUPTED` / 残留 `RUNNING` | 继续跑，从第一个还没有成功证据的 stage 开始 |
| `--force` | 选中的 case 从头重跑（旧目录改名 `*.previous_<时间戳>` 保留） |

**残留 `RUNNING` 的处理**（断电、被关窗口、Ctrl+C、Abaqus 被手动杀）：程序重新启动时，
上一次的 `RUNNING` 不可能还是活跃任务，于是：

- 结果文件（`history.csv` + `stress_strain.csv` + `summary.json` 且 `success=true`）齐全
  → 判为完成，把 `status.json` 改写成 `DONE`（记 `recovered_from: INTERRUPTED`）；
- 结果不齐 → 当作 `INTERRUPTED`，从缺的那一步继续（例如 solve 被杀过就只重跑 solve）。

不检查 PID、不做 heartbeat：单机科研程序没有必要。

配置变化自动失效仍然有效，而且是**按内容**判断的：

- `case_config_sha256`：case 配置（defaults 与这一行合并后的最终配置）的 SHA256；
  改了就整个 case 重跑。写 `case_used.json` 的格式变化不会误判成改动。
- `simulation_config_sha256`：simulation 配置的 SHA256；改了就从 build 起重跑（网格保留）。

每个 case 目录里保存 `case_used.json` 与 `simulation_used.json`（合并后的最终配置），
以后看到某条曲线时可以直接知道当时用了什么参数。

### retry

```powershell
pixi run cli run-batch ... --retry-failed              # 上一轮失败的也重跑
pixi run cli run-batch ... --retry-failed --max-retries 2
```

- `--retry-failed`：只影响"是否把失败 case 纳入本轮"。
- `--max-retries N`（默认 0）：单个 case 失败后再尝试 N 次。
- **重试用的是完全相同的输入**：同一个 case 配置、同一个 simulation，只补跑失败的那个 stage。
  程序绝不为了让 case 跑成功而改摩擦/应变/材料/接触/时间/mass scaling/网格或换求解器。
- 失败就失败，不会无限重试。

### 失败隔离

单个 case 失败（mesh/PBC/Data Check/Solve/Extract）只记录并继续下一个 case。
只有**全局错误**才停止整个 batch：simulation 读不了、`cases.jsonl` 整体非法、case_id 重复、
defaults 本身非法、Abaqus launcher 不可用。`run-batch` 结束时如果有失败 case，退出码为 3
（`failed_cases.jsonl` 里能看到全部）。

### 磁盘

`runtime.json` 的 `results.keep_odb`（默认 `true`）决定是否保留 ODB：

- `true`：全部保留（推荐；原始 ODB 很难复得）。
- `false`：**只在 extract 成功之后**删除 ODB；`.inp/.dat/.msg/.sta` 日志与报告全部保留，
  失败的 case 也**不会**自动删 ODB。

## 参数总表

### 通用（两个求解器都生效）

| 参数 | 作用 |
|---|---|
| `material.density_tonne_mm3` / `youngs_modulus_MPa` / `poisson_ratio` / `plastic_table` | 密度、E、ν、真实应力-塑性应变表 |
| `shell.element_type` / `integration_points` | 壳单元类型（受网格拓扑限制）、厚度方向积分点 |
| `shell.target_relative_density` | 目标相对密度（决定壳厚度 = ρ*·L³/A） |
| `platen.element_type` / `width_factor` / `mesh_size_mm` | 刚板单元、宽度系数（×cell 尺寸）、刚板网格尺寸 |
| `contact.normal` | `*Surface Behavior` 的 pressure-overclosure（hard/soft/…） |
| `contact.allow_separation` | false → 加 `, no separation` |
| `contact.friction` | 摩擦系数 |
| `contact.self_contact` | true：`*Contact Inclusions, ALL EXTERIOR`；false：显式 SHELL/PLATE 面对（关自接触） |
| `loading.target_compression_strain` | 目标压缩工程应变（目标位移 = -ε·L） |
| `loading.amplitude` | `smooth_step`（definition=SMOOTH STEP）或 `ramp`（tabular 线性斜坡） |
| `pbc.include_rotational_dofs` | 周期方程是否含转动自由度 |
| `output.requests` | 要写出的 history 请求：`{"kind":"energy"}` / `{"kind":"node","region":...}` + 变量表 |

### 只有 Standard 有（放在 `solver.standard_dynamic_implicit`）

`time_period_s`、`nlgeom`、`application`、`initial_acceleration`、`initial_increment_s`、
`minimum_increment_s`、`maximum_increment_s`、`maximum_increments`、`slip_tolerance`、
`restart_frequency`、`field_frequency`、`history_frequency`、`preselect_history_frequency`。

`slip_tolerance` 是 Standard 专有数值选项：写在 solver block 里，切到 Explicit 时**不会**
出现在 deck 中（Abaqus/Explicit 会报 `UNKNOWN PARAMETER SLIPTOLERANCE`）。

### 只有 Explicit 有（放在 `solver.explicit_dynamic`）

`time_period_s`、`field_number_interval`（场输出帧数）、`history_time_interval_s`（历史采样时间间隔）、
`field_time_marks`、`mass_scaling.enabled`（+ 可选 `factor`）。

`mass_scaling` **默认关闭**；打开时必须写 `factor`，build report 与 `summary.json` 里都会记录，
程序绝不会为了让 Explicit 跑快而偷偷加质量缩放。

### runtime（机器本地，与科学无关）

| 参数 | 作用 |
|---|---|
| `abaqus.launcher` / `release_required` | launcher 路径、要求的 release（防跑错版本） |
| `cgal.executable` | 编译好的 CGAL mesher；留空则自动找最新的 `work/*/build/periodic_surface_mesher.exe` |
| `<stage>.cpus` | datacheck/solve 的 CPU 数 |
| `<stage>.standard_parallel` | 仅 Standard 传 `standard_parallel=all|solver` |
| `<stage>.mp_mode` | 可选 `threads`/`mpi`，留空不传（本机 Explicit 用 `threads` 可绕开 smpd 报错） |
| `<stage>.timeout_s` | 墙钟上限，超时写 `*_TIMEOUT` 并保留目录 |

命令行可覆盖：`--cpus --timeout-s --job-name --abaqus-command --runtime`。

## 现在不能改的参数（以及真正的原因）

| 想改 | 为什么现在不行 |
|---|---|
| 壳单元用 S4/S4R/S4R5 | 当前网格只有 3 节点三角形；4 节点单元需要四边形网格生成器 |
| 刚板用 R3D3 等 | 刚板是 4 节点四边形网格，只有 R3D4 与之兼容 |
| 修改 11 点论文曲线采样 | 结果只保存**完整**曲线；11 点以后单独从 `stress_strain.csv` 采样 |
| 自动质量缩放优化、ALE、element deletion、damage、adaptive mesh | 本轮显式不做；`mass_scaling` 只支持"用户打开 + 固定 factor" |
| Explicit 的 bulk viscosity、damping 等 | 需要时再往 `solver.explicit_dynamic` 加字段 + 几行 renderer |

单元类型不是"字符串随便换"：`shell.element_type` 只接受与 3 节点三角拓扑兼容的类型
（S3 / S3R / STRI3），`platen.element_type` 只接受 R3D4；填了不兼容的值会在 build 阶段**明确报错**
（不会写出 Abaqus 无法接受的 deck）。

## Standard 与 Explicit deck 的实际差别

同一模型、同一网格，切换求解器只有 3 个 block 不同（其余 7 个文件字节一致，有测试保证）：

| block | Standard | Explicit |
|---|---|---|
| `blocks/step_loading.inc` | `*Step, name=Compression, nlgeom=YES, inc=10000` / `*Dynamic, application=MODERATE DISSIPATION, initial=NO` / `0.001, 1.0, 1e-08, 0.02` | `*Step, name=Compression` / `*Dynamic, Explicit` / `, 1.0`（无 nlgeom、无增量控制） |
| `blocks/contact.inc` | `*Friction, slip tolerance=0.005` | `*Friction`（去掉 Standard 专有参数） |
| `blocks/outputs.inc` | `*Restart` + `frequency=n`（按增量） | 无 `*Restart`；`number interval=`（场帧数）+ `time interval=`（历史时间间隔） |

amplitude、目标位移、材料、厚度、PBC、刚板几何在两者中完全相同。
Explicit 的 `.sta` 表格式与 Standard 不同（1 列增量 + 时间列），解析器按求解器分支处理。
Data Check 的完成判据也不同：Standard 认 `ANALYSIS DATACHECK COMPLETE`，
Explicit 认 `THE ANALYSIS HAS COMPLETED SUCCESSFULLY`（2026 版实测）。

## 单 case 目录（没有 staging）

```
work/<case_id>/
├─ mesh/            engine/（冻结 vendor 阶段 00-06 + CGAL 产物）、mesh_result.json、meshcheck_report.json
├─ abaqus/          physical.inp、ingredients/、blocks/、build_report.json、*.dat/.msg/.sta/.odb
├─ results/         history.csv、stress_strain.csv、summary.json、raw_history.json
├─ status.json      每 stage 状态 + 两个 config SHA256
└─ run.log          带时间戳的阶段日志
```

Data Check 和 Solve **就在 `abaqus/` 里跑**，不再把 deck 复制成新的 attempt：一个 case 一份 deck，
没有 SHA 链和磁盘副本。生成 deck 的 SHA256 仍然记录在报告里，datacheck/solve 前会重算并比对
（deck 被手改过就报 `*_ARTIFACT_MISMATCH`），solve 只接受 `DATACHECK_PASSED` /
`DATACHECK_COMPLETED_WITH_WARNINGS` 的状态。

## 结果文件

| 文件 | 内容 |
|---|---|
| `results/history.csv` | `time_s` + 实际存在的量（`U3_mm`、`RF3_N`、`ALLIE`、`ALLKE`、`ALLAE`、`ALLPD`、`ALLWK`、`ETOTAL`、`ALLVD`）。缺失的变量**不补 0**，在 summary 的 `missing` 里列出 |
| `results/stress_strain.csv` | 完整曲线：`engineering_strain`、`engineering_stress_MPa` |
| `results/summary.json` | case_id、solver、target/final strain、max_stress_MPa、points、wall_time_s、mass_scaling、`max_ke_ie_ratio`、energy_variables、energy_interpolated、missing |
| `results/raw_history.json` | Abaqus Python worker 的原始导出（含 region 名与选中的 key），用于溯源 |

符号约定：**压缩为正**。`engineering_strain = -U3/H0`，`engineering_stress = -RF3/A0`，
其中 `H0` = unit cell 尺寸、`A0 = L²`（都来自 build report 的模型事实，不需要命令行输入）。
该定义与之前的 Fig.1 论文复现脚本一致：用历史 Standard ODB 重新提取的 60 点曲线与旧脚本
逐点完全一致（stress 差值 0）。

ODB 只由 `abaqus python abaqus_worker/export_history.py` 读取（主环境永不 import odbAccess）。

## 配置校验行为

- 未知 key / 缺 key / NaN / 非法数值：直接报错，带上文件名与 key 名。
- 合法但未实现的写法（如 `amplitude=tabular`、`kind=element`）：报 `NOT_IMPLEMENTED`，不会静默忽略。
- 拓扑不兼容的单元类型：`CONFIG_INVALID` 并说明原因。
- 每个 solver 只读自己的 block：Standard 的 `slip_tolerance` 不会进 Explicit deck。

## 代码结构

```
run.py                  CLI：plan / run-case / run-batch / summarize-batch /
                        mesh / mesh-datacheck / build / datacheck / solve / extract
pipeline/
  common.py             错误码、JSON/哈希 IO、配置校验原语、git provenance
  mesh.py               case config → vendor case.json；网格契约；PBC；并负责跑冻结 vendor 阶段与 CGAL
  build.py              simulation.json → blocks/ + physical.inp + build_report.json（两个 solver 的 renderer）
  abaqus.py             runtime/launcher/release gate、datacheck、solve（按 solver 组装命令行与判据）
  extract.py            原始 ODB 历史 → history.csv / stress_strain.csv / summary.json
  run_case.py           单 case 编排：阶段顺序、status.json、续跑、恢复、config 内容 SHA
  batch.py              cases.jsonl + defaults → 逐个调用 run_case()，汇总 batch 表
  curve_qa.py           单条历史 CSV 的曲线 QA（论文 11 点用）
abaqus_worker/
  export_history.py     在 abaqus python 下运行的 ODB 只读导出 worker
scripts/pixi_tasks.py   check / test / mesh-* / build-cgal（低层调试入口）
vendor/periodic_surface_mesher_v1.0/   冻结，不修改
```

数据流：

```
config/cases/<case_id>.json ─→ mesh/ ─→ abaqus/（physical.inp + blocks + ingredients）
                                          │
config/simulation.json ───────────────────┤
                                          ├─ datacheck ─→ 同目录报告 + 日志
                                          ├─ solve ─────→ 同目录 ODB + solve_report.json
                                          └─ extract ───→ results/*.csv + summary.json
```

## 报告与完整性

- `build_report.json`：deck 文件 SHA256、模型事实（L、A0、厚度、目标位移、标签）、
  静态检查（deck_files_present / deck_sha256 / include_graph / region_integrity /
  step_structure）、`solver`（type / time_period_s / mass_scaling）、config SHA、git commit+dirty。
- `datacheck_report.json` / `solve_report.json`：solver、deck SHA256、runtime 与 launcher、
  命令 argv、诊断计数与分类、Abaqus 产出（ODB 大小 + SHA256）、完成判据明细、claims。
- `claims.dataset_eligible` 永远为 `false`：本仓库不产生"科学质量合格"的结论。
  Data Check 通过 ≠ 收敛 ≠ 达到目标应变 ≠ 结果可用于数据集。

## 测试

```powershell
pixi run test        # 147 个 unittest（含 Pixi 边界测试）
pixi run check       # 三个环境自检
pixi run cli-help
```

重点测试：Standard/Explicit deck 的关键字差异、共享 block 字节一致、配置项逐项生效、
Data Check/Solve 判据（含"缺完成标记必须失败"）、run-case 阶段顺序/失败停止/续跑/
RUNNING 恢复/config 内容 SHA、ODB 保留策略、提取的符号与单位、worker 调用形式；
batch 的 JSONL 读取、defaults 合并、重复 case_id、失败隔离、DONE/FAILED skip、
`--retry-failed` 与 `--max-retries`（同输入重试）、workers 并发、汇总三件套内容与重建。
`tests/test_regression.py` 用 tracked config 重建 Fig.1 deck，与
`tests/fixtures/fig1_20pct_regression/deck_sha256.json` 的 10 个 SHA 逐字节比较。

## 真实验证状态（2026-09-17）

已在真实 Abaqus 2026 上验证：

- Fig.1 **Standard deck 10/10 SHA 一致**（`run-case` 目录里重建也一致）。
- Fig.1 mesh data check（`fig1_meshcheck`）+ vendor stage 07 通过。
- Fig.1 Standard **Data Check**：`DATACHECK_COMPLETED_WITH_WARNINGS`，0 error / 10 warning
  （与历史 `fig1_datacheck_m2_final_001` 完全同类）。
- Fig.1 Standard + `self_contact=false` Data Check：0 error / 11 warning（新接触写法被接受）。
- Fig.1 **Explicit**（20% 物理、关自接触）Data Check：0 error，完成标记存在。
- **Explicit smoke solve**：把 `time_period_s` 改成 1e-3 s（`config/examples/simulation_explicit_smoke.json`，
  **不是**正式配置），Abaqus/Explicit 真正跑完并提取出曲线；smoke 结果**不是**准静态，只证明链路通畅。
- 用历史 Standard ODB 重新提取：60 点曲线与旧脚本逐点一致。
- **真实小批量 batch**（4 个 case、workers=1、smoke simulation，`work/r3_smoke/batch_001/`）：

  | case | 结果 | 说明 |
  |---|---|---|
  | fig1 | DONE 177.9 s | 101 点曲线，final_strain 0.2000，max_stress 0.3029 MPa，KE/IE 1.096 |
  | diverse_01 | MESH_STAGE_FAILED (mesh) | 冻结 vendor 阶段 05 判定 PBC 配对非双射（历史同曲面 ref30_01 也是 `STEP 05 STATUS: FAIL`，非本轮引入） |
  | diverse_02 | DONE 261.6 s | 101 点曲线，final_strain 0.19998，max_stress 0.4053 MPa，KE/IE 1.270 |
  | broken_expr | MESH_STAGE_FAILED (mesh) | 故意写错的表达式，快速失败且不影响其他 case |

  同一 batch 复跑：`to run: 0`（2 DONE skip、2 FAILED 默认 skip）；
  `--retry-failed` 只重跑两个失败 case（同输入，仍然失败）；
  `summarize-batch` 从各 case 目录重建总表；把 fig1 的 status.json 强制改成 `RUNNING` 后复跑，
  被正确 settle 成 `DONE`（`recovered_from: INTERRUPTED`）且不重算；
  用 `run-case --case <batch>/fig1/case_used.json` 也能全部 skip（证明 case 身份按内容判断）。

**没有**验证过的（不要当成结论）：Standard 20% 完整 solve、Explicit 20% 完整 solve、
科学质量验收、workers>1 的真实并发（只用 mock 测过并发逻辑）、2 万个 case 的实际规模。

## 真实验证状态（2026-09-17）

已在真实 Abaqus 2026 上验证：

- Fig.1 **Standard deck 10/10 SHA 一致**（`run-case` 目录里重建也一致）。
- Fig.1 mesh data check（`fig1_meshcheck`）+ vendor stage 07 通过。
- Fig.1 Standard **Data Check**：`DATACHECK_COMPLETED_WITH_WARNINGS`，0 error / 10 warning
  （与历史 `fig1_datacheck_m2_final_001` 完全同类）。
- Fig.1 Standard + `self_contact=false` Data Check：0 error / 11 warning（新接触写法被接受）。
- Fig.1 **Explicit**（20% 物理、关自接触）Data Check：0 error，完成标记存在。
- **Explicit smoke solve**：把 `time_period_s` 改成 1e-3 s（`work/r2_explicit_smoke/`，**不改正式配置**），
  Abaqus/Explicit 真正跑完（88 s，`last_step_time = target = 0.001`），提取出 101 点曲线，
  `max_ke_ie_ratio ≈ 1.10` —— 这个 smoke 结果**不是**准静态，只用于证明链路通畅。
- 用历史 Standard ODB 重新提取：60 点曲线与旧脚本逐点一致。

**没有**验证过的（不要当成结论）：Standard 20% 完整 solve（本轮被中止，见下）、Explicit 20% 完整 solve、
科学质量验收、批量运行。

本轮事故记录：我误用 `run-case` + 正式 `config/simulation.json` 启动了一次 Standard solve，
约 4 分钟后被手动终止（`work/r2_final_std/fig1/abaqus/fig1_solve.sta` 走到 increment 10 / step time 0.0703）；
该目录里的 deck、Data Check 报告与部分求解产物都保留作为证据，`status.json` 停在 `solve RUNNING`
（进程被外部杀掉，无法写失败报告）。它的 deck 仍是 10/10 SHA 一致。

## 未实现 / 下一轮

- 批量级的科学验收（接触/PBC/能量、准静态判据）——现在只记录 `max_ke_ie_ratio` 等诊断值，不自动判定。
- `workers>1` 的真实并发运行（逻辑已测，但本机只用 workers=1 跑过真实 batch）。
- retry 的自动策略（如超时后自动重试）——目前只提供显式的 `--retry-failed` / `--max-retries`，且绝不改科学参数。
- Explicit 高级选项（自适应质量缩放、bulk viscosity、ALE 等）。
