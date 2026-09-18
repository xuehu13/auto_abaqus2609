# WORK_LOG — 累积式工作记录

> **本文件是什么**：每次提交/推送的**完整进度与成果记录**（append-only 账本）。
> 每次新增一节，旧内容**永不删除、永不改写**；每节开头标注时间（本地时间 UTC+8，精确到分钟）。
>
> **本文件不是工作上下文**：coding agent 执行任务时**不需要读取本文件**，
> 工作时该怎么做就怎么做；README / AGENTS / HANDOFF_CURRENT / REVIEW_BACKLOG
> 等文档照常独立维护，本文件只是详细的流水报告，与它们内容重叠是有意为之。
>
> 条目格式约定：`## 001 — 2026-09-18 11:45 — 主题`；正文包含
> 背景 / 步骤 / 成果 / 分析 / 偏差与处置 / 产出物 / 关联提交。

---

## 001 — 2026-09-18 11:45 — 第三方审查修复轮：curve QA 闭环、extract 可重跑、文档治理

### 背景

GitHub 公开版收到一份第三方只读审查，提出 3 个实测缺陷与一批文档问题。经本地逐条复核
（全部属实，行号级吻合；一处"Related Files 100% 失效"的说法实测为 13/30 含失效引用、
17/30 仍有效），用户授权按审阅意见施工。

### 修复内容（代码）

1. **extract 重跑必失败（缺陷 1）**：`abaqus_worker/export_history.py` 拒绝已存在的
   `--out`，而 `pipeline/extract.py` 从不清理旧 `raw_history.json`，且注释与
   HANDOFF 都声称"允许覆盖"——手动重跑 `pixi run cli extract`、extract 中断续跑、
   batch `--retry-failed` 三条路径全部撞死。修复：`extract()` 在调用 worker 前
   删除旧 `raw_history.json`；新增 `ExtractRerunTests`（fake worker 复刻真实守卫）。
2. **列名不匹配（缺陷 2）**：`history.csv` 写 `U3_mm/RF3_N`，`curve_qa` 要 `u3_mm/rf3_N`，
   `assess()` 恒报 `HISTORY_MISSING`。修复：列名改为 canonical 小写；`qa-history`
   复用新的 `curve_qa.read_history_csv` 单一实现。
3. **TARGETS 硬编码 0.300（缺陷 3，RB-011）**：默认 case 目标是 20%，论文 11 点 policy
   对它必然 `TARGET_RANGE_NOT_REACHED`。修复：删除模块级 `TARGETS`，policy 必填
   `strain_targets`（≥2 个有限数、严格递增，非法 `CONFIG_INVALID`）；QA 输出键改名
   `strain_targets` / `stress_at_targets_MPa`；`config/quality.example.json` 保留论文
   11 点为示例并在 note 声明 20% 曲线对它按设计 FAIL。
4. **assess 接入流水线**：审阅指出 `assess()` 在 run_case/batch 无调用点、`qa-history`
   是孤立 CLI。修复：`run_case` extract 阶段按新配置 `runtime.results.curve_qa_policy`
   运行 QA 并写 `results/curve_qa.json`（默认关闭、只记录判定不是门槛、resume 按当前
   policy 重算且不触发 stage 重跑）。
5. **extract 阶段补 deck SHA 链**：`summary.json` 记录 `deck_root_sha256`，
   `_stage_done("extract")` 与 build_report 比对（与 datacheck/solve 同语义）。
6. **`*Energy Output`/`*Node Output` 频率继承文档化**（审阅给的两个选项中选文档化：
   显式频率会改冻结 deck 字节、违反"新关键字先真实 Data Check"约束）：
   `render_outputs` docstring 写明继承 `history_frequency`（Standard）/
   `history_time_interval_s`（Explicit）、顺序敏感性与 RB-023 重复 key 现状。

### 文档治理

- 7 个 SUPERSEDED docs 的乱码横幅（各 63 个字面 `?`，中文在写入时被替换）修复为可读
  中文；正文逐字节未动。REVIEW_BACKLOG 横幅单独措辞（该文件按自身规则仍维护）。
- README：两份重复的「真实验证状态（2026-09-17）」章节合并（旧版的 Explicit smoke 实测
  细节与误启动 solve 事故记录保留），"147 个 unittest" 改为"命令 + 证据目录"表述。
- REVIEW_BACKLOG re-reconciliation：RB-008/011/021/024/025/027/028/030 → RESOLVED
  （附解决记录与新文件引用）；RB-023 标注 ACCEPTED（仍活跃）；RB-019 挂上
  `work/r3_smoke/batch_001` 复现线索；30 条的最终引用行脚本校验全部有效。
- HANDOFF_CURRENT 新增第 8 节记录本轮。

### 验证

- `pixi run test` → **core 165 OK（原 150 + 新 15）+ boundary 5 OK**，证据
  `work/pixi_tests_hnxdxmd3`；deck 回归 fixture 仍 10/10（证明未动 deck 字节）。
- `qa-history` CLI 冒烟：论文 policy 对 20% 曲线 `CURVE_QA_FAILED/TARGET_RANGE_NOT_REACHED`
  （按设计）；匹配 policy `CURVE_QA_PASS` 且 `stress_at_targets_MPa` 插值正确。
- 施工中引入过一个问题：Python 文本模式重写曾把 `tests/test_batch.py` 换行转成 CRLF
  （882 行假 diff），已恢复 LF（最终 1 行 diff）。

### 关联提交

- `31ffc12`（2026-09-18 11:45 +0800）`fix: close curve QA loop and make extract
  re-runnable; reconcile docs`，已推送 `origin/main`。

---

## 002 — 2026-09-18 14:54 — 计算实验：ref30_02–05 implicit（8CPU/all）与 explicit（8CPU, T=0.006s/0.01s），暂停于 T=0.01 组

### 背景与目标

用户要求对 30 选择曲面中的第 2–5 号（`ref30_02`…`ref30_05`）做计算实验：
implicit 一组（cpus=8，standard_parallel=all），explicit 两组（cpus=8，T=0.006s 与
T=0.01s），共 12 个 run；单例失败或 >30 min 未成功就停止并计算下一个；结果按文件夹
归档；**不修改任何流水线代码**。

### 实验设计

- 方程取自 tracked `references/validation_30_surfaces.md` 第 2–5 行，与当年 night batch
  `batch_status.json` 的 `source_equation` 逐字核对一致；case 其余参数同
  `config/cases/fig1.json`（iso_level 0.0、unit cell 10 mm、同一套 mesh/CGAL 参数）。
- 配置脚手架（全部新增于 `experiments/ref30_2to5_20260918/`，不动 pipeline）：
  - `cases/ref30_0{2..5}.json`（4 份）
  - `simulation_implicit.json`（= `config/simulation.json` 原样，Standard，T=1.0s，20% 目标）
  - `simulation_explicit_T0.006s.json` / `simulation_explicit_T0.01s.json`
    （`solver.type=explicit_dynamic`，`time_period_s=0.006/0.01`，
    `history_time_interval_s=T/100`（≈101 点曲线，沿用 smoke 基线约定），
    `field_number_interval=10`，无质量缩放；材料/接触/20% 目标/smooth_step 与主配置一致）
  - `runtime_implicit_cpus8_all.json`（datacheck+solve：cpus=8、standard_parallel=all）
  - `runtime_explicit_cpus8.json`（cpus=8；explicit 不传 standard_parallel，见
    `abaqus.py::abaqus_run_argv`）
  - `run_all.py`（顺序驱动：每例硬上限 2100s，超时按 **PID 树** taskkill，绝不用镜像名；
    结果追加 `experiment_log.csv`）
- 超时策略：datacheck 600s；solve 初始 1500s，**12:00 起改为 1800s**（见"偏差与处置"）。
- 干跑校验：所有 case/simulation/runtime 先过 `load_case` / `load_simulation` /
  `load_runtime` 再开跑。
- 结果目录：`work/exp_ref30_2to5_20260918/<组>/<case_id>/`（每组一个文件夹，
  结构与其他 attempt 相同：mesh/ abaqus/ results/ status.json run.log）。

### 执行时间线（UTC+8）

| 时刻 | 事件 |
|---|---|
| 12:01 | implicit/ref30_02 启动（driver 后台运行） |
| 12:03 | ref30_02 datacheck 通过（52.8s，**8CPU + all 未复现 RB-012 的 threads-per-domain 错误**） |
| 12:33 | ref30_02 `SOLVE_TIMEOUT`（停滞 step time 0.312，1500s 上限） |
| 12:34–12:41 | ref30_03：datacheck 过，solve 364.5s 自行失败（`SOLVE_FAILED`），extract 门正确拒绝 |
| 12:36–13:09 | ref30_04：停滞 0.532，`SOLVE_TIMEOUT` |
| 13:03–13:31 | ref30_05：1500s 记 `SOLVE_TIMEOUT`；**orphan standard.exe 继续跑完**（`.sta`：COMPLETED SUCCESSFULLY，~13:31 落盘 ODB 21.4MB） |
| 13:31–14:23 | explicit T=0.006 四例：**4/4 DONE**（solve 1163/474/430/587s） |
| 13:48 | 发现并按 PID 清理两个 orphan standard.exe（ref30_02/ref30_04 的停滞解，各占 8 线程 + license） |
| 14:23 | explicit T=0.01 / ref30_02 启动 |
| ~14:38 | 该 solve 在 ~83% step time 处随会话侧停止（非流水线超时、非收敛问题）；driver 停止 |
| 14:45 | 用户指示暂停；driver 终止、进程清点归零、`experiment_log.csv` 补记该 run |
| 14:52 | ref30_05 implicit 恢复提取完成（见下） |

### 结果总表

| 组 | case | 结果 | solve 耗时 | 点数 | final_strain | max_stress (MPa) | KE/IE |
|---|---|---|---:|---:|---:|---:|---:|
| implicit (8CPU/all) | ref30_02 | SOLVE_TIMEOUT（停滞 0.312） | 顶满 1500s | – | – | – | – |
| implicit | ref30_03 | SOLVE_FAILED | 364.5s | – | – | – | – |
| implicit | ref30_04 | SOLVE_TIMEOUT（停滞 0.532） | 顶满 1500s | – | – | – | – |
| implicit | ref30_05 | 管道记 TIMEOUT，**分析实际完成**，曲线已恢复¹ | ~1500s+ | 78 | **0.20000** | 0.2562 | **0.0053** |
| explicit T=0.006s | ref30_02 | **DONE** | 1163.0s | 101 | 0.19996 | 0.2666 | 0.992 |
| explicit T=0.006s | ref30_03 | **DONE** | 474.1s | 101 | 0.20001 | 0.1479 | 1.023 |
| explicit T=0.006s | ref30_04 | **DONE** | 430.2s | 101 | 0.19997 | 0.3828 | 0.984 |
| explicit T=0.006s | ref30_05 | **DONE** | 587.1s | 101 | 0.19976 | 0.2547 | 0.925 |
| explicit T=0.01s | ref30_02 | **用户暂停**（solve ~83% 处停止） | ~14 min | – | – | – | – |
| explicit T=0.01s | ref30_03–05 | 未启动 | – | – | – | – | – |

¹ 恢复提取写入 `work/exp_ref30_2to5_20260918/implicit/ref30_05_recovered_from_timeout/results/`
（extract 走 `--odb` 路径，attempt 目录未改动，status.json 仍如实为 SOLVE_TIMEOUT）。

### 分析

1. **standard_parallel=all 可用**：implicit 4 例 datacheck 全部
   `DATACHECK_COMPLETED_WITH_WARNINGS`，solve 阶段也在 all 模式下运行——RB-012 记录的
   threads-per-domain ERROR 未复现，历史 workaround（=solver）不再是必需。
2. **implicit 停滞与历史完全同位**：ref30_02 停在 0.312、ref30_04 停在 0.532、
   ref30_03 快速失败——与 RB-020 登记的 night batch 失败位置一致，证实停滞是
   物理/数值原因，与旧临时 runner 无关。新信息：ref30_05 在干净管道下**能跑完**
   （~27–28 min，历史只拿到 partial curve）。
3. **explicit T=0.006 全部收敛到 20%**：final_strain ≈0.200、101 点完整曲线；
   但 **KE/IE ≈ 0.93–1.02，远不满足准静态（<1%）**——这些是真实动力响应，
   不能当准静态应力-应变曲线解释。对照 implicit ref30_05：KE/IE=0.53%，满足判据。
4. **耗时标定**：explicit solve 对 T 近似线性、对曲面强敏感（同 T=0.006 下
   7.2–19.4 min）；T=0.01/ref30_02 实测 14 min 到 83%，推算全程 ~17 min，
   **比 T=0.006 慢仅 ~1.4×（非 1.67 线性外推）**——四例预计都能进 30 min 预算。
5. **RB-014 kill-tree 缺口实证**：`subprocess` 超时只杀 launcher，orphan
   standard.exe 继续占 8 线程 + license（本次两例，已按 PID 手工清理；ref30_05 的
   orphan 跑完后自行退出，其 ODB 因此得以恢复）。
6. 附注：extract 的 KE/IE 诊断在早期零能量点会打印 `invalid value encountered in
   divide` 的 RuntimeWarning——0/0 只发生在非 active 点、被 `ratio[active]` 掩蔽，
   对结果无影响（既有行为，未改动）。

### 偏差与处置

- **solve 上限 1500s → 1800s（12:00 起）**：初始 1500s 是为让 datacheck+solve 合计
  <30 min；explicit T=0.006/ref30_02 实测 19.3 min 后，按用户">30min 停止"规则把
  solve 上限精确对齐 1800s（既不提前白杀健康解，也不超用户预算）。implicit 组前 4 例
  是在 1500s 上限下跑的（其失败均为停滞/快速失败，与上限取值无关）。
- **T=0.01 组暂停**：用户指示；ref30_02 的 status.json 保持 RUNNING/solve（resume 语义：
  下次 `run-case` 会视为"上次进程已死"从 solve 续起，mesh/datacheck 复用）。
- 会话侧停止曾连带终止在跑的 solve（14:38 事件），与收敛无关；证据保留在 case 目录。

### 产出物

- `experiments/ref30_2to5_20260918/`：cases ×4、simulation ×3、runtime ×2、
  `run_all.py`、`README.md`（设计+状态）、`experiment_log.csv`（逐 run 总表）、
  `SUMMARY_20260918_pause.md`（小结）。
- `work/exp_ref30_2to5_20260918/`：12 个 case 目录（含暂停/失败证据）+ 恢复提取目录
  （git-ignored，按仓库惯例结果不入库）。
- 同步更新：HANDOFF_CURRENT §9、README 真实验证状态、REVIEW_BACKLOG（RB-012/014/020 追加
  observed facts）。

### 待用户决定

- T=0.01 组是否续跑（ref30_02 从 solve 续起 ~3–4 min 即完，ref30_03–05 各约 10–15 min）。
- implicit 各例是否需要更长墙钟重试（ref30_05 证明部分曲面 30 min 内可完成）。

### 关联提交

- 本次提交（实验配置/驱动/文档 + 本日志首两节）；前置代码提交 `31ffc12`（同日上午）。
