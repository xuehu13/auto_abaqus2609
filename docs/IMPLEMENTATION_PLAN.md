> **[SUPERSEDED 2026-09-16]** 本文件描述的旧架构（identity v2 / staging planner /
> 三层 schema / 旧 CLI / 旧配置文件）已被单目录流水线取代，本文件不再更新，内容仅作历史存档。
> 当前以 `README.md`、`AGENTS.md`、`docs/HANDOFF_CURRENT.md` 为准。

# 分阶段实施计划

日期：2026-09-13。以现有 v0.1 和本机查证结果为起点，不重写网格算法，不立即放量。完整架构仍见 `Abaqus_Automation_Design_v1.0.md`，本文件落实执行顺序与验收证据。

> **[HISTORICAL / 部分已被 SUPERSEDED（2026-09-16 加注）]**：下一段"当前接管任务到环境检查……本次没有启动"是 2026-09-13 接管时的历史描述。此后 M1/M2/M3 已全部完成、30曲面 Phase A 验证与 5-case ad-hoc ODB diagnostic 已发生；当前状态以 `docs/HANDOFF_CURRENT.md` 与根目录 `README.md` 为准。历史文字保留不删除。

当前接管任务到环境检查、基础测试、旧结果审计和文档为止；下列求解/Data Check/批次属于后续开发任务，本次没有启动。

## HIGH-PRIORITY DEFERRED PERFORMANCE DEBT：standard_parallel=all（2026-09-16 登记）

Status: `DEFERRED`（登记于 30曲面实验后复盘；本轮只记录，不实际运行）

- 现状：开发机 `standard_parallel=all` 在 General Contact preprocessing（`pre|Elem|ElemC|Econtp|ConnectivityAtNodes`）可复现触发 `EXCEEDED THE MAXIMUM AMOUNT OF THREADS TO BE USED PER DOMAIN (<=100)`；当前 workaround 为 `standard_parallel=solver`（单元操作串行）。完整诊断链见 `docs/TROUBLESHOOTING.md`。
- 影响：General Contact preprocessing 无法并行，长时 solve 的 wall time 可能显著高于必要值；30曲面实验中单个 solve 16–36 分钟，若进入批量该债务会放大。
- 后续优先测试（**先 Data Check，后 solve；任何组合未验证不得用于正式求解**）：
  1. `cpus=8, threads_per_mpi_process=8, standard_parallel=all`（首选；`threads_per_mpi_process` 为 environment 文件级参数，需经 `abaqus_v6.env` 注入，非 abaqus.bat CLI 选项）。
  2. 候选矩阵（cpus / threads_per_mpi_process / standard_parallel）：`8/automatic/all`、`8/8/all`、`4/4/all`、`8/4/all`、`8/2/all`、`8/1/all`。
- 验收：以小 deck 或 Data Check 确认 preprocessing 不再触发 threads/domain ERROR，再做真实 solve 对照 wall time；结果无论成败登记回 `docs/TROUBLESHOOTING.md` 与 `docs/HANDOFF_CURRENT.md`。

## v2 Phase 2：配置语义与 identity 重构（2026-09-16，已完成，**未运行 Abaqus**）

定位与边界：本阶段只做"配置解释"与"身份系统"，**不**触碰力学模型、deck 文本、
网格算法、PBC 数学、contact physics、材料数值、厚度公式、压缩目标、增量数值与输出请求。

### 交付

1. **新增 `pipeline/specs.py`**：legacy config → 严格解析 → 兼容断言 → Normalized Spec
   （`ModelSpec` / `MaterialSpec` / `SolverSpec` / `OutputSpec` / `CaseSpec` /
   `RuntimeSpec`），并作为 identity v2 的唯一实现（`physical_model_id` /
   `solver_spec_id` / `output_spec_id` / `build_artifact_id` / `build_input_id` +
   `mesh_identity` 语义网格指纹）。
2. **renderer 只消费 spec**：`physical_builder` 的 6 个 renderer 与 `prepare_fe`、
   `mesher_adapter`、`scripts/pixi_tasks.mesh` 全部改为 spec 入参；`_load_numerics` /
   `_load_outputs` 私有 raw 入口删除。冻结 vendor 仍收到由 spec 重建的
   legacy JSON（`CaseSpec.vendor_payload()`，实测与源 config 内容一致）。
3. **DEAD/FAKE 字段收敛**：baseline 值 = 兼容断言，其他（合法 Abaqus）值 =
   `NOT_IMPLEMENTED`；legacy numerics runtime 字段退出 solver 配置并记录为
   NOT consumed；metadata 字段（`profile_id`/`note`/`validated_to_target`/
   `material_id`/`source`/… ）统一进 `metadata` 段，不进入任何 id。
4. **manifest schema 2**：`identity` / `spec` / `metadata` / `unused_config_fields` /
   `normalized_away` / `config_files`；legacy `model_key`/`scaffold_key`/`build_key`
   保留为 v2 alias（datacheck/solve 与历史 report 不受影响）。
5. **region 角色化**：output region 公开词表 = 语义角色 + 历史 NSET 名；渲染仍用内部名
   （deck 字节不变），未知名字在归一化阶段 `CONFIG_INVALID`。
6. **测试**：新增 `tests/test_normalized_specs.py`（43 项）；core 242 + boundary 8 全 PASS。
7. **回归**：Fig.1 20% byte regression PASS（10 个 deck 输入逐字节一致）、semantic
   regression PASS；30/30 历史 build 与 30/32 历史 datacheck 兼容；未运行 Abaqus。

### 本阶段明确未实现（NOT_IMPLEMENTED，不得静默回退）

任意 `repeats`、非 `lateral_xy_platens` 边界模型、tabular/ramp amplitude、
宏剪切自由取值、通用 rigid-body 策略、R3D3/S4R 等其它板/壳单元、
rate-dependent 材料、非 `true_stress`/`equivalent_plastic_strain` 的 measure、
非零 iso_level、非 hard/penalty 接触策略、restart 开启、非 increment 输出调度、
contact/element/integrated 输出请求、非 `N-mm-s-tonne-MPa` 单位制。

### 下一轮候选（本轮未施工）

runtime/staging 单真值化（含把 `pbc_map.json`/`model_inputs.json` 纳入 provenance）、
diagnostics/evidence 收敛、`physical_builder.py` 拆分、solver renderer 边界、
M4 ODB extraction；`macro_shear` 若要做成真实物理选项，需先做科学决策。

## v2 Phase 3A：runtime / staging 单真值（2026-09-16，已完成，**未运行 Abaqus**）

定位与边界：只处理执行层——runtime 配置解析、artifact 角色、输入 staging、provenance staging、
source integrity、job identity。**不**触碰 diagnostics、completion evidence、timeout 行为、
process ownership、retry/watchdog、Explicit。

### 交付

1. **build 发布 structured artifact manifest**：`build_report.artifacts` 与
   `model_manifest.artifacts`（`path` / `role` / `sha256` / `required_for_datacheck` /
   `required_for_solve`），覆盖 deck root + 9 include + `pbc_map.json` + `model_inputs.json`。
2. **单一 staging planner**（`pipeline/runtime/staging.py`）：`plan_*`（只做决策，无副作用）
   → `verify_source`（recorded SHA == 当前源字节，attempt 创建之前）→ `stage`（copy + 逐条
   SHA 证明）→ `verify_staged`（复检）。datacheck/solve 分别只有一个 plan 入口。
3. **两条独立证据**：deck 的 `*Include` graph ↔ artifact manifest 交叉核对
   （`ARTIFACT_GRAPH_MISMATCH` / deck 侧 `SOURCE_*_ARTIFACT_MISMATCH`）。
4. **provenance staging + 验证**：`pbc_map.json`、`model_inputs.json`、`source_build_report.json`
   进入两级证明；`source_model_manifest.json` 明确自记录（`sha_source`），
   provenance 失败码与 deck 失败码分离（`PROVENANCE_ARTIFACT_MISMATCH`）。
5. **runtime 单一 resolver**（`pipeline/runtime/config.py`）：CLI > stage runtime 文件 >
   safe default；记录 per-value source；`standard_parallel` 标记为 Standard-only 并对非
   Standard 后端 fail closed；`timeout_s` 成为唯一 timeout 真值。
6. **job name 派生**（`pipeline/runtime/job.py`）：`<case_id>_dc` / `<case_id>_solve`，
   可选 `--job-name` 覆盖，report 记录 `derived|cli`；不进入任何 scientific identity。
7. **打破 solve → datacheck 依赖**：launcher/release gate 移入 `pipeline/abaqus_launcher.py`，
   warning 分类器移入 `diagnostics.py`，共享 helper 全在 runtime/leaf 层。
8. **identity chain**：`build_artifact_id` 从实际 deck 字节重算并与声明比对；
   datacheck/solve report 记录同一组 v2 ids。
9. **report schema 2 + 兼容读取**：`artifacts`（输入 manifest）/`job`/`staging`/`abaqus_output`；
   schema 1 的 `staged_files` 被映射为同一 record 形状（真实历史 attempt 实测可用）。
10. **测试**：新增 `tests/test_runtime_staging.py`（40 项）；core **282** + boundary 8 全 PASS。

### 明确未完成（属 Phase 3B 候选，本轮未施工）

diagnostics 统一、completion evidence 统一、timeout 的结构化失败报告、process ownership、
retry/watchdog、Explicit backend、artifact retention/cleanup。

### 验证

Fig.1 byte regression PASS（10/10）+ semantic PASS；五个 v2 identity 与 Phase 2 完全相同；
30/30 历史 build 与 30/32 历史 datacheck 兼容；`work/fig1_datacheck_m2_final_001`（schema 1）
实测可 plan + `verify_source`。

## 阶段 A：固定可复核基准（接管已完成主要部分）

已有：32 文件 vendor 保真、真实 Fig.1 bundle 定位、Mesh Data Check 证据、完整 20% 手工作业快照、14 项基础测试、Abaqus Python 真实 history 导出验证、路径/版本/文件指纹登记。

还要在开发开始时复核源文件 hash，固定 mesh_key / manual_model_key；按“完整 20% 基准”“目标 30%”“历史两次中断”分别登记，不复用含糊的 `fig1` 成功状态。旧文件若变化，产生新的快照，不覆盖本次快照。无需为读取资料再等用户补充。

## 阶段 B：完整物理 INP writer（**已实现 2026-09-15，M1-1..M1-7 完成**）

> 状态（2026-09-15）：以下 1–9 步已全部实现于 `pipeline/physical_builder.py`（M1-1..M1-7）；第 9 步的静态报告即 `build_report.json` 的 13 项 static checks。真实 Fig.1 smoke 见 `work/fig1_build_m17_smoke_001`。仅剩"真实 Data Check 通过才可标为 Abaqus 输入验证通过"尚未发生 → 下一阶段（M2）。

建议接口 `build_physical_inp(mesh_bundle, physics, material, numerics, outputs, attempt_dir)`，由普通 `diffumeta_geo` Python 执行。新增外层模块和 CLI；保留 `prepare-fe` 作为只准备片段的入口，避免悄悄改变既有语义。

按以下小步骤实施，每一步都有可审查产物：

1. **契约和身份**：读取真实 NPZ/report/CSV；验证单位、参数合法性、材料用途标记；把网格/材料/加载/数值/输出/代码版本纳入 manifest 和内容 hash。
2. **壳与集合**：复用 mesh_contract、编号出口与厚度公式；节点坐标/连通/法向不重新生成；建立稳定非空集合，输出与手工壳差异报告。保留高精度坐标，说明 CAE 手工文本舍入差量。
3. **材料和截面**：按配置生成 Density/Elastic/Plastic/Shell Section；明确 5 个截面积分点及所采用壳设置。当前 surrogate 明示研究/接口用途，`allow_production_dataset=false` 不得被绕过。
4. **刚板与 RP**：当前 Fig.1 baseline 为 18×18 mm R3D4 压板，尺寸由 `physics.platens` 配置驱动；R3D4 是当前 supported platen policy，不是长期唯一方案。生成压板、RP/刚体/顶底集合和 BC；统一标签分配，检查无碰撞、无空集合、无 inactive DOF 误选。
5. **PBC**：复用现有代表节点算法；检查原 pairs 关系可恢复、消元自由度不复用；用手工树式 equation 核对约束空间，不能仅比较“1722 条”。保留横向宏观伸缩自由、转角策略及边界模式的显式配置。
6. **接触**：当前 Fig.1 baseline = General Contact / ALL EXTERIOR / HARD / friction=0.6 / slip_tolerance=0.005；friction、slip_tolerance 等数值由 config 驱动；general-contact/all-exterior 是当前 v0.1 supported policy，不是长期唯一 contact strategy，其他合法策略按实际科研需求扩展。压板单侧接触/初始化若作为改进，建立独立 profile 并说明变化，不能声称与旧模型逐项相同。保留壳自接触。
7. **步和加载**：写 Dynamic Implicit / MODERATE DISSIPATION / NLGEOM / Smooth Step。将20%（−2 mm）基准与30%（−3 mm）目标作为独立配置；步骤说明由实际参数生成，禁止“描述30%、实际20%”。
8. **输出**：每成功增量的 U3/RF3/能量及横向 RP；按目标版本确认 field 变量。修正 `frequency=50` 被误读为50帧的问题；设计可支持全过程 PBC/接触诊断的保存频率，记录实际场帧应变。每组 history 各自保存时间轴。
9. **静态报告**：检查 include 存在、引用有效、标签唯一、节点集非空、实际目标位移与描述一致；原子发布 `physical.inp`、includes、`model_manifest.json`、`pbc_map.json`、`build_report.json`。禁止在 BUILD 阶段宣称物理求解通过。

技术债登记：Shell Section 的 Simpson 积分点数当前 baseline 固定为 5（已明确不是不可变科研参数）；出现第二种 section policy/研究需求时再提升为 config，当前不提前建立 section plugin framework。M1-6 Output 阶段应建立独立 `config/outputs.example.json`，field/history 变量与频率不得硬编码为 Fig.1 唯一方案。输出需区分四层：1) Abaqus Output Policy（ODB/restart 写什么，M1-6 负责）；2) Extraction Policy（从 ODB 提取什么，ODB extraction 阶段负责）；3) Dataset / ML Export Policy（数据变换、场快照、训练数据打包，独立阶段）；4) Visualization Policy（曲线、云图、动画、论文图，postprocess 阶段负责）；M1-6 只负责第 1 层。Abaqus/Standard 的 `FREQUENCY=n` 表示每 n 个 increments 输出一次，不是“生成 n 帧”（防止再次把 frequency=50 误读为 50 帧等应变输出）。非阻塞技术债：future explicit output-disable policy（field-only / history-only / zero-field 等场景）必须显式设计并经 Data Check 验证，不得通过空 group 隐式依赖 Abaqus default output。

本阶段先交付可读完整 INP 和与手工基准的逐块差异报告；代码测试重点覆盖标签冲突、空引用、目标变更、PBC 等价与错误输入，不为每段文本格式编写镜像测试。

退出标准：仅靠冻结网格 bundle 和配置可生成完整物理 INP；独立目录，不依赖 CAE 菜单；真实关键字/单位/边界差异均有解释。随后的 Physical Data Check 通过才可标为 Abaqus 输入验证通过。

## 阶段 C：两道 Data Check 和初始状态验收（**2026-09-15 更新：Fig.1 Physical Data Check 已通过（execution level），COMPLETED_WITH_WARNINGS**）

> 状态：M2 已完成——自动 `physical.inp` 通过真实 Abaqus 2026 Data Check（`work/fig1_datacheck_m2_final_001`：returncode=0、0 error、10 warnings 保留）。开发机 `standard_parallel=all` 存在可复现的 General Contact preprocessing 失败，Data Check 安全 profile 为 `cpus=1, standard_parallel=solver`（machine-local 配置，见 HANDOFF "Runtime portability"）。10 条 warnings（双侧面歧义 ×8、STRAINFREE 调整比例、General Contact double-sided）作为 M3/M4 QA 强制输入，未白名单。30% Solve 验收仍属阶段 D。**M3 Solve execution policy 已在本机/20% validation case 上真实验证：`cpus=4, standard_parallel=solver`（16m33s 完成）；`cpus=8, solver` 亦完成但更慢（32m51s，见 TROUBLESHOOTING）；本机 preferred profile = cpus=4 + solver。**

外层执行器分别管理 Mesh Data Check 与 Physical Data Check，唯一 job/attempt/scratch 目录，保存命令、退出码、开始/结束时间、Abaqus 版本、输入/输出 hash。

复用冻结 07 作为 mesh 日志扫描器，但外层补充非空/新鲜/本次作业完成证据。物理与求解日志使用专门解析器，不把 `CONTACT FORCE ERROR` 等残差文字误判成 fatal。

Physical Data Check 检查完整材料/截面/刚体/约束/接触定义；用兼容 Abaqus Python 提取初始 STRAINFREE，并检查周期对应点调整差、壳/压板面向和间隙。为现存 10 个输入 warning 建立逐条审计，不自动继承为允许项。

退出标准：新自动模型有独立 Physical Data Check 完成证据；无未解释的严重初始化/约束问题；报告有具体节点/面/关键词定位。通过不代表30%必然可解。

## 阶段 D：单曲面求解、ODB、QA 闭环（**2026-09-15 更新：M3 已完成——Fig.1 20% validation case 自动求解通过，`work/fig1_solve_m3_20pct_003`，SOLVE_COMPLETED_WITH_WARNINGS，完整 ODB**；30% 验收、ODB 提取与 QA 仍按本节执行）

先建立最小可控单作业 launcher：已验证 bat 引用/退出码处理、唯一工作目录、超时观察、正确进程归属和温和终止。不得启动长程任务却没有停止/留证方案。

按需要做手工20%与自动20%对照，随后执行独立30%目标算例；不对所有未来 case 固定加跑20%预试验。固定材料/接触/PBC/CPU，差异有版本记录。旧模型若有错误，应比较并说明修正，不机械追求复制错误结果。

现有 history worker 扩展为 metadata、history、field、contact 的结构化导出。先独立保存每个时间轴，再校验覆盖区间和对齐规则。选取 RP 必须来自 manifest/真实集合。Abaqus 的退出码0不足以证明脚本完成，必须检查原子报告和必需产物。

QA 至少包括正常终止、最终 −3 mm、完整曲线、符号、单调性、不外推、全保存 history KE/IE、初始低IE、AE等能量、场 PBC 残差、初始接触、接触覆盖、单元异常和材料范围。曲线层 PASS 与最终 ACCEPTED 分开。

退出标准：Fig.1 到30%，关键质量门槛有完整证据；保存完整曲线、11点、场量/接触/诊断报告。若不能达到，输出准确失败类别和原因证据，不修改物理参数强行生成数据。材料定型可与 writer 并行研究，但此处不是自动替换本构的许可。

## 阶段 E：失败分类和有界重试

把当前小函数接入2026真实日志和进程生命周期：启动失败、许可证等待、网格失败、输入错误、接触初始化失败、数值不收敛、极小增量停滞、畸变、预算耗尽、ODB失败、QA失败分别登记。

优先从已保存的20%日志和旧JNL/操作记录建立解析样本；若找到两次卡滞原始日志，再加入真实 fixture。不能把截图推断伪造成标准 `.sta` 原件。未知 warning 进入 NEEDS_REVIEW。

预设观察窗口先只记录，再通过代表性运行校准；总预算/有限次数重试可配置。默认 base 加最多一次经验证的数值重试；每次新 attempt，保留参数 diff。材料、厚度、摩擦、PBC、位移目标不在透明 retry 中改变。改变加载时间/求解方法必须单独验证和标记。

退出标准：缺文件、错误配置、主动中断、许可证不可用等故障能被定位；同一作业进程被可靠停止，其他作业不受影响；失败不会自动进入数据集。

## 阶段 F：断点恢复和小规模队列

扩展 SQLite：artifacts、心跳、PID+启动时间+job身份、所有 attempts、QA结果、唯一发布记录。恢复器核实仍存活进程，决定接管监控/补登记完成产物/仅重做后处理/新 attempt 重试，不因过期心跳直接重复提交。

阶段完成依据输入指纹、输出hash及通过证据；模拟在写文件前后、SQLite提交前后中断。先实现阶段级续跑；Abaqus增量restart另做明确选项和专门测试，当前历史INP没有保存restart。

退出标准：重启不覆盖、不重复求解、不重复入库、不遗留失控进程；已完成的网格/建模/求解可按证据复用。

## 阶段 G：逐级放量

| 规模 | 目的 | 放行条件 |
|---|---|---|
| 5 个差异曲面 | 检查面积、seam、曲率、接触/屈曲差异 | 无需逐案改代码；失败有独立报告 |
| 20–50 个 pilot | 定型阈值、重试、资源估计 | 阶段成功率、P50/P95时间、内存、ODB大小、警告分布真实可算 |
| 200 个 | 验证调度/恢复/多槽位/存储 | 故障后可靠续跑，去重发布，不混淆case |
| 1000–2000 个 | 长期吞吐和资源增长 | 无系统性进程/数据故障，预算可预测 |
| 20000+ / 23534 | 固定生产profile运行 | 有正式曲面清单、材料/方法用途说明、已定型QA、容量与许可条件，批次报告和失败清单完整 |

并发由CPU、内存、许可证、磁盘最小余量决定。本机约31.63 GiB内存，不能照搬论文96 GB机器；先单solver、每job4 CPU候选，测量后再定。几何、solver、ODB提取分别限流。20%作业634秒不是30%全量耗时估计。

保留首批所有ODB与完整日志；明确所需场数据和代表/异常样本后再制定清理策略。不能只导出11点就删除唯一ODB。

## 暂不进入的分支

UMAT、高保真率相关材料、均匀化、有限多胞试件、三维周期和周期镜像接触均保留接口，不在完成单胞主链前混入。Ref41的一维模型不能直接成为S3R三维材料卡。`n×n×n` 不能只是复制单元后仍用单胞尺度的PBC/应力归一化。

## 最近一次开发会话的具体交付清单

- 新增完整 writer 和明确 CLI，保留现有入口语义。
- 使用已找到的真实 bundle；输出在新的 `work/fig1_build_<id>/`。
- 20%手工对照profile与30%目标profile身份分开；说明可用surrogate的用途限制。
- 输出关键词级差异报告、完整INP、来源manifest及基础检查结果。
- 报告“代码实现/基础检查/真实Data Check”三层状态；完整求解与批量仍按后续任务范围执行。

上述 writer 开发没有必须等待用户补文件的障碍。真正进入科研数据生产前，再集中明确材料用途、完整曲面清单和存储/计算预算。
