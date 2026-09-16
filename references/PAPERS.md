# Papers

## Primary paper（主要科学来源）

**Li Zheng, Siddhant Kumar, Dennis M. Kochmann**
*Algebraic language models for inverse design of metamaterials via diffusion transformers*
**Nature Machine Intelligence**, Volume 8, 2026, pages 628–640
DOI: [10.1038/s42256-026-01218-8](https://doi.org/10.1038/s42256-026-01218-8)

这是当前 DiffuMeta 复现工作的**主要科学来源**：本项目要建立的是一条"曲面方程 → 周期网格 → Abaqus 物理模型 → Data Check → Solve → ODB 提取 → 力学 QA → 标准化结果"的自动化科研流水线；该论文提供了问题来源（周期隐式曲面超材料的设计空间与力学响应数据）与参考建模约定。

## 本项目从该论文 / 补充材料中使用的部分

- **periodic implicit shell design space**：周期隐式曲面所定义的单胞壳设计空间
- **Fourier-type implicit equations**：以三角函数（Fourier 型）表达的隐式曲面方程
- **10 × 10 × 10 mm unit cell**：单胞尺寸约定（本仓库 Fig.1 验证案例为 L = 10 mm）
- **S3R shell FE modelling**：Abaqus 中 S3R 三角形壳单元的建模方式
- **target relative density**：以目标相对密度控制等效厚度
- **rigid-plate compression**：两块刚性压板之间的单轴压缩
- **lateral periodic boundary conditions**：横向（X/Y）周期边界条件
- **General Contact / nonlinear compression context**：General Contact 与非线性压缩分析背景
- **30% nominal compression in original work**：论文原始工作中的 30% 名义压缩量
- **11 stress-strain sampling levels**：论文以 11 个应变水平采样应力–应变响应
- **DiffuMeta / diffusion transformer inverse-design context**：该论文的扩散 Transformer 逆向设计框架（本项目**不**实现该深度学习部分，仅复现其仿真/数据生成侧的工作流）

## 11 个应变采样水平（来自论文 Supplementary Table S3）

| # | strain |
|---:|---:|
| 1 | 1.6% |
| 2 | 3.1% |
| 3 | 5.5% |
| 4 | 9.4% |
| 5 | 14.9% |
| 6 | 16.5% |
| 7 | 20.4% |
| 8 | 22.7% |
| 9 | 26.7% |
| 10 | 28.2% |
| 11 | 30.0% |

> 上述 11 个数值来自论文 **Supplementary Table S3**（不是本项目自己的测量或标定结果）。

## 重要范围声明

- 本项目**不**声称逐项复制论文的全部建模细节：材料本构、压缩目标、单元/接触/输出等设置以本仓库当前的 config 与文档为准（见根目录 `README.md`、`docs/PROJECT_STATUS.md`）。
- 本项目当前使用 **validation / surrogate material setup**，并未完整复现论文的原始材料本构；因此由本流水线得到的应力–应变曲线**不应**被要求与论文或数据集中的数值逐点一致。
- 论文正文与 Supplementary PDF **不随本仓库分发**。

> Publisher PDFs are not redistributed in this repository. Readers should obtain the article and Supplementary Information from the DOI / publisher.

本仓库**不包含**（且不得提交）以下文件：

- `s42256-026-01218-8.pdf`（论文正文）
- `42256_2026_1218_MOESM1_ESM.pdf`（Supplementary Information）
