# D31 财务语义校验 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax for tracking.

**Goal:** 解释并验证当期金额的来源列、单位和类型，完成开发及固定新公司对照。

**Architecture:** 独立结构解析、冻结推理与评分模块；只读 API/React 展示。D27 连接复查与研究完全隔离。

**Tech Stack:** Python Decimal、PDF 字词布局、固定 Qwen/CUDA、FastAPI、React18。

**Spec:** docs/superpowers/specs/2026-11-07-filing-semantics-design.md

## Global Constraints

- 不修改 D29/D30/D27 数值源码、旧结果、模型与校准；不读取账号库/FinQA保留集/.env。
- 开发仅原三公司2024Q1共9字段；method-freeze 之前不打开新公司正文。
- Qwen revision989aa7980e4cf806f80c7fef2b1adb7bc71aa306，BF16 batch1 seed0 greedy，4096/384token，quote160。
- 参考只由评分读取；新公司9项名单不按成绩替换；未知/歧义拒答。
- 本次使用当前共享 checkout，不自动提交/推送/部署；保留所有旧工作。

## Review Focus

1. 金额很小/负数/整数与百分数相似时按表头判断，不按数值大小。
2. 当前非首列、重述多级表头和表格跨页不靠模板固定索引。
3. 同名指标多个不同金额与合并/母公司混合时拒绝错误归并。
4. 模型/源码/预测/引用被更改时拒绝重新认可旧身份。
5. 请求失败/乱序与窄屏不能呈现旧公司/旧成绩为当前选择。

## Task 1: D27 独立复查
- [x] 验证锁、源/模型指纹；执行原有 pipeline 一次；校验来源和新计数，保存收据。

## Task 2: 结构解析与挑战测试
Files: research/filing_semantics/structure.py, research/tests/test_filing_semantics_structure.py。
Interface: build_cases(doc) -> list[case]；case 包含 query/blocks/candidates、eligible_ids 与 rule_field/reasons。输入 doc 的前6页与布局，不含参考。
- [x] 写并观察上述列/单位/扣非/歧义测试失败；实现来源绑定，运行新测试通过。
- [x] 在原2024公开PDF检查全部9字段，保存开发证据与 D30 四错误诊断。

## Task 3: 实验管线与方法冻结
Files: research/filing_semantics/{pipeline,model,corpus,score}.py, research/configs/filing-semantics-v1.json, research/tests/test_filing_semantics_pipeline.py。
Interface: prepare --corpus <split-manifest> --attempt <new> [--reference ... --freeze ...]；predict --run；score --run；freeze --run --challenges。每阶段校验原身份。
- [x] 先验证封存前评分/提前启封/篡改/覆盖被拒绝；实现阶段隔离。
- [x] 实际 GPU 开发预测、冻结、独立评分；保存完整 raw/token、模型校验与方法冻结收据。
- [x] 冻结后核验新三公司正文身份并制作独立视觉参考；固定输入/参考SHA；真实预测封存后评分，不再调方法。

## Task 4: 只读展示与交付
Files: backend/src/platform_app/{adapters/filing_semantics_store.py,api/filing_semantics.py,api/app.py}；apps/web/src/features/learning/FilingSemanticsPanel.tsx 与 helper/CSS/tests；scripts/verify_filing_semantics_browser.cjs。
- [x] API 正常/缺失/篡改测试先失败后通过；GET无推理/下载。
- [x] 页面新增来源列/排除原因/开发新公司对照、错误重试、导出；使用 Interactive-front-end。
- [x] 实际浏览器、完整测试/构建、独立审阅与修复；更新报告/status/边界与收据，不编造通过。
