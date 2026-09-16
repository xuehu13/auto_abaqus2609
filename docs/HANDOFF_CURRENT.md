# 当前交接状态 — Pre-M4 / 30曲面阶段性验证

更新时间：2026-09-16
项目：auto_abaqus2609
branch：main
基准 HEAD：last reviewed checkpoint = 22e1a598a47e2ceed977123dc2b49dcd11b3314a（`docs: localize project documentation and record 30-case validation`）；实际当前 HEAD 以 `git rev-parse HEAD` 为准（避免每次 docs commit 立即过期）
Pre-M4 consolidation 完成 commit：852f2765ca987c0360d8e7bcca6ee409e450dab4

本文是快速接管摘要，**不替代** AGENTS/ROADMAP/PROJECT_STATUS/IMPLEMENTATION_STATUS/IMPLEMENTATION_PLAN/LOCAL_ENVIRONMENT。

## 1. 项目真正目标

本项目**不是**机械复现 Diffusion Metamaterials 论文。长期目标是科研平台：

```
surface/equation → automatic periodic mesh → mesh QA → Abaqus physical model
→ Physical Data Check → Solve → ODB extraction → mechanics QA
→ standardized research results → batch / parameter study / ML dataset
```

Fig.1、论文参数、手工模型只是当前 validation baseline/profile。材料、压缩率、接触、输出、时间、后处理等科研参数**不得**因为当前 baseline 而变成长期 hardcode（AGENTS.md 已有此规则）。

## 2. 新会话阅读顺序

1. `AGENTS.md`
2. `docs/HANDOFF_CURRENT.md`（本文件，摘要）
3. `docs/PROJECT_ROADMAP.md`
4. `docs/PROJECT_STATUS.md`
5. `docs/LOCAL_ENVIRONMENT.md`
6. `docs/IMPLEMENTATION_PLAN.md`
7. `docs/IMPLEMENTATION_STATUS.md`

摘要与 **current Git state、PROJECT_ROADMAP、用户明确的新指令** 冲突时，以后三者为准。

## 3. 当前阶段

| 里程碑 | 状态 |
|---|---|
| M1-1..M1-7 physical INP writer | DONE（2026-09-15） |
| M2 Physical Data Check | **DONE（2026-09-15，COMPLETED_WITH_WARNINGS：Fig.1 自动 physical.inp 通过真实 Abaqus 2026 Data Check，0 error / 10 warnings 保留）** |
| M3 solve（single case, 20% Fig.1） | **DONE（2026-09-15，COMPLETED_WITH_WARNINGS：真实 Abaqus/Standard 求解完成，target step time 达标，完整 ODB）** |
| M3.1 solve hardening | DONE（2026-09-15：completion marker gate、job-specific stdout token、non-empty ODB gate、execution.wall_time_s） |
| Pre-M4 consolidation | **DONE（2026-09-15，commit 852f276：run.py Pixi-only 守卫、docs 整合、README 重写、测试包装、CPU8 实验记录）** |
| 30曲面 Phase A（mesh→build→Data Check） | **DONE（2026-09-15/16，local experiment）：30 进入 / 28 mesh PASS / 28 build PASS / 28 Data Check accepted / 0 Data Check failed** |
| 30曲面 Phase B（solve） | **0 完成：ref30_02 人工终止（停滞 ≈0.312）、ref30_03 TOO MANY ATTEMPTS（≈0.39）、ref30_04 人工终止（停滞 ≈0.532）、ref30_05 被 Windows Update 强制重启中断（≈0.979）。0 个有效 ODB。** |
| M4 ODB extraction / mechanics QA | NOT STARTED |

30曲面实验详情与失败分类：`docs/EXPERIMENT_30_SURFACES_20260915.md`、
`docs/TROUBLESHOOTING.md`。该实验使用临时 local batch runner
（`work/night_batch_30surfaces_20260915/run_batch.py`），**不是正式 production
pipeline 的一部分**；其 double-reserve/BOM 问题均为 local runner bug，正式代码已
审计确认无同类问题（`reserve_directory` 单次调用 + `utf-8-sig` 读取 + OUTPUT_EXISTS
测试锁定）。attempt 不覆盖原则未破坏；ref30_05 partial ODB 不作为成功结果。

## 4. 当前 physical builder 产物

`pixi run cli build-physical --npz ... --report ... --pairs ... [--outputs ...] --out work/<新attempt>` 生成：

```
ingredients/        （shell_mesh.inc / lateral_pbc.inc / pbc_map.json / model_inputs.json）
blocks/             （material_section / rigid_platens / boundary_conditions / contact /
                      step_loading / outputs / step_end .inc）
physical.inp        （顶层 deck，仅 9 条固定顺序 *Include，相对路径，原子发布）
build_report.json   （13 项 static checks 逐项 PASS/FAILED + include SHA256）
model_manifest.json （status=PHYSICAL_INP_STATIC_VALIDATED，dataset_eligible=false）
```

固定装配顺序：shell_mesh → material_section → rigid_platens → lateral_pbc → boundary_conditions → contact → step_loading → outputs → step_end。static validation PASS **只证明仓库级内部自洽**（artifact SHA、include 图、label/引用契约、region 存在性、PBC 引用、boundary/loading 契约、step 结构、target/time 一致性）；**不证明 Abaqus 接受该 deck**。M2 用 Abaqus Physical Data Check 验证完整 INP。真实 Fig.1 smoke：`work/fig1_build_m17_smoke_001`（13/13 checks PASS，static_validation=PASS，abaqus_datacheck=NOT_RUN，dataset_eligible=false）。

## 5. 四个独立配置域

| config | 职责 |
|---|---|
| `config/physics.example.json` | boundary/contact/platens/加载目标/时间（schema_version 2） |
| `config/materials/demo_surrogate.json` | 材料本构（demo surrogate，非生产材料） |
| `config/numerics.example.json` | procedure/increments/stabilization/initial_acceleration policy（schema_version 2） |
| `config/outputs.example.json` | restart/field/history 输出策略（schema_version 1） |

上游结构输入：case/mesh（`config/cases/fig1.json` + mesh bundle NPZ/report/pairs）。
**`config/outputs.example.json` 是 Fig.1 baseline output profile，不是长期唯一科研 output**；新 profile = 新 JSON 文件。

## 6. M1-6 最终 output semantics（最终裁决，勿再重释）

```
Restart: disabled → *Restart, write, frequency=0

Field Group 1: PRESELECT, frequency=50

History Group 1: frequency=1
├ *Energy Output: ALLAE ALLIE ALLKE ALLPD ALLWK ETOTAL
├ *Node Output, nset=RP_TOP:    RF3 U3
├ *Node Output, nset=RP_X_CTRL: U1
└ *Node Output, nset=RP_Y_CTRL: U2

History Group 2: PRESELECT, frequency=10
```

关键证据：hand baseline Group 2 **省略 FREQUENCY**；Abaqus/Standard direct-INP Dynamic 下省略默认 = **每 10 个 increments**；automatic writer 显式写 `frequency=10` 冻结该 effective semantics（有意文本差异）。
**不要再写 omitted frequency = 1**；也不要用 Group 1 显式变量的 60 点数据去论证 Group 2 采样（循环论证——60 点由 Group 1 自己的 frequency=1 解释）。PRESELECT-only 变量（ALLSE/ALLEE/ALLVD/ALLJD 等）在 baseline ODB inventory 中存在，但其采样密度从未导出 → M2 复核。

## 7. Output 四层架构

```
Layer 1 Abaqus Output Policy   ODB/restart 写什么        ← M1-6 只负责这一层
Layer 2 Extraction Policy      从 ODB 提取什么           ← ODB extraction 阶段
Layer 3 Dataset / ML Export    场快照/变换/训练集打包     ← dataset 阶段
Layer 4 Visualization Policy   曲线/云图/动画/论文图      ← postprocess 阶段
```

以后增加 S/U/PEEQ/LE/CPRESS/COPEN/CSLIP/SDV 等输出：**扩 outputs config 的 request kind/变量即可，不得要求推翻 builder schema**（kind=node/energy 已支持；element/contact 在 schema 中预留、渲染 NOT_IMPLEMENTED）。

## 8. 关键模型 invariants

- 当前 supported policy：single cell `[1,1,1]`；XY lateral PBC only；**无隐藏 Z-PBC**。
- `RP_X_CTRL`：PBC 宏观 U1 控制节点，**不得 Boundary 固定 U1**；`RP_Y_CTRL`：宏观 U2，同上；二者不属于任何 rigid body。
- `RP_BOTTOM`：DOF1..6 = 0（全固定）；`RP_TOP`：DOF1,2,4,5,6 model-level guide，DOF3 = in-step compression。
- target U3 单一真值：`manifest["target_displacement_mm"] = -target_compression_strain × L`（prepare_fe 生成，renderer 不重算）。
- Step 内**不重申** guide DOFs（`step_reapplies_guide_dofs=false`）：依赖 Abaqus history `*Boundary` 默认 OP=MOD。
- 标签契约：RP/plate labels 一律读 `manifest["labels"]`，禁止手算/硬编码（Fig.1 参考值：rp_x=9484、rp_y=9485、rp_bottom=9486、rp_top=9487、first_plate_node=9488）。
- 冻结 vendor mesher；全部 block 确定性渲染。

## 9. 已验证 / 未验证边界

**已验证**：Python/Pixi 逻辑（142/142 core + 8/8 Pixi boundary，2026-09-16）；真实 Fig.1 mesh bundle smoke；block 确定性渲染；M1-7 physical.inp 确定性装配 + 13 项仓库静态检查；config 隔离；hand-INP 语义逐项对比；**M2：Fig.1 自动 physical.inp 通过真实 Abaqus 2026 Physical Data Check（returncode=0、0 error、10 warnings 保留、`ANALYSIS DATACHECK COMPLETE`，`work/fig1_datacheck_m2_final_001`）**。

**尚未验证**：30% 压缩收敛；接触在加载全过程中的物理正确性（含 10 条 M2 warning 对应的初始化调整与双侧面歧义）；PBC 大变形行为；准静态科学有效性（`quasi_static_status=pending_qa`）；自动模型 requested-output 的真实 ODB 行为；production dataset eligibility。

**`dataset_eligible=false`（builder 硬性保证）。**

## 10. hand/manual baseline 注意

- 手工成功压缩：**20%**（U3=−2mm，L=10）；当前 writer config 目标：**30%**（U3=−3mm）。
- 当前 smoke U3=−3mm **不是 writer bug**，是 config 目标本身的体现；手工模型当前角色 = **keyword 语义 baseline**，不声称自动模型已复现 20% solve。

## 11. 当前重要技术债

1. Shell Section Simpson 积分点 = 5：baseline-fixed，出现第二种 section policy 再 config 化。
2. identity 混合语义：`model_key`=物理模型身份 / `scaffold_key`=pre-output build-input+provenance / `build_key`=build provenance + rendered block identity（M1-7 未把 physical.inp/build_report SHA 并入 build_key，只作为独立 manifest metadata）；batch/cache 阶段统一。`numerics.example.json` 同时含 step numerics 与 cpus/retry/wall limit 且整体进入 scaffold identity，长期需拆分（本次未改）。
3. explicit output-disable policy（field-only/history-only/zero-field）：未实现；空 group → NOT_IMPLEMENTED，禁止依赖 Abaqus implicit default。
4. PRESELECT-only 自动 ODB 采样：仅 keyword semantics reproduced，M2 后用真实自动模型 ODB 复核。
5. restart ownership：当前属 outputs 写盘策略；runtime/recovery 成熟后再评估迁移。
6. demo material：non-production surrogate，不是论文真实材料。
7. ~~Physical Data Check 尚未执行~~ **已执行并通过**（2026-09-15，Fig.1，COMPLETED_WITH_WARNINGS）；static validator 是面向本项目确定性关键词形式的小型解析器，不是通用 Abaqus INP parser。
8. **Solve timeout 债务（M3.1 登记，deferred to M7 reliability）**：`subprocess.TimeoutExpired` 触发时 attempt 可能缺少 command.json/solve_report.json 等结构化证据，且只 kill launcher 层进程，SMALauncher/standard.exe 等子进程树可能残留，需要 reconciliation。watchdog/kill-tree/retry/resume 均属 M7。
其余债务见 `docs/IMPLEMENTATION_PLAN.md` 技术债段与 `docs/PROJECT_STATUS.md` 差异清单（引用，不复述）。

## 12. Local evidence（不进 Git）

`work/` 与 `reference/` 均为 Git-ignored local-only，新机器 clone 后**可能不存在**：
- `work/fig1_solve_m3_20pct_003/`（M3 真实 20% solve：SOLVE_COMPLETED_WITH_WARNINGS，returncode=0，0 error/17 warning，完整 ODB 16,075,836 bytes）
- `work/fig1_solve_cpu8_validation_001/`（CPU8 单变量实验：完成但更慢 32m51s vs 16m33s；本机 preferred 保持 cpus=4）
- `docs/TROUBLESHOOTING.md`（失败/诊断历史索引；10-attempt M2 诊断链摘要见 `work/fig1_datacheck_m2_diagnostics_summary.json`）
- `work/fig1_datacheck_m2_final_001/`（M2 正式 CLI 验证：DATACHECK_COMPLETED_WITH_WARNINGS，returncode=0，0 error/10 warning，execution_policy=cpus=1 solver via local_environment）
- `work/fig1_datacheck_m2_diagnostics_summary.json`（M1 环境解堵 10-attempt 诊断链：standard_parallel=all 的可复现 pre 失败与 solver-mode 绕过）
- `work/fig1_build_m17_smoke_001/`（M1-7 真实 Fig.1 build smoke：physical.inp + build_report.json，13/13 checks PASS）
- `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.inp`（hand keyword 语义 baseline）
- 同目录 `.dat/.msg/.sta/.log/.odb`（接触/求解证据）
- `physical_regions.json` / `physical_raw_history.json`（20% ODB 提取实证）
- 各 M1 smoke attempts（`work/fig1_build_*`）

## 13. Conversation / reference archive policy

本次 M1-6 开发对话**不另行保存为 reference PDF**。

未来接管不得依赖旧 ChatGPT / GLM 对话记录；当前工程状态的正式真值顺序是：

1. current Git state / source / tests
2. `AGENTS.md`
3. `docs/HANDOFF_CURRENT.md`
4. ROADMAP / PROJECT_STATUS / IMPLEMENTATION_PLAN / IMPLEMENTATION_STATUS
5. 用户明确的新指令

`reference/` 仍然是 Git-ignored local evidence 区；以后只有用户明确需要时才新增独立参考资料。其内容不是仓库真值，也不能成为新机器 clone 后继续开发的必要依赖。

## 14. M2 最终结果与 Runtime portability

### 14.1 M2 result

**Fig.1 自动 `physical.inp` 已被真实 Abaqus 2026 Physical Data Check 接受。** 正式 CLI 验证：`pixi run cli datacheck --build-dir work/fig1_build_m2... `（实际命令见 `work/fig1_datacheck_m2_final_001/command.json`）：

```
return code = 0
ANALYSIS DATACHECK COMPLETE
errors = 0
warnings = 10（全部保留，未白名单）
status = DATACHECK_COMPLETED_WITH_WARNINGS
solve = NOT_RUN / odb_results_qa = NOT_RUN / dataset_eligible = false
```

10 条 warning（1× General Contact double-sided facets、1× STRAINFREE adjustment ratio 2.55e-2 @ node 544、8× ADJACENT SECONDARY NODES opposite sides of double-sided main surface）与手工 20% baseline 作业的诊断签名一致，**不是自动化回归**，但绝不等于"无害/已验证安全"——作为 QA obligation 移交 M3/M4 接触与力学检查。

### 14.2 Runtime portability / machine execution profile（重要）

1. **模型与运行策略分离**：`physical.inp` 是 machine-independent model artifact；launcher/cpus/standard_parallel 是 machine-specific execution settings，只出现在命令行与 datacheck provenance/report 中，永不进入 `physical.inp`，也永不改变 `model_key/scaffold_key/build_key`。
2. **当前开发机事实**：Abaqus 2026，Intel i7-13650HX（14 physical / 20 logical，Abaqus 按 14 CPU 计）。观察：`standard_parallel=all`（默认）在 General Contact preprocessing（`pre|Elem|ElemC|Econtp|ConnectivityAtNodes`）中**可复现**触发 `***ERROR: EXCEEDED THE MAXIMUM AMOUNT OF THREADS TO BE USED PER DOMAIN (<=100)`（手工 baseline INP 同样失败，与 M1 writer 无关）；`standard_parallel=solver` 使同一 deck 完整通过 Data Check。这是 reproducible machine/runtime-specific failure 的实验描述，**不是**对 Abaqus 内部缺陷的源码级证明。完整 10-attempt 诊断链见 `work/fig1_datacheck_m2_diagnostics_summary.json`。
3. **不应泛化**：其他机器不要自动假设必须 `standard_parallel=solver`——若真实验证 `standard_parallel=all` 正常，即可使用（在 `config/datacheck_runtime.local.json` 中设置）。
4. **当前 safe Data Check profile**：`cpus=1, standard_parallel=solver`（保守默认，已作为代码内置 safe default；机器可用 `config/datacheck_runtime.local.json` 覆盖，CLI `--cpus/--standard-parallel` 优先级最高）。解析顺序：CLI → local file → safe default；来源记录在 report 的 `execution_policy.source`（`cli` / `local_environment` / `safe_default`）。
5. **M3 Solve execution policy：已在本机与 20% validation case 上真实验证成功**（`cpus=4, standard_parallel=solver`，`work/fig1_solve_m3_20pct_003`）。This is validated for this machine and this validation case only; it is not a universal or performance-optimal profile for all machines/cases. Safe conservative fallback（`cpus=1, standard_parallel=solver`）保留。
6. **Machine capability probe（Abaqus release/CPU/parallel modes/小型 datacheck 能力缓存）**：NOT IMPLEMENTED，未来需要时再设计。
7. **HIGH-PRIORITY DEFERRED PERFORMANCE DEBT（standard_parallel=all）**：本机 `standard_parallel=all` 在 General Contact preprocessing 可复现触发 threads-per-domain ERROR（见 TROUBLESHOOTING）；当前 workaround `standard_parallel=solver` 可能牺牲 preprocessing 并行性能。后续优先测试：`cpus=8, threads_per_mpi_process=8, standard_parallel=all`（先 Data Check），候选矩阵 `8/automatic/all`、`8/8/all`、`4/4/all`、`8/4/all`、`8/2/all`、`8/1/all`。任何组合未经验证不得用于正式 solve。详见 `docs/TROUBLESHOOTING.md` 对应条目。

## 15. M3 result 与下一步

**M3 = DONE（COMPLETED_WITH_WARNINGS，20% validation case）。** 链路：同一真实 Fig.1 mesh bundle + local 20% physics config（唯一差异 `target_compression_strain 0.3→0.2`）→ `build-physical`（`work/fig1_build_m3_20pct_001`，PHYSICAL_INP_STATIC_VALIDATED，target U3=-2.0mm）→ `datacheck`（`work/fig1_datacheck_m3_20pct_001`，0 error/10 warnings）→ `solve`（`work/fig1_solve_m3_20pct_003`）。

真实 Solve 结果（`solve_report.json`）：returncode=0、`Abaqus JOB fig1_m3_solve COMPLETED`、`.sta: THE ANALYSIS HAS COMPLETED SUCCESSFULLY`、last_step=1/last_increment=59/last_step_time=1.00=target、0 fatal error、17 warnings、完整 ODB 16,075,836 bytes。execution policy：`cpus=4, standard_parallel=solver`（local solve_runtime 配置，本机候选 profile）。M3.1 hardening 后 report 亦含 `execution.wall_time_s`（`time.monotonic()` 实测 subprocess 时长）。

**Warning 语义（M3.1 澄清，勿混淆）**：solve 的 17 条 warning 中——10 条是 M2 Data Check 同一批 preprocessing warnings 在 solve `.dat` 中的**原样重现（signature-identical）**；7 条是 solve-only 的 `.msg` zero-moment warnings（`THERE IS ZERO MOMENT EVERYWHERE ...`）。`source_datacheck.warning_count=10` 是 provenance 继承记录，**不加进** solve 的 warning_count。全部未白名单。

**Timing 事实（非性能基准）**：attempt 001 ≈25m07s（物理完成，被 .sta parser bug 误判 FAIL，bug 已修复并有真实格式回归测试）；attempt 002 ≈5m40s（误触发的重复运行，手动终止，仅保留为证据）；attempt 003 ≈16m33s（正式 accepted M3 solve）。用户体感"约1小时" = 001 完整求解 + 002 部分求解 + 003 完整求解 + parser 诊断/修复 + 测试 + 轮询等待。不同非线性 solve 即使同模型也可能有 wall-time 波动，16m33s/25m07s 不是稳定性能基准。

**Scope**：M3 只证明自动提交+完成判定+ODB artifact 产出；未读取 ODB、未提取曲线、未做准静态/接触/PBC 科学判断。ODB 尚未由 odbAccess 打开或验证。M2 的 10 条 warning 与 solve 的 17 条 warning 是 M4 mechanics/contact QA 的强制输入。

**下一步 = M4 ODB 自动提取与 raw result integrity**：对已成功的 Fig.1 20% solve ODB 用 Abaqus Python/odbAccess 自动提取 history/field/metadata 并验证 raw result 完整性。30% compression 是 20% extraction+QA 链路稳定之后的**新 validation target**，不是 M4 第一步。

## 16. 下一阶段明确禁止

```
Do NOT:
- batch 20000 cases yet
- implement concurrency
- implement retry/recovery
- implement UMAT
- implement n×n×n
- change frozen vendor mesher
- run M3 solve without first validating its execution profile
- silently modify physics for convergence
- whitelist the 10 M2 warnings without real mechanics QA
```
