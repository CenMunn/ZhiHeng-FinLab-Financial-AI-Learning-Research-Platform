# M2.1 训练数据与环境准备实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 生成可追溯、标签隔离的 FinQA train/dev 清单、可信标注工作包和本机资源检查结果，形成 M2.2 的开训条件。

**Architecture:** 复用既有页内序列化与 BM25；离线准备分别输出推理输入、评分标签、隔离记录和划分。人工标签单独验证。环境检查不依赖 torch，CUDA 实算为显式选项。

**Tech Stack:** Python 标准库、unittest、现有固定 FinQA 快照；本轮不安装训练框架或下载权重。

**Spec:** `docs/research-roadmap.md` A 与 `docs/superpowers/specs/2026-10-14-platform-foundation-design.md` 1.1。

## Global Constraints

- 仅固定 commit 的 train/dev 和既有许可/来源文件；不读取最终测试或旧 heldout。
- 候选只从 pre_text/post_text/table 构造，gold 仅用于标签和评分。
- 未标注不等于负例；B3 必须有可信复核标签。
- 官方页内协议与自定义公司隔离诊断分开，不声称验证未见报告版本泛化。
- 用户已批准 M2.1，直接在当前独立研发目录 feature/m1-foundation 执行；保留服务、前端和存量数据。
- 本轮逐题人工阅读仍限既有固定60题；机器结构处理覆盖train/dev。标注包使用其中30个训练题。

## Review Focus

- 文件被改写/来源清单不符：拒绝准备，不静默重算来源hash。
- gold越界、重复题ID、空问题/标签：隔离并记录，不用负索引修补。
- 标签/答案污染推理输入：字段白名单及污染测试。
- 未复核、错误片段绑定、dev标签：拒绝进入训练负例出口。
- 驱动可见但CUDA算子未验证：环境状态保持未验证，不能报告可开训。

### Task 1: 固定清单与隔离

**Files:** `research/training/prepare_finqa.py`、`research/tests/test_training_preparation.py`。

**Interfaces:** `prepare(data: Path, output: Path) -> dict`；输出 `manifest.json`、`inference/{train,dev}.jsonl`、`labels/{train,dev}.jsonl`、`quarantine.jsonl`、`splits.json`。所有实际输出文件hash进入manifest。划分由问题ID生成，推理输入无gold/答案/程序。

- [x] 编写污染隔离、无效gold隔离、来源篡改拒绝、公司隔离、确定性重跑测试并观察失败（6项缺实现失败）。
- [x] 实现固定白名单来源验证、隔离与确定性输出；保留超过5个gold的问题。
- [x] 6项测试通过；真实结果6250 train、883 dev、1隔离；超过5个gold为34/7，均保留。
- [x] 更新实施记录与阶段提交。

### Task 2: 可信标注工作包

**Files:** `research/training/review_labels.py`、对应测试、`docs/research/2026-10-15-labeling-protocol.md`。

**Interfaces:** `make_review_queue(records, split) -> list[dict]`；固定既有训练先导30题，每题最多3个top20非gold候选，默认uncertain/pending。`validate_reviews(reviews, queue) -> dict` 按唯一绑定与复核信息导出训练用确认负例；完整候选仍是必要上下文。

- [x] 5项复核测试先因缺实现失败，再通过；覆盖未复核/不确定/support、绑定篡改、dev拒绝、重复与类型检查。
- [x] 实现工作包和验证；confirmed_conflict必须有reviewer、理由、类型，所有完成记录绑定原任务。
- [x] 生成30题90条任务，全pending，零确认负例；保持B3关闭。
- [x] 写标注规范、训练损失/指标推导与下一阶段接口，提交。

### Task 3: 环境检查与交付

**Files:** `research/training/probe_environment.py`、对应测试、准备报告与status/routing/log。

**Interfaces:** `assess(resources: dict) -> dict`；`probe(output: Path, torch_smoke: bool=False) -> dict`。默认仅资源/包版本检查；--torch-smoke才导入框架并验证CUDA前向/反向。

- [x] 4项环境测试缺实现失败后通过，覆盖缺torch、低/未知内存、CUDA未实测与小试条件。
- [x] 实现检查；记录时间、脚本hash、系统内存/显存/磁盘及未知项。
- [x] 实际运行并保存小型收据，核对官方兼容性来源；未安装框架，CUDA请求跳过。
- [x] 全部23项研究测试通过、真实重跑一致；独立审阅2项Important已补回归并修复；status与报告已更新。

## 执行记录

开始基线：1abb2a8，工作区clean。当前技能中的重复审批/新worktree建议由用户已授权逐步执行和现有独立研发目录解决，避免再启动一套环境。任务间接口依赖：1→2使用相同候选/序列化版本；1→3仅汇总清单，无训练耦合。实现记录保存在 docs/implementation-log.md；本计划复选框是当前任务账本。

最终审阅裁决：补充manifest身份校验与隔离前冻结先导ID；2项问题回归先失败后通过，另加1项已存在的隔离不替补行为测试。真实30题未变化，未扩大人工阅读范围。保留本地feature分支，不合并或推送。
