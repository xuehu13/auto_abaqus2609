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
3. **explicit T=0.006 全部完成 20% 压缩**：final_strain ≈0.200、101 点完整曲线；
   全程 max KE/IE ≈ 0.93–1.02，但该峰值可能受启动阶段内能接近零影响，
   不能单凭它判定整条曲线非准静态。对照 implicit ref30_05 的全程峰值为 0.53%，
   低于 1% 能量阈值；两组均未完成综合准静态验收（见条目 007 下方的勘误）。
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

---

## 003 — 2026-09-18 20:02 — Abaqus 超时进程树强制终止 + 确认机制（RB-014 kill-tree 缺口闭合）

### 背景与需求

条目 002 的实验实证了 kill-tree 缺口：solve 墙钟超时只杀 launcher，orphan `standard.exe`
继续占 8 线程 + license。用户据此提出五点硬性要求：① 超时必须强制终止该 case 的**整个**
Abaqus 进程树（launcher、standard.exe 及相关子进程）；② 终止后**不得立即**启动下一个
case，先确认该 case 相关进程全部退出；③ 终止必须基于当前 case 的具体进程/PID，禁止
`taskkill /IM` 之类的镜像名杀法；④ 已有的 .sta/.msg/.dat/partial ODB 全部保留；
⑤ 树杀不干净就停止 batch 并明确报错，清干净后才允许继续。

### 实现（`pipeline/abaqus.py`，三层递进）

1. **Windows Job Object（首选，OS 级保证）**：launcher 启动时通过 `AssignProcessToJobObject`
   把它放进一个 `KILL_ON_JOB_CLOSE` 的 Job——之后 Abaqus 自己 spawn 的所有后代
   （standard.exe、DAE/packager、mpi）自动继承成员身份，超时一次 `TerminateJobObject`
   全部结束。实现细节：这台 Windows 内核对 class 9 的结构体长度期望是 **144 字节**
   （BASIC 无 IoInfo 的老式布局）而非头文件的 192，代码按 `[192, 144]` 双尺寸探测，
   尺寸不对只会干净地报 ERROR_BAD_LENGTH，不会半写。
2. **PID 定向兜底**：root launcher 一律 `taskkill /F /T /PID <pid>`（带 /T 连带其子树）；
   再按**本 case 的 deck 目录 + job 名**在进程命令行里精确匹配（`_case_pids`，小写化、
   分隔符归一、**显式排除控制器自身 PID**），逐 PID 清理逃逸/晚生成的进程。全程没有
   任何按镜像名的杀法。
3. **确认等待**：终止后轮询进程枚举（PowerShell `Get-CimInstance`，2s 间隔，60s 宽限），
   直到本 case 匹配进程清零才返回——batch 天然被阻塞在这道确认上，不会带着残留进程
   进入下一个 case。
   - 宽限期内清零 → 照常把 `TimeoutExpired` 抛回给 stage 层（`DATACHECK_TIMEOUT` /
     `SOLVE_TIMEOUT` 消息不变，证据目录保留语义不变）。
   - 宽限期满仍有幸存者 → 抛**新的致命错误** `ABAQUS_TREE_NOT_TERMINATED`。

**batch 停止机制**（`pipeline/batch.py`）：`PipelineError` 增加 `fatal` 标志。
`run_case_safe` 在捕获 fatal 的**worker 线程内**立刻 set 共享 `stop_event` 再抛出
（否则线程池会在主线程处理 fatal 之前就把下一个排队的 case 启动起来——单测抓到过这个
竞态）；已排队的 case 看到 stop_event 直接跳过不启动；已在上跑的 case 允许跑完
（与 KeyboardInterrupt 的既有哲学一致）；batch 仍写出汇总三件套后把 fatal 向上抛，
CLI 以非零码明确报错。fatal 一律不重试。

### 测试

- 新增 6 个单测：超时杀树并验证后才返回（root+匹配 PID 都被终止）；幸存者 → fatal
  `ABAQUS_TREE_NOT_TERMINATED`；正常退出完全不碰进程；PID 匹配只命中本 case
  （不误伤其他 case、不匹配控制器自身命令行）；混合分隔符/大小写归一；batch fatal
  停止（case_C 不启动、汇总仍写出、异常向上抛）。
- `pixi run test` → **core 171 OK（165 + 新 6）+ boundary 5 OK**。
- **真实 Abaqus 验证**（scratch 目录 `work/killtree_selftest/`，fig1 全流程）：
  1. `datacheck.timeout_s=15` 强制超时：mesh_datacheck 15s 到点 → 真实 Job terminate +
     taskkill + 真实进程枚举确认 → `DATACHECK_TIMEOUT`，部分产物（.dat/.023/.cax/.com
     等）全部保留，进程清零（唯一残存的 ABQcaeK 是测试前就存在的无 job 共享守护进程，
     匹配器正确地没有碰它——守护进程不是 case 进程）。
  2. 正常路径：同目录重跑 mesh datacheck 至完成 → `PASSED` / return_code 0，证明
     Popen 化改造后的正常分支无回归。
- **观察（未修，登记用）**：被超时终止的 meshcheck 目录若直接重跑，vendor 阶段 07 会
  按"已有产物"幂等校验那份不完整的 .dat → 永远 FAIL；需要把该目录挪走（保留证据）才
  能重新跑。这属于 resume/reconciliation 语义（RB-014 剩余部分），不是本次改动引入的。

### 关联提交

- 本次提交（abaqus.py 进程树控制、batch fatal 语义、6 个新测试、文档同步；
  前置提交 `31ffc12`、`a710334`）。

### 复查修正（2026-09-18 20:2x，独立审查后追加）

按"只看代码不看汇报"的复查要求重审了本条目全部改动，发现并修正三处：

1. **case_key 未解析绝对路径**：CLI 传相对 `--work-root` 时，匹配键是相对路径而真实
   solver 命令行里的 `-indir/-outdir` 是绝对路径——兜底清扫会失明，确认环节可能在有
   残留时误判"已清零"。修正：`_run_launcher` 内 `Path(cwd).resolve()`。
2. **枚举失败 ≠ 已清零**：`_system_processes` 原先在 PowerShell 失败时返回 `[]`，确认
   环节会把"无法枚举"当成"确认干净"直接放行——违反"不确认就不继续"。修正：失败返回
   `None`，验证窗口内持续重试，宽限期满仍不可确认 → 以哨兵值 `-1`（含义见错误消息）
   进入 fatal 分支。新增对应单测。
3. **验证窗口内只看不杀**：幸存者现在在每次轮询时被再次终止（最大化宽限期内清零的
   机会），窗口结束仍存活才 fatal。新增对应单测。

同时补上了此前缺失的最关键真实验证：**solve 阶段真实 standard.exe 的超时终止**
（此前只验证过 meshcheck 预处理器阶段）——scratch 目录 fig1 真实 datacheck 通过后，
solve 30s 超时：standard.exe 被终止、`killtree_selftest` 相关进程清零、
`.dat`(20KB)/`.msg`(7.7KB)/部分 `.odb`(6.3MB) 证据保留、状态记 `SOLVE_TIMEOUT`。
全套测试 **173 OK**（171 + 本次复查新增 2）。

---

## 004 — 2026-09-18 20:39 — 运行入口整理：production.json 总配置 + run-experiment + thickness_mode

### 背景与目标

用户要求"小范围、科研自用"的运行入口整理：新使用者只编辑一个带注释的总配置
`config/experiments/production.json`、准备 `cases.jsonl`、执行一条
`pixi run cli run-experiment --config ...`，即可走完现有已验证流水线
（surface → mesh → mesh datacheck → build → physical datacheck → solve → extract →
batch summary）。**不重实现 pipeline、不做通用框架**；另加一个小能力
`shell.thickness_mode`（relative_density / fixed）。

### 施工前核对

只读核对了 mesh.py（load_case/merge_case/prepare_ingredients）、batch.py
（load_cases/_write_batch_files/batch_config.json）、build.py、run.py、各 config，
从**当前代码**提取真实参数面（require_keys 的 required/optional 集合、runtime 的
_RESULTS_KEYS 等），不按旧文档猜。

### 改动清单

- **`config/experiments/production.json`（新增）**：12 个大类（01 EXPERIMENT …
  12 RUNTIME）全覆盖当前代码实际支持的用户可调参数；每个参数上一行有简洁中文注释
  （单位/作用/适用 solver）；大类之间横幅分割。注释约定 = **仅整行 `//`**，
  读取时剥离后走标准 `json.loads`（字符串内的 `//` 不受影响）。
- **`pipeline/experiment.py`（新增，薄适配层）**：`load_production`（剥注释+解析+
  顶层 12 类目 require_keys 校验）、`build_inputs`（拆成 case defaults =
  geometry+mesh；simulation = material/shell/pbc/platen/contact/loading/solver/output；
  runtime；cases_file/work_root 相对仓库根解析并检查存在性；experiment_id 过
  safe_id 校验）、`start_experiment`（把三份解析后配置 + `production_used.json`
  写入 batch 目录作为 provenance 快照，然后调用**现有** `run_batch`）。
- **`run.py`**：新增 `run-experiment --config` 子命令；docstring 与 `plan` 增加入口说明。
- **thickness_mode（mesh.py/build.py 各极小改动）**：`shell.thickness_mode`
  （默认 `relative_density`，行为与历史完全一致）+ 可选 `shell.thickness_mm`；
  `fixed` 模式直接以 `thickness_mm` 为正式物理壳厚度；两者互斥（relative_density 下
  thickness_mm 非 null → 明确报错，不静默混用）；`build_report.model.thickness_source`
  记录厚度来源。`config/simulation.json` 的 shell 块显式补上这两个键（行为不变）。
- **`docs/RUN_GUIDE.md`（新增）**：普通使用者运行手册；**`README.md`** 顶部加入口
  「普通运行请看 docs/RUN_GUIDE.md」。

### 映射方式（production.json → 现有 pipeline）

```
production.json
  ├─ experiment            → run_batch(work_root=<work_root>/<experiment_id>,
  │                                   workers/retry_failed/max_retries/force)
  ├─ cases_file            → run_batch(cases_path=...)（沿用现有 JSONL + per-case overrides）
  ├─ geometry + mesh       → 快照 batch_dir/case_defaults.json → run_batch(defaults_path=...)
  ├─ material/shell/pbc/   → 快照 batch_dir/simulation.json → run_batch(simulation_path=...)
  │  platen/contact/loading/solver/output
  └─ runtime               → 快照 batch_dir/runtime.json → run_batch(runtime_path=...)
```

batch 目录内同时保存 `production_used.json`（剥离注释后的完整有效配置）。已存在且
内容一致 → 允许 resume；不一致 → `EXPERIMENT_ID_REUSE` 报错（提示换新 experiment_id），
绝不覆盖证据。batch_config.json 天然指向 batch 目录内的快照，自洽可溯源。

### 测试

- 新增 `tests/test_experiment.py`（12 测）：整行注释剥离（含字符串内 `//` 保留、
  行尾注释不支持）、shipped production.json → 三份文档全部通过**真实的**
  `load_cases`/`load_simulation`/`load_runtime` 校验、solver 切换、路径解析、
  快照写入与 resume/改配置复用报错、run_batch 调用边界（mock，不启动 Abaqus）。
- `tests/test_build.py` 新增 ThicknessModeTests（5 测）：relative_density 与不带
  标记的默认行为逐字节一致；fixed 厚度进入 *Shell Section 且
  `thickness_source=fixed`；非法模式/非法 fixed 厚度/两来源混用全部明确报错。
- 全套 **190 OK**（原 173 + 新 17）；`pixi run cli run-experiment --help` 与
  `plan` 正常；真实边界检查确认 production.json 派生的快照被真实 loader 接受。
- **未跑真实 Abaqus 批量**（按本轮要求不启动长时间求解；thickness_mode 的 deck 级
  一致性由回归 fixture 覆盖：relative_density 默认路径的 deck 字节与冻结基线一致）。

### 兼容性

`run-case` / `run-batch` / `summarize-batch` / `mesh` / `mesh-datacheck` / `build` /
`datacheck` / `solve` / `extract` / `qa-history` 全部未动接口，现有
simulation.json / case_defaults.json / runtime*.json 保留；旧入口 = 高级调试入口，
run-experiment 只是上面一层薄用户入口。pipeline 大模块仅 mesh.py（厚度 4 行）与
build.py（shell 校验 + 报告字段）按任务许可做了必要小改。

### 关联提交

- 本轮改动已随本次提交入库（本条目 + experiment.py + production.json + RUN_GUIDE + 测试）。

---

## 005 — 2026-09-19 10:08 — 修复参数实验暴露的两个问题：vendor 0.20mm 硬门 + *Fixed Mass Scaling 位置

### 背景

`scripts/run_para_aly_24.py` 的 24 组 Explicit 参数实验（3 曲面 × Fine/Coarse × T=0.01/0.02 ×
MS0/MS9）暴露两个问题：Coarse（0.25mm）12 例全部死于 vendor Stage 03 的固定 0.20mm 上限；
Fine+MS9 6 例全部 Data Check 失败。用户明确授权修改冻结 vendor 的验收规则例外，并要求
保留 Coarse 0.25 配置、不破坏 Fine baseline、不重跑完整实验。

### 根因（均以本地证据坐实）

1. **Stage 03 固定上限**：`03_standardize_master_boundaries.py` 的 pass_status 含
   `all_segments > 0.20 == 0`。Coarse diverse_05 报告：`n_segment_gt_020=382`、
   `segment_max_mm=0.25`（=配置值），而 `max_abs_f≈9e-12`、`endpoint_mismatch=0`、
   `n_segment_lt_005=0` 全过——唯一 FAIL 原因即写死的 0.20。
2. **Mass Scaling 位置**：`build.py` 把 `*Fixed Mass Scaling` 写在 `*Step` 之前。
   MS9 的 `.dat` 第 66 行原始报错：`***ERROR: in keyword *FIXEDMASSSCALING, file
   "step_loading.inc", line 4: The keyword is misplaced. It can be suboption for
   the following keyword(s)/level(s): step`。

### 修复

- **Stage 03**：pass_status 删除 `>0.20` 条款；保留 `max_f<1e-8`、`endpoint mismatch<1e-10`、
  `segments<0.05==0` 三个必要条件；`Segments > 0.20` 打印与 `n_segment_gt_020` 报告统计保留。
- **Stage 04（施工中发现的第三处同款 0.20 门）**：`04_export_cgal_input.py` 的
  `MAX_SEGMENT=0.20` 同样 gate 了 feature 曲线段长（Coarse 首次推进到 Stage 04 即 FAIL）。
  同样仅删除 max-segment 条款；`MIN_SEGMENT>0.05`、plane/f/endpoint 门全保留；
  `global_min/max_segment_mm` 统计保留。此项略出用户点名的文件清单，但为验证 A
  「后续 CGAL 正常」的必要条件，与 Stage 03 同类同处理。
- **AI_HANDOFF_SPEC §10.3/§10.4** 最小同步（硬性 PASS 清单去掉 0.20 行 + 变更注记；
  契约行改为"仅报告、无硬性上限"）。`REFERENCE_RESULTS.md` 历史数值未动。
- **build.py**：`*Fixed Mass Scaling`（含注释）移入 Explicit `*Step` 内
  （`*Dynamic, Explicit` 之后、`*Boundary` 之前）；MS0/Standard 不输出；无 ELSET、
  无 adaptive/target dt。`SOURCE_DATACHECK_INVALID` 保护逻辑未动。
- **MANIFEST_SHA256.txt**：同步 03/04/AI_HANDOFF_SPEC 三行 SHA，`vendor_hashes()` 31 文件全过。

### 验证

- 单测新增/扩展 4 处（solver 关键字顺序 + Standard 无 mass scaling + Stage 03/04
  源码契约 + manifest 一致性），全套 **194 OK**。
- **真实验证 A**：diverse_05 Coarse(0.25) 全网格流程 Stage 00→06 通过
  （`work/fix_verify/diverse_05`），`mesh_result.json` 正常生成；mesh Data Check pass=true。
- **真实验证 B**：diverse_05 Fine + Explicit T=0.02 + MS9 → `*Fixed Mass Scaling, factor=9.0`
  位于 `*Step` 内（`*Dynamic, Explicit` 之后、`*Boundary` 之前）；真实 Abaqus 2026
  Data Check = `DATACHECK_COMPLETED_WITH_WARNINGS`（0 error / 1 warning）。MS0 负例：
  deck 无 Mass Scaling、Data Check 同样通过。

### 关联提交

- 本轮修复本地提交（未 push，待用户要求）。`scripts/run_para_aly_24.py` 为用户自己的
  实验驱动脚本，由用户自行提交。

---

## 006 — 2026-09-19 10:2x — MS9 warning 确认 + 注释/VERSION.txt 同步

用户复查条目 005 后的三个小疑问，全部处理：

1. **MS9 Data Check 唯一 warning 原文**（`.dat` 第 186 行，`.msg` 无 warning）：
   `***WARNING: THE OPTION *BOUNDARY,TYPE=DISPLACEMENT HAS BEEN USED; CHECK STATUS
   FILE BETWEEN STEPS FOR WARNINGS ON ANY JUMPS PRESCRIBED ACROSS THE STEPS IN
   DISPLACEMENT VALUES OF TRANSLATIONAL DOF. FOR ROTATIONAL DOF MAKE SURE THAT
   THERE ARE NO SUCH JUMPS. ALL JUMPS IN DISPLACEMENTS ACROSS STEPS ARE IGNORED`。
   **与 mass scaling 无关**：这是用 `*Boundary, type=displacement` 施加 RP_TOP 位移的
   通用提示（跨 step 位移跳转会被忽略的例行告知）；**MS0 对照组的 `.dat` 里有逐字相同
   的同一条 warning**（两个 datacheck 均为 0 error / 1 warning）。不影响 MS9 参数
   实验的物理含义，也不涉及质量缩放适用范围/质量增加/刚体/shell formulation。
2. **build.py 陈旧注释修正**：`render_step_and_loading` docstring 原写
   "mass scaling ... is written before the step"（关键字位置修复前的旧表述），已改为
   "written as *Fixed Mass Scaling INSIDE the Explicit step (after *Dynamic, Explicit,
   before the loading *Boundary)"。
3. **VERSION.txt 最小更新**：补两行——"segments > 0.20 mm are reported only (no hard
   gate) since 2026-09-19；0.25 mm boundary spacing revalidated end-to-end
   (stages 00-06 + Abaqus mesh data check, diverse_05) on 2026-09-18/19"。
   MANIFEST 中 VERSION.txt 行同步，`vendor_hashes()` 31 文件全过。

全套测试 **194 OK**。关联提交：`f384e54`（已推送 origin/main）。

---

## 007 — 2026-09-20 13:52 — para_aly 24 组参数敏感性实验：完成、修复、重跑与完整分析

### 研究问题

Explicit 求解点阵压溃时，三个最重要的计算参数——**网格尺寸**（boundary/edge/facet
0.18 vs 0.25 mm）、**加载时长 T**（0.01 vs 0.02 s）、**质量缩放**（OFF vs factor=9）——
对应力-应变曲线、KE/IE 与计算时长各有多大影响？参数重要性如何排序？

### 实验设计

3 曲面（diverse_05 早峰软化 / diverse_04 单调硬化 / diverse_28 五次斜率反转振荡）×
2 mesh × 2 T × 2 MS = **24 case**。固定：Explicit、理想弹塑性（E=484 MPa、ν=0.4、
ρ=1.1e-9、plastic_table=[[8.0,0.0]]）、ε=0.2 smooth_step、S3R/5 积分点/relative_density
0.1、friction 0.6、self_contact true、cpus=8、workers=1、history=T/100（101 点）。
驱动脚本 `scripts/run_para_aly_24.py`（8 组配置 → 现有 start_experiment()）；
结果 `work/para_aly/<mesh>/<T>/<MS>/<case>/`（git-ignored），配置快照留各 batch 目录。

### 过程（含两次失败与修复）

1. **首轮过夜运行**：Fine/MS0 6 例 DONE；**Fine/MS9 6 例全部 Physical Data Check 失败**
   （根因：`*Fixed Mass Scaling` 被写在 `*Step` 之前，Abaqus 2026 报 misplaced；
   solve 阶段的 `SOURCE_DATACHECK_INVALID` 是正确的下游保护）；**Coarse 12 例全部死于
   vendor Stage 03**（根因：写死的 segment>0.20mm 硬门与用户配置 0.25mm 冲突）。
2. **修复（条目 005，commit `0135dc7`）**：Stage 03/04 删除 0.20mm 硬门（统计保留为
   诊断）；`*Fixed Mass Scaling` 移入 Explicit Step 内；MANIFEST/SPEC/VERSION 同步。
   修复经真实最小验证：Coarse diverse_05 网格 00→06 全过 + mesh datacheck PASS；
   Fine/MS9/T0.02 datacheck 0 error；MS0 负例干净（条目 006 确认唯一 warning 与 MS 无关）。
3. **清理与重跑**：精确删除 18 个失败目录（保留 4 份快照/batch 配置；成功 6 例不动）→
   smoke 单例（diverse_04/Coarse/T0.02/MS9 完整六 stage DONE）→
   `scripts/run_para_aly_remaining17.py`（DONE 自动 skip，smoke 例出现在统一
   batch_summary.csv）一夜跑完剩余 17 例。

### 结果

- **24/24 DONE**，101 点曲线全部到达 ε≈0.200（0.1992–0.2006）；累计墙钟 **3.59 h**，
  最重一例 Fine/T0p02/MS0/diverse_04 = 26.3 min。
- Abaqus 0 error；warning 仅 2 种且 24 例一致（*BOUNDARY,TYPE=DISPLACEMENT 例行提示、
  *MPC/*EQUATION echo 抑制 NOTE）；无 distortion/element deletion/negative
  eigenvalue/singularity。12 个 MS9 deck 关键字位置全部正确。
- mesh 规模（diverse_04）：Fine 8372 节点/15914 单元 vs Coarse 3489/6368（2.5×）；
  厚度 0.37585 vs 0.37570 mm（相对密度公式下随表面积略变）。

### 分析

**耗时模型**（近似独立可乘）：MS9 加速 **2.65×（Fine）/ 2.0×（Coarse）**（实测 dt：
Fine 1.52e-8→4.15e-8，≈理论 ×3；Coarse 2.37e-8→9.17e-8）；T×2 → 时间 **1.85–1.98×**；
Fine→Coarse → **2.4×**。最贵/最便宜组合 ≈ **11×**。

**峰值应力对三参数全部稳健**（跨 8 组合离散度：diverse_05 ±5.0%、diverse_04 ±4.5%、
diverse_28 ±2.7%）——无论怎么选参数，峰值水平可信。

**逐参数归因**（固定应变点 e=0.15/0.199，MPa，对另两因素取平均）：

| 曲面 | mesh(粗−细) | T(0.02−0.01) | MS(9−0) |
|---|---|---|---|
| diverse_04 | **+0.0135 / +0.0079** | −0.0039 / −0.0053 | **+0.0084 / +0.0034** |
| diverse_05 | +0.0005 / +0.0017 | −0.0040 / −0.0022 | **+0.0053 / +0.0029** |
| diverse_28 | **+0.0078 / +0.0027** | +0.0002 / +0.0005 | −0.0002 / −0.0002 |

1. **mesh 第一重要**（曲线均值差 4.1–4.5%）：粗网格应力系统性偏高（三曲面方向一致），
   高应变段最明显（坍塌带自由度少、局部化更早更硬）。
2. **MS 第二**（2.4–4.1%）：MS9 系统性抬高 diverse_04/05 的应力（惯性增大→响应偏硬），
   软化/陡降段最敏感（diverse_05 e≈0.05 处点差 24–34%）。
3. **T 第三**（1.5–3.8%）：更长 T 应力略降（方向符合准静态化预期；理想弹塑性无率相关，
   纯惯性效应）。
4. **振荡型曲面（diverse_28）逐点差可达 40–50%**，但发生在 e≈0.17–0.19 局部极小值附近，
   是**坍塌事件的相位移动**而非系统误差（端点 e=0.199 离散仅 ±1.9%）——对这类曲面
   应比峰值/平台均值，不比逐点。

**2026-09-21 勘误：不能用全程 max KE/IE 判定 24 例全部非准静态。**
原始 `summary.json` 的 max KE/IE = **0.84–1.20**，峰值主要位于启动阶段内能接近零的
区间，分母过小使该指标失真。按 `history.csv` 中 `-u3_mm/10 >= 0.01`、`ALLIE > 0`
重新计算后，24 例中 **6 例**的 KE/IE 峰值超过 1%；其余 18 例不能直接称为准静态
PASS，因为接触、PBC、局部惯性与曲线收敛还没有完整验收。原文由全程峰值推断
“动能主要来自坍塌带而非加载速率”的因果结论同时撤回。**目前可说的是：这批曲线
到达目标应变，参数敏感性结果已记录，是否达到准静态极限仍待 T 收敛实验。**

### 下一步建议（优先级序）

1. **准静态收敛实验**：1–2 曲面 × T=0.05/0.1/0.2s（Coarse/MS9 便宜 ≈17 min/例），
   回答"曲线何时收敛、KE/IE 何时显著下降"——显式结果能否当准静态用的直接依据。
2. **MS factor 扫描**（9/25/100，Fine/T0p02）：确认大 factor 下软化解漂移。
3. **第三档网格**（0.21 或 0.35mm）+ **thickness_mode=fixed 锁厚**：网格无关解 +
   解耦网格密度与厚度随表面积的变化。
4. **摩擦扫描**（0.2/0.6/1.0）：接触主导问题里与实验对标的最大不确定项。
5. 壳积分点 5 vs 9；self_contact / PBC 转动自由度对照。
6. 方法：振荡曲面峰值/平台指标；24 例聚合出表脚本。

### 产出物

- 脚本（本提交入库）：`scripts/run_para_aly_24.py`、`run_para_aly_smoke_one.py`、
  `run_para_aly_remaining17.py`（`remaining18` 方案被单例 smoke + 17 重跑取代，已删）。
- 结果与配置快照：`work/para_aly/`（本地，git-ignored）。
- 本条目即完整分析报告；修复部分详见条目 005/006。

### 关联提交

- 本次提交（脚本 + 本条目 + HANDOFF/README 同步）。

---

## 008 — 2026-09-21 — 硬化材料求解器对照、绘图与 2×2 Sigmoid 初筛

### 已有本地证据

- `work/hardening_compare/{implicit,explicit}/diverse_05/` 两例均为 `DONE`，
  `simulation_used.json` 的塑性表相同，mesh NPZ 与 PBC pairs 的 SHA 相同，最终压缩应变
  约 20%。Standard Dynamic Implicit：峰值应力 0.25624 MPa、solve 约 872 s、
  全程 max KE/IE 0.00529；Explicit：峰值应力 0.24785 MPa、solve 约 2043 s、
  全程 max KE/IE 0.93540。峰值差约 3.39%，应变 ≥1% 的共同区间内逐点平均相对误差
  约 29.45%。分析步时长分别为 1.0 s 和 0.02 s，不能把该对照解释为求解器等价验证。
- 理想弹塑性 `diverse_05` 的 Standard `*Static` 对照：真实 Abaqus Data Check 完成
  （有 warnings），但 solve 因时间增量小于最小值而失败。`application="static"`
  渲染与 12 个 solver deck 单测已通过；这仅是语法和渲染验证，不是静力收敛证明。
- `scripts/test_sigmoid_2x2_geometry.py` 的单例 G/P/D/I-WP 预览：κ=7、采样间距
  0.25 mm，临时曲面 36002 顶点/69892 三角形；场值 X/Y 周期误差 0，盒内和
  XY 周期合并后均为 1 个连通分量，有限采样下未见非流形边或内部开放边。
  这不检验有限壳厚、自交、连接强度，也不是 Abaqus 网格验证。

### 本次整理

- `scripts/run_hardening_compare.py` 从既有成功快照构造同材料对照；默认每次写入
  唯一的新 `work/hardening_compare_<时间戳>/`，`--check-only` 只生成并核对配置。
  不带该参数会启动两个完整 case（含长时间 Abaqus solve），须显式决定后再运行。
- 绘图脚本 `make_para_aly_ppt_figures.py`、`make_para_aly_config_figures.py`、
  `make_para_aly_runtime_table.py`、`make_hardening_compare_figure.py` 只读本地结果，
  各自写入新的 `work/figures_*_<时间戳>/`。前者的图 07/08 使用含硬化的历史
  Implicit 与理想弹塑性的 Explicit，材料不同，不能作为同材料求解器误差图；
  同材料对照应看 `make_hardening_compare_figure.py`。
- Sigmoid 脚本输出新的 `work/sigmoid_preview_<时间戳>/`；`geo` Pixi 环境新增
  Matplotlib 3.10.9。生成图、配置快照和计算结果均留在 git-ignored `work/`。
- 汇报 PPT 提到的 200 组组合与 73.5% 几何成功率，目前在仓库内未找到对应的
  原始数据或可重跑批量程序，保持待复核，不计入已验证的流水线能力。

---

## 009 — 2026-09-23 — 模块化 deck 导出为独立单文件 INP

- 现有物理 deck 是 `physical.inp` + 9 个 `blocks/` / `ingredients/` include；这种形式
  可直接供 Abaqus 使用，但移动时必须保持整个 `abaqus/` 目录结构。
- 新增 `scripts/export_flat_inp.py`：递归展开 `*Include`，检测循环、缺失文件和越界路径，
  输出必须不存在；只读源 deck，不覆盖历史结果，不启动 Abaqus。
- 实测源：`work/para_aly/Coarse/T0p01/MS9/diverse_28/abaqus/physical.inp`。
  输出：`work/inp_exports_20260923T203032/diverse_28_Coarse_T0p01_MS9.inp`，
  465735 bytes，SHA256 `230755de2f641b6adcf790bb5c1ad59e6b1789b57c61df8b40d8b0ce5c90904a`；
  核对为 0 条剩余 include、0 个绝对路径。
- 真实 Abaqus 2026 Data Check：`job=diverse_28_flat_dc`，8 CPU，返回码 0，
  `THE ANALYSIS HAS COMPLETED SUCCESSFULLY` / `Abaqus JOB ... COMPLETED`。
  warnings 与模型原有接触/厚度诊断同类；本次只验证独立文件可被输入处理器读取，
  没有重新 solve，也不新增科学质量结论。
