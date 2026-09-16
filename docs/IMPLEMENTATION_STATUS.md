# v0.1 实施状态与后续接口

## M1/M2/M3 进度（M1 checkpoint 2026-09-15 → BUILD complete；M2 checkpoint 2026-09-15 → COMPLETED_WITH_WARNINGS；M3 checkpoint 2026-09-15 → **M3 DONE, COMPLETED_WITH_WARNINGS**；Pre-M4 consolidation checkpoint 2026-09-15 → DONE；30曲面阶段性验证 2026-09-15/16 → Phase A DONE / Phase B 0 完成）

### Pre-M4 consolidation与30曲面阶段性验证（2026-09-15/16）

- **Pre-M4 consolidation DONE**（commit 852f276）：`run.py` Pixi-only 守卫强化、
  README/docs 整合重写、测试包装梳理、CPU8 实验记录入档。
- **30曲面阶段性验证（local experiment）**：30 个差异曲面进入自动化链；
  **28/30 mesh PASS、28/28 build PASS、28/28 Data Check accepted（0 failed）**；
  4 个 solve 尝试（ref30_02/03/04/05）全部未完成、**0 个有效 ODB**（02/04 收敛
  停滞人工终止、03 TOO MANY ATTEMPTS、05 被 Windows Update 强制重启中断于
  ≈0.979）。证明 mesh → build → Data Check 初步泛化；batch/recovery framework
  与 solve 收敛性研究仍属后续里程碑。实验记录：`docs/EXPERIMENT_30_SURFACES_20260915.md`。
- 使用临时 local batch runner（非正式 pipeline）；其 double-reserve/BOM bug 不涉及
  正式代码（正式代码 2026-09-16 审计确认无同类问题）。attempt 不覆盖原则未破坏；
  ref30_05 partial ODB 不作为成功结果。
- 登记新债务：`standard_parallel=all` HIGH-PRIORITY DEFERRED PERFORMANCE DEBT
  （`docs/IMPLEMENTATION_PLAN.md` / `docs/TROUBLESHOOTING.md`）。
- 文档语言整理：面向人的文档中文化（README/TROUBLESHOOTING 等），技术术语与
  状态枚举保留英文；历史资料全部保留并加注状态标记。

### M1-1 已完成：physical builder scaffold
- `pipeline/physical_builder.py` 与 `run.py build-physical` CLI（Pixi default 守卫不变，现有命令语义未改）。
- 新 attempt 内生成 `ingredients/`（完全复用现有 `prepare-fe` 产物）与 `model_manifest.json`；拒绝覆盖。
- numerics 契约校验：参数非法 → `CONFIG_INVALID`；合法但本版未支持 → `NOT_IMPLEMENTED`。
- 无 physical.inp；无 Abaqus 验证；`dataset_eligible=false`。

### M1-2 已完成：material/section block
- `blocks/material_section.inc`：Material/Density/Elastic/Plastic + Shell Section（homogeneous，Simpson + 5 个厚度积分点——当前 builder baseline，不是固定科研参数）。
- 语法基准为已验证手工模型 Fig1_Compression.inp 的对应块；数值全部来自 prepare_fe 验证过的配置，厚度继承 `model_inputs.json`，不重算。
- 确定性渲染：相同输入跨 attempt 字节一致，SHA256 记录于 manifest 的 `blocks.material_section`。
- `status=PHYSICAL_BUILD_PARTIAL`；`scaffold_key` 保留、`build_key` 新增；仍无 Abaqus 验证。

### M1-3a 已完成：rigid platens / control nodes / rigid body
- `blocks/rigid_platens.inc`：RP_X_CTRL / RP_Y_CTRL 两个 PBC macro control nodes、RP_BOTTOM / RP_TOP 两个 rigid-body reference nodes、deterministic bottom/top rigid platen 网格（R3D4，配置驱动：W=width_factor×L，中心 (L/2,L/2)，z=0/L）与两条 `*Rigid Body` 定义。
- 标签契约：禁止手算/硬编码 RP label，一律读取 `model_manifest/model_inputs["labels"]`（Fig.1 实际值：rp_x=9484、rp_y=9485、rp_bottom=9486、rp_top=9487、first_plate_node=9488，由 prepare_fe 按节点数推导）；标签安全审计（两两不同、与 shell/plate 范围无碰撞）内置于渲染前。
- `normal_policy = baseline_shared_connectivity_plus_z_both`（忠实复现手工模型"一个 RigidPlate part 两次平移 instance"的语义：bottom/top 共享同一局部 connectivity，均 +Z 法向）；
  `normal_policy_status = baseline_reproduction_pending_contact_validation`——SPOS/SNEG、ALL EXTERIOR、General Contact 对刚板的实际 side/domain、初始接触/穿透、以及是否建立 top −Z candidate profile，全部留待 M1-4 Contact 阶段专项验证；不宣称 +Z/+Z 是最优接触设置。
- RP_X_CTRL DOF1 与 RP_Y_CTRL DOF2 被 lateral PBC equations 作为宏观横向控制自由度使用，**不应被 Boundary 固定**；RP_X/RP_Y 其他 DOF 的处理尚未确定，M1-3b 必须先从成功手工 Fig1_Compression.inp 提取完整 `*Boundary` 证据后再决定。
- 本阶段无 Boundary / Contact / Step / Loading / Output 关键字；无 physical.inp；无 Abaqus 验证；`dataset_eligible=false`。

### M1-3b 已完成：Boundary Conditions
- `blocks/boundary_conditions.inc`：RP_BOTTOM DOF1..6 = 0（BC_BOTTOM_FIXED 语义）；RP_TOP DOF1,2,4,5,6 = 0（BC_TOP_GUIDE 语义）；RP_TOP DOF3 保留给 Step/Loading（非零 U3 属未来里程碑，block 内不存在）。
- RP_X_CTRL / RP_Y_CTRL 无任何 Boundary（手工 baseline 证据：其 DOF1/DOF2 被 lateral PBC equations 用作宏观横向控制自由度）；整块零出现有测试保证。
- 渲染与 loading 参数完全解耦：`target_compression_strain 0.30→0.20` 时 block 字节不变（有测试）；无 AMPLITUDE/OP/TYPE/非零 magnitude。
- `status=PHYSICAL_BUILD_PARTIAL`；`dataset_eligible=false`；无 physical.inp；无 Abaqus 验证。`build_key` 已包含三个 block SHA。
- 备注（非本阶段任务）：手工 Compression Step 内以 `*Boundary, amplitude=AMP_COMPRESSION` 重申 RP_TOP guide 并施加 U3=−2；Abaqus 默认 OP=MOD，model 级 zero guide 持续有效，未来 Step/Loading 里程碑可自行决定仅加 U3 或完整重申。

### M1-4 已完成：Contact
- `blocks/contact.inc`：`*Surface Interaction, name=ContactProp` + `*Friction, slip tolerance=<config>` + `<friction>` + `*Surface Behavior, pressure-overclosure=HARD` + `*Contact`（无 OP）+ `*Contact Inclusions, ALL EXTERIOR`（无数据行）+ 全局 `*Contact Property Assignment` → ` , , ContactProp`。
- General Contact / ALL EXTERIOR 是当前 v0.1 supported policy（hand-baseline 复现），不是长期唯一 contact strategy；friction、slip_tolerance 由 config 驱动，产品代码无科研数值硬编码。
- 手工 baseline 的 `*Surface Interaction` optional scalar 行（`1.,`，仅适用 2D/node-based pair）**有意省略**（本模型为 3D element-based），省略原因写入 block 注释并有结构化测试锁定。
- 无显式 `*Surface`、无 Contact Initialization/Controls keywords；`allow_separation=true` 通过省略 NO SEPARATION 表达；`tangential=penalty` 依赖 Standard 默认 penalty 语义（`tangential_policy=penalty_default`）。
- `normal_policy_status` 演进为 `baseline_contact_definition_reproduced_pending_datacheck`（writer 已复现 baseline 接触定义，真实初始化待 M2 Abaqus Data Check；不声称 contact validated）。
- `status=PHYSICAL_BUILD_PARTIAL`；`dataset_eligible=false`；无 physical.inp；无 Abaqus 验证；`build_key` 已包含四个 block SHA。

### M1-5 已完成：Step + Loading
- `blocks/step_loading.inc`：`*Amplitude, name=AMP_COMPRESSION, definition=SMOOTH STEP`（数据 `(0,0,T,1)`，T=physics.time_period_s，相对幅值 0→1 跨整个步程）+ `*Step, name=Compression, nlgeom=YES, inc=<maximum_increments>` + 事实性 subheading（不含 quasi-static 声明）+ `*Dynamic, application=MODERATE DISSIPATION, initial=NO`（INITIAL=NO 经 numerics policy `initial_acceleration_policy="bypass"` 表达）+ in-step loading 仅 `RP_TOP, 3, 3, <target_displacement_mm>`（单一真值继承自 manifest，不重算；OP=MOD 下 model 级 guide 持续有效，不重申 guide DOFs）。
- `blocks/step_end.inc`：`*End Step`（所有权归 M1-5，M1-7 仅按序拼接）。
- `automatic_stabilization=true` → NOT_IMPLEMENTED（attempt 创建前失败）；amplitude 非 smooth_step → NOT_IMPLEMENTED。
- `quasi_static_status=pending_qa`：Dynamic Implicit + Smooth Step 不构成准静态证明，判定留给 QA（ALLKE/ALLIE、曲线振荡、能量平衡）。
- `status=PHYSICAL_BUILD_PARTIAL`；`dataset_eligible=false`；无 outputs.inc；无 physical.inp；无 Abaqus 验证；`build_key` 已包含六个 block SHA。

### M1-6 已完成：Output Requests
- 新增 `config/outputs.example.json`（schema_version 1，profile_id=`fig1_baseline_outputs_v1`，output policy 独立 config，Fig.1 输出只是 baseline profile）与 CLI `--outputs`（默认该文件）。
- `blocks/outputs.inc`：`*Restart, write, frequency=0`（restart disabled）+ **1 个 Field group**（PRESELECT frequency=50）+ **2 个 History groups**——Group 1（frequency=1：Energy ALLAE/ALLIE/ALLKE/ALLPD/ALLWK/ETOTAL + RP_TOP RF3/U3 + RP_X_CTRL U1 + RP_Y_CTRL U2）、Group 2（PRESELECT，**显式 frequency=10**）。
- Group 2 的 frequency=10 = hand baseline 省略 frequency → Abaqus/Standard Dynamic direct-INP documented effective default → automatic writer 显式冻结该有效语义（有意文本差异；官方语义由 Evidence Review 确认）。
- group-oriented schema：PRESELECT 是 group-level mode；field explicit / element / contact / integrated v1 → NOT_IMPLEMENTED；空 `field_groups`/`history_groups` 不得静默依赖 Abaqus default output → NOT_IMPLEMENTED（explicit requests=[] → CONFIG_INVALID）；未知变量不拒绝（M2 验证）；region 存在性 → M1-7。
- `_load_outputs` 在 attempt 创建前校验；manifest 记录 parsed outputs snapshot + `outputs_config_sha256`（provenance）+ required_regions/requested_variables（未来 extraction hints）。
- identity 术语：`model_key`=物理模型身份；`scaffold_key`=当前 pre-output build-input/provenance 身份；`build_key`=build provenance + rendered block identity。outputs 的 config SHA 仅 provenance、block SHA 进 build_key；identity 统一分层留待 batch/cache 阶段（非阻塞债务）。
- `status=PHYSICAL_BUILD_PARTIAL`；`dataset_eligible=false`；无 physical.inp；无 Abaqus 验证；`build_key` 含七个 block SHA。

### M1-7 已完成（2026-09-15）：physical.inp assembly + static validation
- `pipeline/physical_builder.py` 新增 `_assemble_physical_inp` / `_validate_static_model` / `_run_static_stage`：顶层 `physical.inp` 只含 9 条固定顺序 `*Include`（shell_mesh → material_section → rigid_platens → lateral_pbc → boundary_conditions → contact → step_loading → outputs → step_end），全部为 attempt 内相对路径（禁止盘符/绝对/`..`），`atomic_text` 原子发布。
- 13 项 repository-owned static checks：`artifact_integrity`（文件存在 + manifest block SHA256 对盘）、`include_graph`（顺序/重复/安全路径/目标存在）、`label_uniqueness`（node/element 定义重复 + manifest RP label/range 契约）、`node_reference_integrity`（nset/equation/rigid-body 引用）、`element_reference_integrity`（connectivity/elset 引用）、`region_integrity`（SHELL_ALL/PLATE_*/RP_* + `required_regions` 存在且非空）、`pbc_reference_integrity`（pbc_map 计数对 manifest、mode=lateral_xy、无隐藏 Z、macro DOF 契约、dependent node 引用）、`boundary_contract`（RP_BOTTOM 1-6 / RP_TOP 1,2,4,5,6 / macro RP 零 Boundary / step 内唯一 `*Boundary, amplitude=AMP_COMPRESSION` = RP_TOP U3）、`step_pairing`、`step_order`（Step < outputs/Dynamic/boundary < End Step，amplitude 在 Step 外）、`target_consistency`（`-strain×L` 对 manifest 对 step 渲染值，只检查不覆盖）、`time_amplitude_consistency`（amplitude 端点 = `*Dynamic` 总时 = physics.time_period_s）、`output_region_integrity`（渲染 region == manifest required_regions 且已定义）。
- 解析器为只针对本项目确定性关键词形式的小型 line-oriented helper，不是通用 Abaqus INP parser。
- 失败路径：attempt 保留全部证据；`build_report.json` 写 `STATIC_VALIDATION_FAILED` + `failed_checks`；manifest 写 `PHYSICAL_INP_STATIC_VALIDATION_FAILED`；抛 `PipelineError("STATIC_VALIDATION_FAILED")`；不把 manifest 标成功。
- 成功路径：`build_report.json`（status=STATIC_VALIDATION_PASSED，static_validation=PASS，abaqus_datacheck/solve/odb_qa=NOT_RUN，dataset_eligible=false，逐 check PASS/FAILED + includes/physical_inp SHA256）；manifest 更新 `status=PHYSICAL_INP_STATIC_VALIDATED`，`missing_stages` 仅剩 physical datacheck/solve/ODB QA，新增 `physical_inp`/`build_report` artifact metadata；`build_key` 语义未改（identity debt 保留）。
- 测试：新增 21 个 M1-7 回归测试（`PhysicalInpAssemblyTests`）；`_render_outputs` 对不存在 region（TEST_SET）仍只渲染不检查存在性（renderer 职责不变），final `build_physical` 则必须 STATIC_VALIDATION_FAILED（有测试）。`pixi run test`：94/94 core + 8/8 Pixi boundary。
- 真实 Fig.1 smoke：`work/fig1_build_m17_smoke_001`（npz/report/pairs 指纹与 M1-6 smoke manifest 一致）→ 13/13 checks PASS，`static_validation=PASS`，`abaqus_datacheck=NOT_RUN`，`dataset_eligible=false`。
- **Abaqus 未被调用**：static validation PASS ≠ Abaqus keyword parser 接受 ≠ Data Check 通过 ≠ 可求解。

### M2 已完成（2026-09-15，COMPLETED_WITH_WARNINGS）：Physical Data Check
- 新增 `pipeline/physical_datacheck.py`（窄职责）：source build 校验（status=PHYSICAL_INP_STATIC_VALIDATED、static_validation=PASS、physical.inp SHA 对 manifest）→ attempt 内 SHA 双向校验 staging（physical.inp + 9 includes + source manifest/report provenance）→ launcher resolution（CLI --abaqus-command → environment.local.json abaqus_launcher → PATH abaqus → PATH abq2026；不可解析 → ABAQUS_LAUNCHER_NOT_FOUND）→ **execution policy 解析（CLI `--cpus/--standard-parallel` → `config/datacheck_runtime.local.json`（`*.local.json` 已 git-ignore）→ safe default `cpus=1, standard_parallel=solver`；非法值 → CONFIG_INVALID；来源记录为 cli/local_environment/safe_default）** → `abaqus job=<验证过的名称> input=physical.inp datacheck interactive cpus=<n> standard_parallel=<mode>`（cwd=attempt；命令恒含 datacheck，绝不含 analysis/continue）→ 保留全部生成文件（.dat/.msg/.odb/.prt/.mdl/.stt/.sim/.cax/.com/.env/.exception 等；required = .dat + .odb + stdout 捕获，.msg/.log/.exception optional——Abaqus 2026 datacheck interactive 不生成 .log）→ line-oriented ERROR/WARNING 解析（保留原文+行号+来源+轻量分类，无白名单）→ DATACHECK_PASSED / COMPLETED_WITH_WARNINGS / FAILED 判定 → `datacheck_report.json`（含 execution_policy；claims: solve=NOT_RUN、odb_results_qa=NOT_RUN、dataset_eligible=false 恒定）。
- CLI：`pixi run cli datacheck --build-dir <M1 build> --out <新attempt> [--abaqus-command] [--job-name] [--cpus] [--standard-parallel]`；非 clean pass 退出码 3。
- 测试：新增 21 个 M2 回归测试（mock subprocess/release，不调用真实 Abaqus；覆盖 policy 默认/覆盖/优先级/非法值、required artifacts、三态判定、claims discipline）；总计 **[HISTORICAL] 该 milestone 时点数量：115 core + 8 boundary 全过**（历史数字保留不改；当前 full suite 实测记录见 `docs/PROJECT_STATUS.md` / `docs/HANDOFF_CURRENT.md` 的 maintenance checkpoint）。
- **Runtime portability 原则**：execution policy 是 machine/runtime-local 配置，只进命令行与 datacheck/solve provenance，永不进入 physical.inp 或 model_key/scaffold_key/build_key；同一 physical.inp 可在不同机器用不同 execution profile。**M3 Solve execution policy 已在本机/20% validation case 上真实验证：`cpus=4, standard_parallel=solver`（16m33s）；`cpus=8, solver` 也完成但更慢（32m51s，见 TROUBLESHOOTING）——本机 preferred = cpus=4 + solver；portable safe default 保持 `cpus=1, solver`。**
- **真实 Fig.1 Data Check 最终结果**（正式 CLI，`work/fig1_datacheck_m2_final_001`，physical.inp SHA `AD93E91B…` 与 M1 manifest 一致）：**returncode=0、`ANALYSIS DATACHECK COMPLETE`、0 error、10 warnings**（1× General Contact double-sided facets、1× STRAINFREE adjustment ratio 2.55e-2 @ node 544、8× ADJACENT SECONDARY NODES opposite sides of double-sided main surface——与手工 20% baseline 诊断签名一致）→ `status=DATACHECK_COMPLETED_WITH_WARNINGS`。**M2 = DONE。**
- 开发机 runtime 事实（reproducible machine/runtime-specific failure，谨慎表述）：默认 `standard_parallel=all` 在 General Contact preprocessing 触发 `***ERROR: EXCEEDED THE MAXIMUM AMOUNT OF THREADS TO BE USED PER DOMAIN (<=100)`（手工 baseline 同样失败；cpus/reqcpus/env 变量均排除；10-attempt 诊断链见 `work/fig1_datacheck_m2_diagnostics_summary.json`）；`standard_parallel=solver` 绕过该路径。其他机器不得自动假设需要同样 workaround。

### M3 已完成（2026-09-15，COMPLETED_WITH_WARNINGS）：Single-Job Real Solve
- 新增 `pipeline/physical_solve.py`（窄职责）：accepted M2 datacheck attempt 校验（status ∈ {DATACHECK_PASSED, DATACHECK_COMPLETED_WITH_WARNINGS}、error_count=0、solve=NOT_RUN、dataset_eligible=false、physical.inp SHA 对 datacheck report）→ SHA 双向校验 staging（deck + includes + source datacheck/manifest/build provenance）→ launcher resolution（与 M2 相同优先级）→ **solve runtime policy 解析（CLI `--cpus/--standard-parallel` → `config/solve_runtime.local.json` → safe default `cpus=1, standard_parallel=solver`；非法值 → CONFIG_INVALID）** → stdout/stderr 直接流式写入 attempt 文件（长作业不占内存）→ `abaqus job=<name> input=physical.inp analysis interactive cpus=<n> standard_parallel=<mode>`（无 datacheck/continue/recover）→ 完成判定（returncode + stdout `Abaqus JOB … COMPLETED` + `.sta: THE ANALYSIS HAS COMPLETED SUCCESSFULLY` + fatal 诊断 + required artifacts（.dat/.msg/.sta/.odb）+ **target step time 达标**，绝不只看 return code）→ `.sta` 窄解析器（成功增量行：last_step/last_increment/last_step_time/increment_count；cutback 'U' 行跳过；真实 10 列三时间列格式有回归测试）→ `solve_report.json`（M2 warning 继承 provenance；claims: odb_exists、odb_results_qa=NOT_RUN、mechanics_qa=NOT_RUN、dataset_eligible=false 恒定）。
- CLI：`pixi run cli solve --datacheck-dir <M2 attempt> --out <新attempt> [--abaqus-command] [--job-name] [--cpus] [--standard-parallel]`；非完成状态退出码 3。
- **Runtime portability**：solve runtime policy 与模型完全分离，不进 physical.inp/identity keys；不得自动继承 M2 datacheck profile；M3 性能策略待单独验证。
- 测试：新增 23 个 M3 回归测试（mock subprocess/release；覆盖 source 校验、staging、policy、命令契约、失败证据、三态判定、claims、attempt 保护、真实 .sta 格式回归）；总计 **[HISTORICAL] 该 milestone 时点数量：138 core + 8 boundary 全过**（历史数字保留不改；当前 full suite 实测记录见 maintenance checkpoint）。
- **真实 20% solve 结果**（`work/fig1_solve_m3_20pct_003`，job=fig1_m3_solve，cpus=4 + standard_parallel=solver via local_environment）：**SOLVE_COMPLETED_WITH_WARNINGS**——returncode=0、stdout 完成 token、`.sta: THE ANALYSIS HAS COMPLETED SUCCESSFULLY`、last_step=1/last_increment=59/last_step_time=1.00=目标、0 error、17 warnings、完整 ODB 16,075,836 bytes。20% 目标为 validation profile（local config，唯一差异 strain 0.3→0.2），不是科研硬编码。Timing：001≈25m07s（物理完成，被 .sta parser bug 误判 FAIL，已修复+回归测试）、002≈5m40s（误触发重复运行，手动终止，仅证据）、003≈16m33s（正式 accepted solve）；wall-time 波动属正常，不是性能基准。M3.1 后 report 含 `execution.wall_time_s`（monotonic 实测）。
- **Warning 语义（M3.1 澄清）**：solve 的 17 条 warning = 10 条 M2 datacheck preprocessing warnings 在 solve `.dat` 中的原样重现（signature-identical）+ 7 条 solve-only `.msg` zero-moment warnings；`source_datacheck.warning_count=10` 是 provenance 记录，不加进 solve warning_count。全部未白名单，移交 M4 QA。
- 诊断记录：第一次真实 solve（`work/fig1_solve_m3_20pct_001`）因 **M3 .sta parser bug**（真实 10 列三时间列格式未解析）误判 SOLVE_FAILED，bug 修复 + 回归测试后以新 attempt 003 验证；`work/fig1_solve_m3_20pct_002` 为误触发的重复运行，已终止并保留为证据。
- M3.1 hardening（2026-09-15）：M2 accepted gate 增加 `ANALYSIS DATACHECK COMPLETE` marker 要求（缺失 → DATACHECK_FAILED）；M3 stdout COMPLETED token 绑定 `job_name`（其他 job 的 token 不作为证据）；ODB 增加 non-empty gate（0 字节 → SOLVE_FAILED，"zero-byte odb"）；report 增加 `execution.wall_time_s`；ODB claim 措辞修正为"produced by a successfully completed Abaqus job; NOT yet opened/validated by odbAccess (M4)"。
- **CPU8 实验（2026-09-15，单变量）**：同一 accepted deck、唯一变量 `cpus 4→8`（`work/fig1_solve_cpu8_validation_001`）→ `SOLVE_COMPLETED_WITH_WARNINGS`、59 增量、cutback 模式与 003 一致、0 error、17 warnings、ODB 16,075,836 bytes，但 **wall_time 1971s vs 003 的 993s（明显更慢）**。结论：本机 preferred profile 保持 `cpus=4, standard_parallel=solver`；portable safe default 保持 `cpus=1, solver`。实验记录见 docs/TROUBLESHOOTING.md。
- 失败/诊断历史集中化：`docs/TROUBLESHOOTING.md`（并行 preprocessing 失败、jleConfig 假设证伪、.log 行为、warning 签名、.sta parser bug、001/002/003 attempts、CPU8 实验、timeout 债务、attempt 保存政策、30% 非收敛历史）。

## 已实现且经过本地逻辑验证

| 文件/入口 | 已完成内容 | 不应超出的解释 |
|---|---|---|
| `pipeline/common.py` | 稳定配置 hash、文件 hash、原子写文件、独立目录预约 | 未包含跨机器文件锁 |
| `pipeline/mesher_adapter.py` | 私有源码/配置工作目录与完整命令计划 | 不执行外部网格任务或验证 exe 环境 |
| `pipeline/mesh_contract.py` | NPZ/report/CSV 数据契约核查 | 不取代 Step05 拓扑和 Abaqus Mesh Data Check |
| `pipeline/pbc.py` | 等价类与周期偏移、代表节点约束 | 未用真实 Fig.1 ODB 做残差验证 |
| `pipeline/prepare_fe.py` | 壳/PBC include、壳厚和模型输入清单 | 不是完整物理模型 writer |
| `pipeline/state.py` | SQLite 独占 claim、owner、事件与阶段结果 | 未连接真实进程、不提供自动接管/心跳恢复 |
| `pipeline/diagnostics.py` | 关键日志判断与归一化进度停滞函数 | 不是完整 Abaqus 2026 日志解析器 |
| `pipeline/curve_qa.py` | 对齐曲线检查与 11 点插值 | 不是完整样本验收器 |
| `run.py` | 各已实现功能的命令行入口 | 无 solve/batch 命令 |

## 下一阶段模块接口

以下是后续里程碑（M2 起）的**待实现接口**，不是当前可调用功能。`build_physical_inp` 已由 `pipeline/physical_builder.py::build`（M1-1..M1-7）实现：-> physical.inp, includes, model_manifest, build_report（static validation only）。实现应以基础模块为支撑，而非重写已有网格。

```python
# 输入/输出均应保存为带 schema_version 的 manifest；此处是类型示意。
def build_physical_inp(mesh_bundle, physics, material, numerics, outputs, attempt_dir):
    # -> physical.inp, includes, model_manifest, build_report
    ...

def run_datacheck(model_manifest, environment, resource_policy, attempt_dir):
    # -> launch metadata, fresh logs, diagnostic report, initialization ODB
    ...

def inspect_initial_contact(datacheck_odb, model_manifest, quality_policy):
    # -> STRAINFREE statistics, PBC-initial-geometry check, contact initialization QA
    ...

def run_solver(model_manifest, numerics, environment, watchdog_policy, attempt_dir):
    # -> process metadata, completion evidence, logs, solve_report, ODB
    ...

def export_odb(odb_path, model_manifest, output_policy, extraction_dir):
    # -> separate raw history time axes, field snapshots, contact data, extraction report
    ...

def assess_result(raw_results, upstream_evidence, model_manifest, quality_policy):
    # -> ACCEPTED / REJECTED / NEEDS_REVIEW, metrics and source locations
    ...

def reconcile_pending_attempts(state_store, environment):
    # -> adopt live jobs / recover completed stages / label interrupted attempts
    ...

def run_batch(case_manifest, profiles, resource_policy, state_store):
    # -> stage-level scheduling, bounded retry, resumability, batch reports
    ...

def export_dataset(accepted_results, export_profile, export_dir):
    # -> deterministic, deduplicated, immutable dataset snapshot
    ...
```

## 完整 builder 的固定装配顺序

1. 读取已验收网格和配置，确认单位及内容指纹。
2. 分配全局 node/element/RP 标签，拒绝重叠。
3. 写 shell mesh、集合，计算 h=ρV/A。
4. 写材料/截面，检查材料类型与参数范围。
5. 写刚板网格、RP、rigid body、接触表面。
6. 写代表节点 PBC 和对应 manifest。
7. 写底板固定与顶板导向 BC；辅助横向控制变量自由。
8. 写 General Contact 和明确的初始化策略。
9. 写 Dynamic Implicit、Smooth Step 和目标位移。
10. 写与本构及求解器兼容的 history/field 输出。
11. 确认 include 都存在、节点集非空、引用有效、无 dependent DOF 冲突。
12. 原子发布 INP 和 build_report；随后由另一阶段实际 Data Check。

## 关键待验输入

真实 Fig.1 shell.npz / pairs.csv / shell_report、手工 physical.inp、完整 `.dat/.msg/.sta/.log` 和 ODB。若本地尚未完整达到 30%，先保留已有部分结果作诊断，并将完整 30% 验收单独登记为未完成。

## 为什么不在 v0.1 假装接通生产运行

本次输入只有文档与网格源码，沒有实际生成的 Fig.1 网格、手工 physical.inp、ODB、CGAL exe，也没有当前环境可调用的 Abaqus。强行把尚未逐关键字对照的 writer 标成生产可用，会把错误扩散到后续批次。当前接口与基础函数已可审查，完整 INP 接通后可以直接进入真实本机验证。
