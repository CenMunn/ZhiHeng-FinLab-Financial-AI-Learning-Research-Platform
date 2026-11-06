# D29 跨公司字段核验与规则/模型抽取 Implementation Plan

> 使用subagent-driven-development在当前feature/m1-foundation工作区分工实施，逐模块核验后做独立全链路审阅。用户已明确批准执行；保留既有未提交工作，不提交、清理或合并其他改动。

**Goal:** 建立六份公开季报的可追溯字段参考集，真实运行规则与固定本地模型并独立评分，向初学者展示正确项、失败项和证据。

**Architecture:** research/filing_extraction隔离来源/参考/输入/预测/评分；API只读发布和白名单PDF；训练页提供对照与导出。D28事件数学与D27前向任务保持不变。

**Tech Stack:** 现有Python3.12研究环境、Decimal、pypdf、torch/transformers、本地Qwen2.5-1.5B-Instruct；FastAPI和React18原依赖。

**Spec:** 用户本轮指令、D28报告下一切片及research/configs/filing-extraction-v1.json；平台总架构仍沿用2026-10-14规格。

## Global Constraints

- 固定600519/600036/600585各2024Q1(development)、2025Q1(evaluation)共6报告，三字段共18条；不因失败替换报告。
- 双方只用前6物理页相同文本，页号和PDF摘要保留；模型输入不静默截断。超过16384输入token记录失败。
- 目标当期合并/集团营业收入、归母净利润、经营现金流净额；数值原表单位，金额用Decimal。期间/范围已是查询约束，分项称口径一致性。
- 模型固定官方revision及safetensors摘要，batch1 BF16 greedy，输出上限1024；无付费API/训练/远程代码执行。
- 参考代理独立实际视觉核对；evaluation数值不发给实现者。参考集先封存，抽取原始预测先冻结，再评分；不把助手参考称专家金标。
- 权重与PDF在忽略的research/artifacts/filing-extraction；旧账号、M1、FinQA保留集禁读写。

## Review Focus

1. 百万元/元、括号负值、0/null和不同显示精度必须保留；禁止数值/页码跨变体拼接。
2. 当期/上期、总净利/归母、集团/母公司不能凭近似名称混用。
3. 正确页号但无关或伪造quote应失败；全文核对不自动证明前6页上下文充分。
4. 缺页、坏JSON、重复字段、超上下文、拒答都保留在固定分母，规则不能补模型答案。
5. 源、参考、提示词、输入、模型和预测更改后必须新身份；不能用重新计算摘要认可旧运行的变化。

## Tasks and Interfaces

### 1. 来源与独立参考

- [x] 新建acquire.py与test_filing_sources.py；先失败测试身份/名单/非法PDF，再实现有界官方获取。
- [x] corpus/v2/manifest.json只含6文档及来源字段；pages.json保留全文逐物理页文本，不含标签。v1旧目录副本含开发案例值，保留现场；v2已剔除。
- [x] reference/v2/references.json含18字段、预先核验(value,unit,page,quote)变体、上下文支持和23张已目视截图SHA。回报身份/数量，不披露evaluation值。

### 2. 固定输入、规则和评分（根任务）

- [x] common.py准备前6页公共inputs.json并校验源；rules.py仅基于给定文本抽取，合成测试覆盖不同量纲/负值/错列/缺单位。
- [x] score.py独立读取冻结预测及参考，输出数值/单位/币种/期间/范围/引用/完整正确计数，按split与方法保留原分母。
- [x] pipeline.py冻结配置、全部数值源码、参考SHA和输入；运行规则与模型后才评分发布，旧结果不覆盖。

### 3. 本地模型（模型代理）

- [x] download_model.py有界获取固定官方安全文件/模型卡/许可、LFS SHA；不安装依赖。真实断流及续传残片保留，9文件验证完成。
- [x] model.py暴露build_prompt(doc)、parse_output(raw)、run_model(inputs_path,output,model_manifest)，输入/输出/源码/模型SHA绑定；严格三字段JSON失败不补写。
- [x] 合成文本真实GPU smoke后，等待协议冻结，再实际运行全部6份输入并保留raw、token、耗时、显存与失败。smoke生成成功但格式无效；正式6份也全部invalid_output，原样冻结，不称抽取正确。

### 4. API与页面（界面代理）

- [x] filing_extraction_store/API GET目录和登记PDF；SHA/路径白名单/空和缺失状态测试先行。
- [x] 训练页新增FilingExtractionPanel，development/evaluation和公司联动，参考/规则/模型逐字段对照、原文和MD/JSON导出。使用Interactive-front-end。
- [x] 前端测试/构建，实际浏览器验证鼠标、键盘、窄屏/减少动画、失败重试和导出。81前端测试、10组真实浏览器通过；运行异常与普通字段缺失展示分开。

### 5. 验收与记录

- [x] 预测冻结后独立复核评分；36行/324检查/4汇总一致，97PDF页重提一致；6份完整提示词重建一致。无遗留Important/Critical；结果规则各9/9、模型各0/9，详见独立收据。
- [x] 跑适用后端/研究/前端完整测试、构建、实际浏览器；177/182/81测试、构建与10组真实浏览器通过。模型无效输出、下载断流、测试刷新竞态和真机未测均记录。
- [x] 更新D29报告、status、README、AGENTS与skill-routing，保留D27任务及旧成绩。

模型证据：[官方模型卡](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct)，[发布说明](https://qwenlm.github.io/blog/qwen2.5/)。方法参考：[TAT-QA](https://aclanthology.org/2021.acl-long.254/)和[FinQA](https://aclanthology.org/2021.emnlp-main.300/)，不把其基准成绩用于本项目的小样本宣称。
