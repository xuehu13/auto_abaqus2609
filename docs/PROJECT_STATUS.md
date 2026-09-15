# 工程已验证状态

> **2026-09-15 development checkpoint（M1-1..M1-7）**：M1-1 scaffold、M1-2 material/section、M1-3a rigid platens/control nodes/rigid body、M1-3b boundary conditions、M1-4 contact、M1-5 step+loading、M1-6 output requests、M1-7 physical.inp assembly + repository static validation 均已完成，**M1 BUILD complete**。`pipeline/physical_builder.py` + `build-physical` CLI 现在生成 `ingredients/`、7 个 blocks、顶层 `physical.inp`（9 条固定顺序相对路径 `*Include`，原子发布）、`build_report.json`（13 项 static checks）与 `model_manifest.json`（`status=PHYSICAL_INP_STATIC_VALIDATED`，`dataset_eligible=false`）。Pixi 下 94/94 core + 8/8 boundary 测试通过；真实 Fig.1 smoke 见 `work/fig1_build_m17_smoke_001`（13/13 checks PASS）。以上仍仅为 **Python builder + 仓库级静态检查**：**Abaqus 未被调用**，Physical Data Check 未执行、自动 solve 未执行、ODB QA 未执行，不构成任何 Abaqus 验证。M2 Physical Data Check NOT STARTED。早期 checkpoint（环境迁移、Fig.1 网格回归、M1-1..M1-6 细节、2026-09-13 接管核查记录）见 git 历史与 IMPLEMENTATION_STATUS，以下 2026-09-13 接管核查记录保持原样。

核查日期：2026-09-13。范围：工程接管、源资料核对、环境检查、原有轻量测试、现有 ODB 只读检查。未启动任何新 Abaqus Data Check、完整求解或批量计算。

**当前完成的是"冻结的网格模块 + 自动化基础模块 + 完整自动物理 INP writer（仓库级静态验证）+ 一个真实完成到 20% 的手工压缩算例"。完整 30% 压缩验收、Physical Data Check、监控、恢复和批量主链尚未完成（2026-09-15 M1-7 checkpoint）。**

## 1. 最重要的新发现

较新的交接文档记载两次 30% 目标试算在约 `t=0.6083` 和 `t≈0.72` 卡滞。工作区最初只有 meshcheck 基准，但继续按交接路径和相关文件名查找后，在 `E:\ABAQUS\2026temp\Abaqus_Work` 找到 2026-09-12 19:17–19:28 的 `Fig1_Compression.*`。

这套文件的 `.log/.sta/.msg` 和 ODB 均显示正常结束；然而 **INP 的实际加载是 `RP_TOP, 3, 3, -2.`，ODB 最终 `U3=-2.0 mm`**。高度 10 mm，因此仅到 20%。INP 步骤说明仍写 `30% quasi-static compression`，描述文字没有随位移更新。

这证明在历史记录之后至少存在一个完整 20% 作业，不能据同名 Job 或 COMPLETED 推断 30% 已完成，也不能用当前这套成功日志替代之前两个卡滞作业的原始日志。首次卡滞另有 JNL 证据；第二次约 0.72 的进度目前主要来自操作 PDF/交接。

## 2. 文件证据分级

| 对象 | 实际位置及内容 | 分类 / 结论 |
|---|---|---|
| 工作区 meshcheck INP | `F:\auto_abaqus\baseline_test\fig1_meshcheck.inp`，9483 nodes / 18164 S3R，E=1、ν=0.3、厚度 1 mm、静力占位步；无 PBC/压板/接触/压缩 BC | 网格检查 INP，不是物理压缩模型 |
| meshcheck 日志/报告 | 同目录 `.dat/.msg` 及 2 个 report JSON；dat 中 `ANALYSIS DATACHECK COMPLETE`，无网格 error/warning 命中 | 历史 Mesh Data Check 通过证据；本次只复核 |
| meshcheck ODB | 同目录 3,016,580 bytes；`MESH_CHECK` 仅 1 帧、time=0；ODB jobStatus 为 successfully completed | 初始化 ODB，无非零时间压缩结果；状态成功仅对应 Data Check |
| baseline 其他文件 | `.023/.cax/.com/.mdl/.prt/.sim/.stt`，以及 pairs CSV | 伴随/中间文件；`.stt` 大小 72,342,532 bytes 不代表存在完整压缩解；未逐一解释这些二进制内容 |
| 真正 shell bundle | `F:\DiffuMeta_Abaqus\periodic_surface_mesher_clean\cases\fig1\shell\fig1_shell.npz` 和 `fig1_shell_report.json`；pairs 已在 baseline | 工作区 baseline 缺 NPZ/report，但本机已找到，现有契约读取通过 |
| 完整物理 INP | `E:\ABAQUS\2026temp\Abaqus_Work\Fig1_Compression.inp`，1,152,781 bytes；具备材料/截面/刚体/PBC/接触/动态步/加载/输出 | 完整手工物理模型，实际目标 20%，不是 v0.1 自动生成 |
| 完整 20% 结果 | 同目录 `.odb/.dat/.msg/.sta/.log`；ODB 16,897,560 bytes | 已完成所施加的 20% 作业；相对项目 30% 目标仍不完整；科学质量尚未全面验收 |
| 第一次部分试算 | `F:\DiffuMeta_Abaqus\DiffuMeta_onecell0912.jnl` 尾部记载 t≈0.6083087、微小增量、外部中断 | 实际运行历史，未找到这次独立留存的 ODB/INP/log 全套；不能从当前 20% 文件复原 |
| 第二次部分试算 | 操作 PDF p137、最新交接第 13 节记录 t≈0.72 卡滞 | 文档/截图级证据，未定位同一 attempt 的完整原始结果包 |
| 更早 OneCell ODB | `E:\ABAQUS\2026temp\Abaqus_Work\OneCell_Compression.odb`，壳 21980 nodes / 42868 elements；Compression 没有场帧，jobStatus UNKNOWN | 早期非 clean 网格，不能作为完整压缩结果 |
| CAE 模型 | `F:\DiffuMeta_Abaqus\DiffuMeta_onecell0912.cae` 等存在；JNL 可读 | 本次没有打开 CAE 内核验证数据库内部最终状态，不把 JNL 与当前 INP 当作必然同一版本 |

`baseline_test` 共 14 个文件，原文件保留不变；其中没有 `.sta/.log`，纯 mesh datacheck 缺 `.sta` 不自动判失败。现有 export/report 中的路径指向外部 clean 工程，是来源记录，不代表文件已经复制到 baseline。

本次已把当前 20% 作业的六个主要文件复制到独立 `work/takeover_20260913_01/physical_snapshot/`。原件、快照、网格、资料、CGAL 程序的大小和 SHA256 见 [LOCAL_EVIDENCE.json](LOCAL_EVIDENCE.json)。不覆盖 baseline，也没有把大型文件加入 Git。

## 3. 代码实现与验证矩阵

| 模块 | 代码已实现 | 本次逻辑/真实数据检查 | 真实 Abaqus 验证范围 |
|---|---|---|---|
| vendor 00–07 + CGAL | 网格生成、独立 validator、meshcheck 导出及日志扫描 | 原始 zip 的 32 个文件全部一致；外部 clean 的 Python/C++/hpp 也一致；CGAL Usage 启动通过 | 历史 Fig.1 Mesh Data Check 已复核；本次不重跑完整网格链 |
| common | hash、原子文件、独立目录预约 | 已有测试涉及，14/14 通过 | 不适用 |
| mesher_adapter | 创建私有工作副本和阶段命令计划 | 隔离与拒绝覆盖测试通过 | 不执行外部网格/Abaqus 命令，不是 launcher |
| mesh_contract | NPZ/report/CSV 的编号、范围、面积、配对一致性检查 | 合成测试及真实 Fig.1 bundle 读取通过 | 不替代网格几何或 Abaqus Data Check |
| pbc | X/Y 等价类、周期偏移、代表节点方程 | 合成代数测试通过；真实 pairs 得到 287 条独立关系、1722 条 equation | 新代表节点写法未提交 Abaqus；旧手工 1722 条树式 PBC 有实际 20% 求解 |
| prepare_fe | shell/PBC include、厚度、标签、manifest | 真实 Fig.1 输出 `FE_INPUTS_PREPARED_ONLY` | 没有完整 INP，无新物理 Data Check |
| diagnostics | 少数 fatal/warning 正则、完成证据组合、停滞函数 | 逻辑测试通过 | 未接实时 `.sta` 解析和进程监控；不能自动完整分类所有 2026 日志 |
| state | SQLite 登记、独占 claim、owner、阶段事件 | 已有测试通过 | 无 heartbeat、真实进程接管、崩溃对账或队列 |
| export_history worker | region 列表和按精确映射读取 history，保留各自时间轴 | Abaqus Python 成功读取当前真实 20% ODB，4 个 region；原始 JSON 导出成功 | 本次已从“仅语法检查”提升为“真实 history 导出验证”；仍不是完整后处理器 |
| curve_qa | 覆盖范围、符号、单调性、能量、11 点插值 | 14 项中的相关测试通过；真实 20% 曲线被正确拒绝作为 30% 数据 | 不承担接触/PBC/材料/完整场验证 |
| run.py | plan、prepare-mesher、prepare-fe、qa-history、status | plan/help 正常 | 无 solve/batch 命令 |
| 完整 writer / launcher / watchdog / recovery / batch / dataset exporter | 未实现，设计文档有接口 | 未验收 | 不可生产运行 |

所有当前准备/曲线输出仍然 `dataset_eligible=false`。不能把模块列表中的“有设计”记成“已实现”。

## 4. 论文、手工模型与源码的设置对照

页码均为 PDF 物理页码，不是期刊页码。

| 设置 | 原始依据 | 现有实际实现 / 核查结论 |
|---|---|---|
| Abaqus 版本 | 主文 p11：ABAQUS/CAE 2023 | 本机和真实日志为 2026；属于版本差异，需要本机回归 |
| 单胞/单元 | 补充 p6–7：10×10×10 mm，S3R | config L=10；NPZ、meshcheck、物理 INP 均为 9483 / 18164 S3R |
| 曲面表达式 | 交接、config；论文代表性曲面 | `2.3*cos(X)*sin(Z)+1.9*cos(Y)*cos(Z)-0.6=0`；`X=2πx/L` 等；不是把 mm 直接带入三角函数 |
| 网格尺寸 | 主文 p11、补充 Fig.S2 p7：最终平均边长约 0.20 mm | CGAL `facet_size=0.15 mm`，真实报告平均边长 0.20181657 mm；输入 criterion 不等于输出平均边长 |
| 厚度/相对密度 | 主文相对密度 10%，补充 p4 厚度与体积/面积关系 | `h=0.1×1000/304.6482709049=0.328247390681 mm`；手工 `0.32825, 5` 为舍入厚度及 5 个截面积分点；meshcheck 的 1 mm 仅占位 |
| 材料 | 主文 p11–12：实验标定弹塑性，UMA90 标称 E=484 MPa、UTS=11.9 MPa、伸长 19.3% | 手工 INP 与 demo_surrogate 的 E=484、ν=0.4、ρ=1.1e-9、12 点 Plastic 表一致；该表不是作者公开的标定卡，硬化尾段是项目近似 |
| 压板/BC | 主文 p11：底板固定，顶板垂直下压，侧向周期 | 实际每板 324 个 R3D4，362 节点含 RP；RP 坐标 (5,5,0)/(5,5,10)；底板六自由度固定，顶板除 U3 外固定；18×18 mm、1 mm 网格是项目选择 |
| 周期关系 | 主文只明确 lateral PBC；操作记录 p28–40 展示 X/Y 树式方程 | X141/Y148/Z124；压缩不使用 Z；X/Y 宏观正应变自由、宏观剪切受限、三转角相等是具体实现选择；新 pbc.py 使用代表节点式，需验证约束空间等价及大转动残差 |
| 接触 | 主文 p11：General Contact，μ=0.6 | 实际 ALL EXTERIOR、自接触、HARD、Penalty 摩擦，slip tolerance=0.005；没有明确定义压板单侧初始化；double-sided 警告仍在 |
| 求解过程 | 主文 p11：dynamic implicit / moderate dissipation | 实际 NLGEOM、1 s、初始 0.001、最小 1e-8、最大 0.02、最多 10000 增量、`initial=NO`；这些具体数值不是论文公开参数 |
| 幅值/目标 | 项目目标 30%，手工历史设 Smooth Step | 现存完成作业 Smooth Step (0,0)→(1,1)，**−2 mm/20%**；配置示例仍为 −3 mm/30%，不能混为同一物理输入 |
| 输出 | 主文 p11：50 个等应变状态，随后 11 点重构；补充 p7 Table S3 | 现存 INP 场输出 `frequency=50`，实际仅 t=0、0.8308828、1 三帧，**不是 50 个等应变点**；history 每增量一次，共 60 点 |
| 11 点 | 补充 Table S3 p7，已看图表 | 1.6/3.1/5.5/9.4/14.9/16.5/20.4/22.7/26.7/28.2/30.0%；与 curve_qa.TARGETS 一致；未达目标不外推 |
| 准静态 | 主文 p12：所有应变增量 KE < 1% IE | 现有规则按每个已保存 history 点检查，低内能区间另查绝对 KE；ALLAE/IE 5% 是项目草案，不是论文标准 |
| 采样/插值 | 补充 p7：11 点加隐含原点用 cubic spline 重构曲线 | 现有模块从密集 history 线性插取目标点；“提取目标点”与“用稀疏点重构曲线”是不同操作 |

手工 INP 壳连通与真实 NPZ 完全相同，坐标最大差约 `4.805e-7 mm`，因此不是逐字节相同的节点文本；差量很小，可能来自 CAE 导出精度，但本次不把原因当成已证实。自动 writer 应保留 NPZ 精度并在比对报告中说明差量。

## 5. 当前 20% 结果的质量边界

直接用 ODB 的 RP_TOP 集合确认顶板 region 为 `Node TOPPLATE.362`，并核对 RP 坐标 z=10，避免仅按名称猜对象。选取标准变量名 ALLIE/ALLKE/ALLAE；ODB 还存在 Repeated history 键，清单已保留，不重复拼接或相加。

| 实测项 | 结果 |
|---|---|
| 最后 step time | 1.0 s |
| 成功增量 | 59（加初始点后 60 history 点）；1 次 cutback；241 次迭代 |
| 最终 U3 / RF3 | −2.0 mm / −31.41401863098 N |
| 宏观压缩应变 / 应力 | 0.20 / 0.3141401863 MPa；取 `ε=-U3/10`，`σ=-RF3/100` |
| U3/RF3/IE/KE/AE 时间轴 | 本次选取的 5 组时间轴逐项相同，无需插值对齐 |
| max KE/IE | 2.2247987e-5（约 0.002225%），IE>1e-8 N·mm 的保存点 |
| max AE/IE | 0.005850738（约 0.5851%），同一有效区间 |
| 初始低内能 | 6 个点，按现有草案绝对 KE 规则未失败 |
| 按当前 30% 曲线策略 | `CURVE_QA_FAILED / TARGET_RANGE_NOT_REACHED`，11 点结果 null，不外推 |
| dat/msg 诊断 | 输入阶段 10 个 warning、运行阶段 7 个 warning、0 error；运行 warning 为初始 zero moment 类，仍需审核 |
| 初始接触 | dat 记载约 0.0382796 mm 调整量、double-sided facets 和 8 组相邻底板节点侧向歧义警告；不可因完成或能量较低直接忽略 |
| ODB 场 | U/UR/S/LE/PEEQ、CPRESS/COPEN 等存在；初始帧有 STRAINFREE；未见 CSTATUS 键；仅 3 帧 |
| restart | INP `*Restart, write, frequency=0`；未证明可从任意中断增量续算 |

本次没有对所有场帧执行完整 PBC 残差、初始调整周期差、接触覆盖/穿透/法向、材料塑性范围或网格敏感性验收，也没有比较上下板反力（底板 history 未请求）。因此质量状态为 **NEEDS_REVIEW；相对 30% 任务拒收**。不能把低能量比值解释为“物理模型全部正确”。

## 6. 已确认的差异与处理

1. **旧 Current_State 与较新 Full 交接**：前者尚建议重建物理模型，后者已有两次试算；按时间顺序保留，不采用“尚未开始物理建模”的过时概括。
2. **交接与现在的真实文件**：新增发现完整 20% 作业；30% 仍未验证。文件名相同无法证明是原卡滞 attempt；不编造覆盖经过或恢复关系。
3. **INP 描述与实际加载**：说明写 30%，加载 −2 mm，ODB 同为 −2；以物理关键词和真实结果确定本次 20%。
4. **Step time 与应变**：Smooth Step 不线性。假定旧目标为 −3 mm，t=0.6083 对应约 20.90%，t=0.72 对应约 25.87%，不是按 0.72×30% 得到 21.6%；旧试算最终应变仍优先取其原始 U3，现缺对应 ODB。
5. **PBC 算法**：手工树式与 v0.1 代表节点式不同。1722 条数量一致只证明计数一致，不能代替约束空间/消元顺序/结果残差验证。
6. **论文与实现**：论文用 Abaqus 2023、实验标定材料；本机用 2026 和 surrogate。ν、密度、Plastic 尾段、1 s、具体增量、转角约束、压板尺寸均不可说成作者原始输入。
7. **输出“50”**：`frequency=50` 是每 50 个增量输出，不是 50 个输出点；现有三帧无法支撑全过程场质量检查。
8. **运行完成与验收**：meshcheck ODB 同样能显示 completed；必须同时检查任务类型、实际加载、最后位移和质量。
9. **旧文档称缺输入/不可调用 Abaqus**：是当时 Linux 交付环境限制。本次在用户 Windows 本机找到并验证路径，原文不删除，新状态以本文件为准。
10. **环境 pin**：环境 yml 的 NumPy1.26 与实际2.2.6不同，后者符合历史 clean 回归和当前 requirements；不改环境凑版本。

## 7. 哪些文件还缺，哪些只是没放进工作区

| 文件/资料 | 现在的状态 | 是否阻碍下一步 |
|---|---|---|
| clean Fig.1 shell.npz / shell_report | baseline 内缺，但已在 F 盘旧工程找到；pairs 在 baseline | 不阻碍 writer 开发 |
| 手工完整物理 INP + 当前日志/ODB | baseline 内缺，但已在 E 盘找到完整 20% 套件并作独立快照 | 足够作为结构/20% 行为基准，不能当 30% 基准 |
| `1、复现Abaqus仿真（初步尝试）.pdf` | reference 内缺；已在 `C:\Users\xuehu\Desktop\gpt总结\自动划分网格提交ai的文件\` 找到 249 页原件，hash 与 source_inventory 对应项一致 | 不再阻碍历史核对 |
| `ADMA-37-2505125-s001.pdf` | reference 内缺；已在 `C:\Users\xuehu\Downloads\` 找到 11 页原件，读取了 note3/Table1 | 不再阻碍确认其是一维材料模型 |
| 原两次卡滞的独立 INP/ODB/dat/msg/sta/log | 本次未找到可明确绑定到两个 attempt 的全套文件；第一次有 JNL，第二次有操作记录 | 不阻碍 writer；限制失败解析回归和原因归因 |
| 真正 −3 mm、30% 正常结束的完整结果包 | 在本次可访问的相关搜索范围内未找到 | 是后续 30% 验收缺口，不能伪造补齐 |
| 可直接生产使用的材料标定卡/适用范围 | 当前只有示例 surrogate；Ref41 一维 Maxwell+黏塑性+损伤不是 S3R 普通 Plastic 表 | 不阻碍示例程序开发；正式科研数据生产前必须定型 |
| 20000+ 曲面清单（稳定 ID、方程、单位、来源） | 当前项目只有 `config/cases/fig1.json`；未把外部数据集导入工程 | 不阻碍单例，批次阶段需要明确输入清单 |
| 完整 writer/监控/调度/恢复等源码 | v0.1 尚未实现 | 是开发任务，不是等待用户提供的文件 |

本次相关文件名搜索覆盖工作区、F/E 盘可访问目录及用户目录；部分目录权限受限，搜索错误记在 work 中，因此“未找到”不是声称全盘绝对不存在。没有必要为了开始 writer 再向用户索要已经找到的文件。

## 8. 阅读范围与可追溯性

- 阅读项目 README、IMPLEMENTATION_STATUS、VERIFICATION、source_inventory、设计方案及三份 Markdown 交接的相关架构/算法/限制/回归内容；核对 pipeline 全部模块、CLI、tests、worker、config，及 vendor 的 config/surface、05–07、CGAL 接口与关键约束。不是对所有网格算法重新做形式验证。
- 主文 16 页：完整提取可提取文字，重点阅读 FE simulation、材料、单位胞、输出；逐页图像核查 p11–12。p14–16 无足够文字，本次未据此声称读过其中内容。
- 补充材料 27 页：重点核查 p3–7 的生成/厚度/FE、p14–15 的耗时；查看 p6–7 的公式/Fig.S2/Table S3、p15 Table S6。其他 ML 部分不作为本次建模结论依据。
- 操作记录 159 页：提取逐页文本，重点检索/阅读 p28–40 PBC、p64–74 接触、p77 进度、p100–128 试算诊断、p137–140 材料/卡滞讨论；查看 p40、p71、p77、p137 页面。没有把历史聊天中的建议直接当成已执行事实。
- 早期 249 页记录：本次仅针对末期网格错误等相关内容核查；不是声称精读全部 249 页。
- 早期记录 p248–249 和补充 p4 的厚度公式亦已查看页面；前者记载 5661 distorted / 114 aspect ratio / 24 shell-normal 错误，不能与 clean 基准的零错误混用。
- Ref41 补充 11 页：阅读 note3 p5–7，并查看 p6 本构公式和 Table1。证实其基于梁纤维一维本构，含 Maxwell、黏塑性与损伤；不是论文 S3R 模型的现成材料卡，不启动 UMAT 分支。

原始文件未改写。文字/渲染中间结果在 work；文件指纹在 LOCAL_EVIDENCE。旧 docs/VERIFICATION 的“未在 Abaqus ODB 上运行”保留其历史日期；本次新的真实 history 验证以本文件为准。

## 9. 当前可执行的下一项任务

实现 `pipeline/physical_inp.py`（名称可按现有结构调整）的完整 INP writer，先用找到的 clean shell bundle 和手工 20% INP 逐块对照，输出完整模型与 manifest；把目标应变写成明确配置，保留 20% 基准与 30% 目标两套身份。随后在新的任务中进行独立 Physical Data Check，再做 30% 验证。具体工作包和退出标准见 [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)。
