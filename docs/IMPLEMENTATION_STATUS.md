# v0.1 实施状态与后续接口

## M1 进度（2026-09-14 checkpoint）

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

### M1-3b 未开始：Boundary Conditions
- 待办：从手工 Fig1_Compression.inp 提取完整 `*Boundary` 证据（含 RP_BOTTOM 的固定 DOF 集）后再实现；位移加载（RP_TOP U3）属 Step/Loading 阶段。

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
