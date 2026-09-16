# Validation: 30 diverse surfaces

## 这是什么

本文件列出 **30 个周期隐式曲面方程**，它们是 30 曲面阶段性验证所使用的**测试对象**。

- 来源：原始数据集（**23,534 samples**）中挑选出的 30 个样本。
- 选择目的：**不是**统计意义上的 optimal subset，而是
  1. 用于 **Abaqus pipeline validation**（验证 mesh → build → Data Check 链路在不同曲面上的泛化能力），
  2. 同时覆盖**较丰富的 mechanical-response shapes**。
- 选择时的主要覆盖目标：`softening`、`hardening`、`early peak`、`plateau`、`re-hardening`、`multi-turning / oscillatory`。

## 溯源与验证（provenance）

- 原始整理稿为本地资料 `reference/selected_30_diverse_cases_report.md`
  （**git-ignored**，仍是 local raw archive；本文件是它的 tracked 精选版，二者内容一致）。
  该本地稿的 SHA256 为 `d42e946155ad61a1753a1bacfd76625a50b0bdeaca331426e85a8754a39d889b`，
  与实验目录 `work/night_batch_30surfaces_20260915/batch_source_manifest.json` 中记录的
  `source_sha256` **完全相同**。
- 2026-09-16 核对结果：本表 30 条方程与上述实验 manifest 的 30 条方程
  **集合与顺序完全一致（30/30）**；表内的 `dataset row`、曲线类型与响应数值均逐字取自原稿，未做任何修改或重算。
- 命名映射：本表第 N 行对应实验记录中的 `ref30_NN`（`diverse_01 ↔ ref30_01` … `diverse_30 ↔ ref30_30`）。
  该映射已按 `batch_status.json` 中的 `source_equation` 对全部 30 例逐一核对一致。

## 30 个 case（方程原样保留）

| ID | 数据集行(1-based) | 曲线类型 | 峰值应变(%) | 峰值 | 30%值 | 30%/峰值 | 曲面方程 |
|---|---:|---|---:|---:|---:|---:|---|
| diverse_01 | 8725 | 单调软化（低强度） | 1.6 | 15.691 | 4.031 | 0.257 | `-0.3*sin(2*X)+3.9*sin(Y)*sin(Z)+0.6*sin(Y)*sin(Y)-0.2 = 0` |
| diverse_02 | 1689 | 单调软化（较高强度） | 1.6 | 31.859 | 8.201 | 0.257 | `2.9*sin(2*Y)+4.0*sin(Y)*cos(Z)+1.5*sin(X)*sin(X)-0.7 = 0` |
| diverse_03 | 397 | 单调硬化（低强度） | 30.0 | 17.072 | 17.072 | 1.000 | `1.3*sin(2*Z)-5.6*cos(X)*cos(Y)-5.6*cos(X)*cos(Z)-1.0 = 0` |
| diverse_04 | 1439 | 单调硬化（高强度） | 30.0 | 58.723 | 58.723 | 1.000 | `-2.6*sin(Z)-4.5*sin(X)*cos(Y)-0.1*cos(Z)*cos(Z)+1.8 = 0` |
| diverse_05 | 19230 | 极早峰值，强软化 | 3.1 | 26.519 | 5.769 | 0.218 | `0.6*sin(2*Z)-4.6*cos(Y)*sin(Z)+0.8*sin(X)*sin(X)-0.4 = 0` |
| diverse_06 | 18631 | 极早峰值，高强度软化 | 3.1 | 62.474 | 24.904 | 0.399 | `-4.8*cos(X)*cos(Y)-1.7*sin(Y)*sin(Z)-0.9*cos(X)*cos(Y)*cos(Z)-0.5 = 0` |
| diverse_07 | 11289 | 极早峰值，中高强度软化 | 3.1 | 54.242 | 23.923 | 0.441 | `5.5*sin(X)*cos(Z)+5.6*sin(Y)*sin(Y)-3.3 = 0` |
| diverse_08 | 13766 | 早峰后软化并回升 | 3.1 | 59.109 | 30.655 | 0.519 | `-4.0*cos(2*Y)-5.2*cos(X)*cos(Z)+0.7*cos(Y)*cos(Y)+0.1 = 0` |
| diverse_09 | 16916 | 5.5%峰值，强软化 | 5.5 | 37.255 | 12.449 | 0.334 | `-1.7*cos(X)+5.7*cos(X)*cos(Z)-3.1*sin(X)*cos(Y)+1.1 = 0` |
| diverse_10 | 22529 | 5.5%峰值，中高强度软化 | 5.5 | 49.309 | 22.237 | 0.451 | `-4.5*cos(2*Y)-4.3*cos(X)*cos(Y)-5.4*cos(X)*cos(Z)-0.6 = 0` |
| diverse_11 | 13813 | 5.5%峰值，中等软化 | 5.5 | 37.032 | 17.665 | 0.477 | `5.8*cos(X)*cos(Z)-3.7*sin(X)*sin(Y)*sin(Z)-1.1 = 0` |
| diverse_12 | 15181 | 5.5%峰值，较高平台/软化 | 5.5 | 44.501 | 23.967 | 0.539 | `-3.4*cos(X)*sin(Y)+5.0*sin(X)*cos(Z)+2.6*sin(Y)*sin(Y)-1.1 = 0` |
| diverse_13 | 20313 | 5.5%峰后明显再硬化 | 5.5 | 57.027 | 34.618 | 0.607 | `4.4*cos(Y)*cos(Z)-5.0*sin(X)*sin(X)+1.7 = 0` |
| diverse_14 | 21102 | 5.5%峰后强再硬化 | 5.5 | 39.290 | 28.876 | 0.735 | `-3.6*cos(Y)-0.3*cos(2*Z)-5.6*sin(X)*sin(Z)-0.2 = 0` |
| diverse_15 | 11346 | 5.5%峰后轻微回升 | 5.5 | 38.815 | 26.188 | 0.675 | `5.3*cos(X)*cos(Y)*cos(Z)-2.5*sin(X)*sin(Y)*sin(Z)+1.2 = 0` |
| diverse_16 | 18776 | 9.4%峰值，强软化 | 9.4 | 27.075 | 11.825 | 0.437 | `1.0*sin(X)-4.8*cos(X)*cos(Y)+3.9*cos(Z)*cos(Z)-1.1 = 0` |
| diverse_17 | 5286 | 9.4%峰后轻微回升 | 9.4 | 21.517 | 10.393 | 0.483 | `-0.4*cos(X)-2.3*cos(2*Z)-4.1*sin(X)*sin(Y)+0.9 = 0` |
| diverse_18 | 8935 | 9.4%峰后轻微回升（中强度） | 9.4 | 35.626 | 17.751 | 0.498 | `5.6*sin(X)*sin(Y)+0.7*sin(Y)*sin(Z)+3.3*cos(Z)*cos(Z)-0.2 = 0` |
| diverse_19 | 16044 | 9.4%峰值，高强度软化 | 9.4 | 50.947 | 25.629 | 0.503 | `-2.2*cos(X)*sin(Z)-2.5*sin(X)*sin(Y)+0.9*sin(X)*sin(Z)-1.7 = 0` |
| diverse_20 | 12040 | 9.4%峰值，中等软化 | 9.4 | 28.440 | 17.534 | 0.617 | `2.0*sin(Z)+2.5*cos(Y)*cos(Z)-5.3*sin(X)*sin(Y)*sin(Z)-1.0 = 0` |
| diverse_21 | 18677 | 9.4%峰值，低强度软化 | 9.4 | 21.650 | 13.554 | 0.626 | `3.5*cos(Y)*sin(Z)+2.1*sin(X)*cos(Z)+2.1*cos(Z)*cos(Z)-0.5 = 0` |
| diverse_22 | 9418 | 9.4%峰值，较高保持率 | 9.4 | 33.988 | 25.953 | 0.764 | `3.4*cos(X)*sin(Z)+4.8*cos(Y)*cos(Z)+2.1*sin(X)*sin(Y)+2.4 = 0` |
| diverse_23 | 13092 | 9.4%峰后回升 | 9.4 | 33.033 | 28.043 | 0.849 | `3.2*sin(X)-5.9*cos(Y)*sin(Z)+2.0 = 0` |
| diverse_24 | 17547 | 9.4%峰值，低强度近平台 | 9.4 | 17.702 | 15.291 | 0.864 | `-0.4*sin(2*Y)+5.5*sin(X)*sin(Y)-5.8*sin(Z)*sin(Z)+0.5 = 0` |
| diverse_25 | 12718 | 9.4%峰值，近平台 | 9.4 | 28.347 | 26.265 | 0.927 | `5.3*cos(X)*sin(Z)-5.9*sin(Y)*cos(Z)+1.2*sin(X)*sin(Y)*sin(Z)+3.4 = 0` |
| diverse_26 | 2780 | 多转折/振荡型 | 9.4 | 30.469 | 23.015 | 0.755 | `-2.9*cos(X)*cos(X)-4.9*cos(Y)*cos(Y)+5.3*cos(Z)*cos(Z)+2.1 = 0` |
| diverse_27 | 19104 | 显著软化后再硬化/多转折 | 9.4 | 22.765 | 18.253 | 0.802 | `-2.8*cos(2*Z)-5.4*sin(X)*sin(Y)-1.8 = 0` |
| diverse_28 | 19195 | 5次斜率反转的振荡型 | 9.4 | 30.849 | 28.323 | 0.918 | `-3.4*cos(X)*cos(Z)+4.6*sin(X)*sin(Y)*sin(Z)+2.0 = 0` |
| diverse_29 | 16740 | 深软化后强回升 | 9.4 | 54.740 | 53.882 | 0.984 | `-2.4*cos(Z)-3.1*cos(X)*cos(Y)-0.3 = 0` |
| diverse_30 | 15908 | 晚峰值/近平台型 | 22.7 | 29.934 | 29.654 | 0.991 | `-5.0*sin(Y)*cos(Z)-4.8*sin(X)*sin(Z)+3.9 = 0` |

## 重要 caveat（使用这些数值前必读）

> 原始 dataset 中的 stress-response 数值（峰值应变 / 峰值 / 30% 值 / 30%/峰值）只作为这些 case 在**原始论文数据集中的参考标签**。
>
> 当前 `auto_abaqus2609` 使用的是 **validation / surrogate material setup**，**并没有**完整复现论文原始材料本构。
>
> 因此**当前项目重新计算得到的 stress-strain curves 不应被要求与 dataset 中的数值逐点一致**。

同时：

- 这 30 个方程的 **X / Y / Z 约定与当前项目一致**，即当前 periodic implicit surface expression convention；
  `surface_expression` 可直接作为 `config/cases/*.json` 中的隐式曲面表达式使用。
  （实验记录会剥离曲面表达式尾部的 “= 0”；本表按原稿风格保留该尾部。）
- 本表**只描述"测试对象是什么"**。实际运行了什么、结果如何，见
  `docs/EXPERIMENT_30_SURFACES_20260915.md`；本地原始运行证据在 `work/`（git-ignored）。

