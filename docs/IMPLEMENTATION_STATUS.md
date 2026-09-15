# v0.1 实施状态与后续接口

## M1 进度（M1-1/M1-2 checkpoint 2026-09-14；M1-3a/M1-3b checkpoint 2026-09-15）

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

### M1-7 未开始：physical.inp assembly + static validation
- 待办：按 step_loading → outputs → step_end 顺序装配 physical.inp（原子发布）+ static validation（region 引用存在性、`*Step`/`*End Step` 配对、label/集合契约、build_key 一致性）。

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

这些是**待实现接口**，不是当前可调用功能。实现应以基础模块为支撑，而非重写已有网格。

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
