# Current Handoff — M1-6 Checkpoint

更新时间：2026-09-15
项目：auto_abaqus2609
branch：main
M1-6 feature commit：6b83d2c990907b093e882f1c7477aeea0757f2b3（`feat: add configurable output requests to physical builder`）

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
| M1-1 scaffold | DONE |
| M1-2 material + section | DONE |
| M1-3a rigid platens / RP | DONE |
| M1-3b BC | DONE |
| M1-4 contact | DONE |
| M1-5 step + loading | DONE |
| M1-6 output requests | DONE |
| M1-7 assembly/static validation | NOT STARTED |
| M2 Physical Data Check | NOT STARTED |
| M3 solve / M4 ODB extraction | NOT STARTED |

## 4. 当前 physical builder 产物

`pixi run cli build-physical --npz ... --report ... --pairs ... [--outputs ...] --out work/<新attempt>` 生成：

```
ingredients/        （shell_mesh.inc / lateral_pbc.inc / pbc_map.json / model_inputs.json）
blocks/
  material_section.inc
  rigid_platens.inc
  boundary_conditions.inc
  contact.inc
  step_loading.inc
  outputs.inc
  step_end.inc
model_manifest.json
```

**physical.inp DOES NOT EXIST YET.**

M1-7 将负责 assembly + static validation，并首次生成完整 physical.inp；M2 随后使用 Abaqus Physical Data Check 验证该完整 INP。**M1-7 生成成功 ≠ Abaqus 已验证通过。**

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

**已验证**：Python/Pixi 逻辑（81/81 tests：73 core + 8 boundary）；真实 Fig.1 mesh bundle smoke；block 确定性渲染；config 隔离（loading/contact/platen 参数互不泄漏）；hand-INP 语义逐项对比。

**尚未验证**：完整 physical.inp；Physical Data Check；自动接触初始化；自动模型 requested-output 的真实 ODB 行为（PRESELECT 采样密度）；30% solve；准静态科学有效性（`quasi_static_status=pending_qa`）；production dataset eligibility。

**`dataset_eligible=false`（builder 硬性保证）。**

## 10. hand/manual baseline 注意

- 手工成功压缩：**20%**（U3=−2mm，L=10）；当前 writer config 目标：**30%**（U3=−3mm）。
- 当前 smoke U3=−3mm **不是 writer bug**，是 config 目标本身的体现；手工模型当前角色 = **keyword 语义 baseline**，不声称自动模型已复现 20% solve。

## 11. 当前重要技术债

1. Shell Section Simpson 积分点 = 5：baseline-fixed，出现第二种 section policy 再 config 化。
2. identity 混合语义：`model_key`=物理模型身份 / `scaffold_key`=pre-output build-input+provenance / `build_key`=build provenance + rendered block identity；batch/cache 阶段统一，M1-7 前不重构。
3. explicit output-disable policy（field-only/history-only/zero-field）：未实现；空 group → NOT_IMPLEMENTED，禁止依赖 Abaqus implicit default。
4. PRESELECT-only 自动 ODB 采样：仅 keyword semantics reproduced，M2 后用真实自动模型 ODB 复核。
5. restart ownership：当前属 outputs 写盘策略；runtime/recovery 成熟后再评估迁移。
6. demo material：non-production surrogate，不是论文真实材料。
7. **Physical Data Check 尚未执行。**
其余债务见 `docs/IMPLEMENTATION_PLAN.md` 技术债段与 `docs/PROJECT_STATUS.md` 差异清单（引用，不复述）。

## 12. Local evidence（不进 Git）

`work/` 与 `reference/` 均为 Git-ignored local-only，新机器 clone 后**可能不存在**：
- `work/takeover_20260913_01/physical_snapshot/Fig1_Compression.inp`（hand keyword 语义 baseline）
- 同目录 `.dat/.msg/.sta/.log/.odb`（接触/求解证据）
- `physical_regions.json` / `physical_raw_history.json`（20% ODB 提取实证）
- 各 M1 smoke attempts（`work/fig1_build_*`）

## 13. reference PDF 约定

计划在本次会话结束后由用户本地归档为：
`reference/2026-09-15_chatgpt_auto_abaqus_M1-6_checkpoint_full_conversation.pdf`

**截至本 handoff commit，该 PDF 尚未由本项目代码/GLM 创建；其存在性不能作为 Git checkout 的前提。**
如果用户之后实际保存了该 PDF，它只是 Git-ignored local evidence / conversation archive，**不是代码真值**。正式工程状态以 Git docs + source + tests 为准。

## 14. 下一步

**下一次新会话不要立即编码 M1-7。** 先做 **M1-1~M1-6 stage-wide review**：
goal alignment / config boundaries / block ownership / identity debt / current validation claims / M1-7 scope。
总审查通过后，下一工程 milestone 才是 **M1-7 physical.inp assembly + static validation**；随后尽快进入 **M2 Physical Data Check**。不要继续无限拆分 BUILD milestone。

## 15. 下一阶段明确禁止

```
Do NOT:
- batch 20000 cases yet
- implement concurrency
- implement retry/recovery
- implement UMAT
- implement n×n×n
- change frozen vendor mesher
- launch full solve before M1-7/M2
- silently modify physics for convergence
```