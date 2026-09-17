# Fig.1 20% 压缩算例（deck regression fixture）

**这是什么**：`work/fig1_solve_m3_20pct_003`（唯一真实完整跑完的 Fig.1 20% 压缩算例）的
10 个 deck 输入文件（`physical.inp` + 9 个 include）的 SHA256 冻结副本，用来回答一个问题：

> 修改代码或配置后，物理模型是否被无意改变了？

**这不是什么**：

- 不是"程序已验证 Abaqus 求解"的声明。真实 Abaqus 证据只在 git-ignored 的
  `work/fig1_solve_m3_20pct_003/`（`solve_report.json`、`.sta`、`.dat`、`.msg`、ODB）里。
- 不是通用默认值。`fig1` 只是一个 validation case。
- 不含 ODB/DAT/MSG/INP 等大文件，只存指纹。

## 文件

| 文件 | 内容 |
|---|---|
| `deck_sha256.json` | 10 个 deck 文件的 SHA256、mesh 来源文件的 SHA256、目标完成证据（step time / increment / warning 数）、ODB 身份（大小 + SHA256，仅作 artifact 身份） |

## 用法

```powershell
pixi run test
```

`tests/test_regression.py` 用 tracked config（`config/simulation.json` +
`config/cases/fig1.json`）重建 deck，并与本目录的 10 个 SHA 逐字节比较。本地没有
git-ignored 的 mesh bundle 时该测试会 skip（并明确标注），不会伪造 PASS。

## 规则

1. **不得为了让测试通过而更新本 fixture**。SHA 变化必须先判断是"有意修改模型"还是
   "无意回归"；有意修改必须单独说明原因，并重新做真实 Abaqus Data Check / solve 验证。
2. renderer 的生成注释也保持逐字节不变，否则注释改动会掩盖真实改动。
3. 本 fixture 只比较 deck 字节。它不判断惯性/准静态、接触、PBC 或科学质量。
