# D30 Filing Development Implementation Plan

> 执行用户已明确批准的三项工作；当前checkout保留既有未提交修改。按writing-plans、executing-plans和TDD执行，独立来源/人工包任务可按dispatching-parallel-agents分派；整体完成后做新上下文审阅。不自动提交、重置或新建worktree。

**Goal:** 在2024开发集真实比较单字段自由/有限约束输出，准备新公司封存报告及可填写的人工核验包，并恢复智投委可访问性。

**Architecture:** research/filing_development隔离证据、模型、准备与独立评分；API只读发布；前端在原D29记录旁展示开发改进。新公司只封存，人工包不含预填答案。

**Tech Stack:** 原研究Python/torch/transformers、固定Qwen、Decimal、原FastAPI/React18；无额外模型/解码库安装。

**Spec:** docs/superpowers/specs/2026-11-06-filing-development-design.md；参数research/configs/filing-development-v1.json。

## Global Constraints

- 只使用600519/600036/600585的2024Q1进行本轮模型开发和评分；原2025不重评。
- 输入前6页内确定性字段证据块，两种新方法相同；不以参考值筛选候选。
- 最大输入4096token、生成384token、引用160字符，BF16/batch1/seed0/greedy；输入不静默截断。
- 新评估000333/601318/600887各2025Q1只获取元数据与PDF字节，不打开内容或生成答案。
- 不修改D29冻结源码/产物，不训练模型、访问私有库或付费服务；D27任务和来源边界保留。

## Review Focus

1. 上期列换到首列、扣非与归母数值并存时，不能把首个数字当模型答案。
2. 脚注括号和括号负值区分；每股局部元单位不覆盖百万元表头。
3. 约束树合法性不等于正确；应保留错误选择、拒答和候选缺口，引用绑定真实位置。
4. 完整预测先冻结再评分；raw/token/结构化字段与已登记选项一致，来源不能重新认可变化。
5. 新公司不得进入开发输入/人工答案；人工空白表不能冒称审核完成。

## Tasks

### 1. 智投委运行恢复
- [x] 复现API offline与3155拒绝连接，定位两个子服务未运行。
- [x] 隐藏启动现有start_committee.mjs，健康与版本恢复ready。
- [x] 只读浏览器核对四子页、原品牌隐藏、窄屏；记录恢复收据，不调用AI/写账号库。

### 2. 开发隔离、证据和受限解码
Files: research/filing_development/{evidence.py,model.py,pipeline.py}; research/tests/test_filing_development.py。
- [x] 先写失败测试：所有列/扣非干扰、脚注/负数、单位、短引用、候选上限、JSON解析与前缀树/EOS。
- [x] evidence构建build_case(doc,metric)返回case_id/doc_id/metric/blocks/candidates/query；只消费公共2024文本。model暴露parse_field(raw,metric)、PrefixTrie、run_predictions(inputs_path,model_manifest,run_dir,generation)。
- [x] pipeline冻结开发输入/参考SHA/来源/配置/提示词代码和模型；运行两方法各9次，原始输出及token序列保存，freeze后才score/publish。初始全null保留，键序codec红→绿后以canonical-options新身份重跑。
- [x] 金额/单位/期间/范围/引用使用D29原冻结评分，另报格式通过与候选覆盖；所有失败计入9分母。最终约束完整5/9，含4项语义错选；free严格格式0/9。

### 3. 新公司封存与人工包
Files: research/filing_development/preparation.py; research/tests/test_filing_preparation.py。
- [x] 元数据身份/PDF签名/白名单/失败保留测试先行，再有界查询巨潮官方公告与PDF。
- [x] 输出初始清单并保留失败；修正官方组织身份、发行人题名与Q1同义标题后，另建qualified-metadata最终清单，3份sealed、content_accessed:false。旧initial/official-org-id保持原SHA，无正文读取/新模型评估。
- [x] 输出docs/research/human-review/2026-11-06/{checklist.csv,guide.md,manifest.json}：18空白核验项、原始链接、固定字段/单位/范围/物理页规范；完成/未完成/异议明确区分。
- [x] 输入人工表的核验函数拒绝缺金额/单位/期间/范围/证据、重复项和虚假completed；不覆盖原参考。

### 4. API与页面
Files: 新filing_development_store.py/api/filing_development.py、FilingDevelopmentPanel.tsx及API/CSS，测试各层。
- [x] 只读API验证发布摘要、固定开发身份、来源路径和分母；空/缺失/篡改明确返回，不执行模型。新增绑定预测/评分文件、精确D29基线及离线模型验证收据。
- [x] 使用Interactive-front-end复用深色绿金风格，展示旧基线/两种新方法、逐字段证据、9固定分母、候选覆盖及开发性质；提供报告/人工包下载。
- [x] 新评估只展示封存准备状态，无模型成绩。

### 5. 验收与交付
- [x] 研究/后端/前端适用全套测试及构建；226/198/94项全部通过，13组真实页面通过；桌面/375px及4错卡目视。
- [x] 新上下文审阅协议、数据隔离、受限输出与人工包；评分前资产复核P2已红→绿修复，927约束token及36行/4汇总独立审阅一致，无遗留重要问题。
- [x] 更新D30报告、status、AGENTS、README/skill路由与小型收据；D29身份保持，明确开发结果不代表泛化。
