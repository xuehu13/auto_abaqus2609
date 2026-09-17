> **[SUPERSEDED 2026-09-16]** ??????????????identity v2 / staging planner /
> ?? schema ???????????? CLI ???????????? `README.md`?
> `AGENTS.md`?`docs/HANDOFF_CURRENT.md`?????????????????????

# 本次验证结果

> [HISTORICAL 文档说明]：本文包含 2026-09-12 的 Linux 交付验证与 2026-09-14 的
> Windows + Pixi checkpoint 记录，均为历史证据，正文原样保留。当前最新验证状态以
> `docs/HANDOFF_CURRENT.md`、`docs/PROJECT_STATUS.md` 与根目录 `README.md`
> （"当前验证结果"与"30曲面阶段性验证"章节）为准。

> **当前 checkpoint（2026-09-14，Windows + Pixi）**：`pixi run check` 三环境 PASS；`pixi run test` 35/35 OK（14 项原始核心 + 7 项 builder scaffold + 6 项 material/section block + 8 项 Pixi 迁移边界）；`build-physical` 对真实 Fig.1 mesh bundle 冒烟通过，产物为 `ingredients/`、`blocks/material_section.inc`、`model_manifest.json`，无 physical.inp。此为 **Python builder + real mesh bundle smoke**，不是 Abaqus Physical Data Check。以下 2026-09-12 的 Linux 验证是历史交付记录，不是当前状态。

验证时间：2026-09-12。环境：当前 Linux 工作区的普通 Python；不是用户本地 Windows/Abaqus 2026 环境。

## 已执行

- `python3 -m unittest discover -s tests -v`：14 项测试全部通过。
- 新增 Python 文件逐个 `ast.parse`：语法检查通过。
- `python3 run.py plan`：正常输出阶段结构与未实现项。
- 两个不同 case 的私有 mesher 工作目录隔离、不同配置指纹、拒绝覆盖检查通过。
- 合成网格的 NPZ/CSV/report → prepare-fe 集成检查通过，壳厚、PBC equation 数和输出状态正确；没有生成或宣称存在完整 physical.inp。
- 原始 zip 与交付 vendor 内的 32 个原文件逐字节对照：完全相同。
- 论文补充材料中 Fig.S2 / Table S3 和 Table S6 的 PDF 页面已渲染核查；11 点位置与耗时表述录入方案。

## 14 项测试覆盖

1. X/Y 交角等价类消除冗余，并恢复全部原始仿射周期关系。
2. 不一致的周期闭环拒绝通过。
3. 代表节点位于 high 面时的负偏移符号。
4. 已知线性曲线的 11 点插值。
5. 不足 30% 的曲线禁止外推。
6. 惯性能量尖峰不被平均值掩盖。
7. 反力符号错误不被绝对值掩盖。
8. 应变回退不被排序掩盖。
9. 初始低内能区间的动能检查。
10. 正常接触误差残差不误判为 fatal，同时要求匹配 job 的完成证据。
11. 假网格契约、0/1 编号、CSV 及 prepare-fe 集成验证。
12. 两个 case 的网格配置与输出隔离。
13. 成功但极小增量的卡滞识别。
14. SQLite 重复领取、owner 和配置身份冲突检查。

## 没有执行，也没有声称通过

- CGAL/网格 00–07 的完整 Fig.1 回归（本次源码包未含实际网格和已编译 exe）。
- 真实 Abaqus Mesh/Physical Data Check。
- 真实 Fig.1 的 30% 非线性求解及手工模型曲线比对。
- Abaqus Python 对真实 ODB 的运行验证。
- n×n×n 拼接与周期镜像接触验证。
- Windows 进程树终止、掉电恢复、许可证等待及连续多日运行验证。

测试中的网格、位移、应力和能量都是明确构造的逻辑测试数据，不能作为论文复现结果。下一阶段的真实本机验证条件详见完整设计文档第 24–27 节。
