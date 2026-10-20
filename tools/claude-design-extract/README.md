# claude-design-extract

从 Anthropic Claude Design 桌面端的线上 bundle 中抽取系统提示词与内置技能注册表。

这个目录只包含**工具、清单与验证报告**，不包含抽取出的正文。

## 为什么有用

`skills/baoyu-design/references/upstream-sync/built-in-skills.json` 记录的是 2026-09-14 那一版构建。Anthropic 在同名文件上重建过 bundle（字节数从 1,685,062 变成 1,356,800），因此旧清单里的一部分技能 id 已经不存在，同时又出现了新的 id。这个工具可以针对任意一版 bundle 重新生成清单。

## 用法

```bash
curl -sS --compressed -o an2.js \
  https://assets-proxy.anthropic.com/design/v2/assets/v1/desktop-auth-wait-BFZPsTr6.js
sha256sum an2.js
# 368344ed3ca2901b105a081714f56aa3dc805e22d41da7c64f7767cb2f816cb2

CD_ROOT=. python3 extract-skills.py     # 生成 skills-current.json + eval2.cjs
```

脚本会打印 `skills N defs M` 与每条技能的名称/长度，`skills-current.json` 含 `prompt` / `dcPrompt` 正文。

## 方法

1. 定位 `var FA=[...]` 注册表（40 项）。
2. 逐条解析 `prompt` / `dcPrompt`：字面量、变量引用（`` Z`...` `` / `Bk([...])`）或 getter。
3. 只解析被引用的定义，在 Node 沙箱中求值（`with(Proxy)` 兜底、依赖拓扑排序、未定义标识符渲染为空串）。

## 踩过的坑（都会导致静默错误）

| 症状 | 根因 | 修法 |
|---|---|---|
| 正文为零 | 模板内嵌套模板 `${`…`}`，跳过逻辑把内层反引号当结束符 | 递归 skip |
| 大批定义被当成“字符串内” | 正则字面量里的引号被当作字符串起点，遮罩污染 76% 文件 | 识别正则字面量 |
| 正文被 join 成数组 | `Z` 是 tagged template，不是普通函数 | 实现真实语义 |
| 某条技能短了一大截 | 包装函数自带前缀，被本地 stub 覆盖 | 用 bundle 内真实定义 |
| 出现 `undefined` | 定义初始化存在前向依赖 | 依赖图拓扑排序 |
| 出现 `function(){}` | 未解析标识符参与模板插值 | 空串兜底 + 可调用 Proxy |

## 覆盖（2026-10-20 构建）

- 40 个注册项，38 个取得 `prompt` 正文，合计 194,681 字符。
- 3 个 `dcPrompt` 变体，合计 3,687 字符。
- `tweaks-protocol` / `low-level-tweaks-api` 的 `prompt` 分别是 `k` / `N`，这两个名字在该 bundle 内没有绑定，且两项都 `hidden:!0` —— 死条目。

## 验证

与 2026-09-14 快照做 8-gram shingle 包含度比对：29/53 个旧文件在 ≥85% 上 1:1 对应，中位数 86.7%，最高 99.4%。低覆盖项长度差异大且结尾完整，属于改版而非截断。

## 授权

抽取内容版权归 Anthropic 所有。本目录不含正文，仅提供方法与清单。
