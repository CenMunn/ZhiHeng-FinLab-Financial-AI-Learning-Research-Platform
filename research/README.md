# FinQA 独立训练与开发对照

D31新增独立`filing_semantics`，使用PDF布局绑定金额/比率/每股、当期/上期/调整列和原单位；原三公司2024开发9项规则/固定模型各9/9，但各只有一个合格候选，不能称AI增益。方法冻结后才启封美的/平安/伊利2025Q1，真实两方法各完整3/9、6拒答；未追调方法，助手视觉参考待人工审计。新公司现在已被评估，后续不能继续称未知封存；优先于下面D30当时的“仅封存”状态。详见[D31真实结果/命令/限制](../docs/research/2026-11-07-filing-semantics.md)，FinQA保留集及旧模型边界不变。

D30单字段开发实验另在`filing_development`，2024原三公司9字段：有限来源候选约束格式9/9、完整5/9，自由JSON仍0/9。只是冻结模型推理/候选语义选择，不是金融微调；新3公司报告仅封存，人工18项空白包可与工程并行。原始失败、codec修正和新身份详见[实际报告](../docs/research/2026-11-06-filing-development.md)，不得改动D29或FinQA保留集。

中文财报字段实验D29已独立实现于`filing_extraction`：三公司两年Q1三字段，规则/本地Qwen相同前6页输入，先冻结预测再读参考评分。开发/评估各9字段，规则完整正确各9/9，模型实际GPU运行但输出格式全部失败，各0/9；未金融微调、未改FinQA成绩或保留集规则。参考是助手视觉核对，待人工审计；见[实际协议、失败诊断与复现命令](../docs/research/2026-11-06-filing-extraction.md)。PDF抽取使用应用提供的独立运行环境，不向研究/应用环境临时混装包。

公开市场实验另行隔离：D28公告资格/事件回放见[实际方法与结果](../docs/research/2026-11-06-event-study.md)，D27冻结模型前向任务见[运行说明](../docs/research/2026-11-06-forward-market.md)，D26可执行区间训练/风险预算见[历史结果](../docs/research/2026-11-05-risk-budget.md)。使用同一独立研究环境，数据/产物与FinQA分开，原保留集限制不变。

此目录运行离线证据排序实验，不依赖平台API密钥，不修改backend/.venv或智投委依赖，不操作现有账号数据库。实验为英文给定页内排序；研究结果不自动替换中文线上模型。

## 环境和数据

本机使用Python3.12的research/.venv。安装验证完成后生成requirements-training.lock.txt；CUDA版torch来自官方cu128索引，不能将CPU wheel或驱动可见视为GPU训练通过。原模型为Apache2.0许可的cross-encoder/ms-marco-MiniLM-L6-v2，固定revision见configs/finqa-b012.json，7个文件均有上游blob/LFS和本地SHA校验。model.safetensors不启用远程代码、不加载pickle模型。

应用训练集、最终测试和旧比赛保留集严格隔离。只消费M2.1清单中的train/dev，数据准备结果按manifest校验，不能读取FinQA test/private_test。所有模型、输入、大型预测和checkpoint位于git忽略的artifacts，虚拟环境也不提交。

## 分阶段复现

在项目根使用research/.venv/Scripts/python.exe：

```powershell
research/.venv/Scripts/python.exe -m research.training.run_ranking bm25
research/.venv/Scripts/python.exe -m research.evaluation.audit_tokens
research/.venv/Scripts/python.exe -m research.training.run_ranking smoke
research/.venv/Scripts/python.exe -m research.training.run_ranking pretrained
research/.venv/Scripts/python.exe -m research.training.run_ranking train --seed 42
research/.venv/Scripts/python.exe -m research.training.run_ranking predict --seed 42
# 同样依次执行种子43与44；全部预测完成后单独评分：
research/.venv/Scripts/python.exe -m research.training.run_ranking summarize
research/.venv/Scripts/python.exe -m unittest discover -s research/tests
```

run_b012.ps1是本机完整顺序入口，核对已下载官方CUDA wheel的SHA后安装依赖、锁定环境，依次验证与执行所有阶段。它不会下载未知软件或调用收费服务。已有训练目录拒绝覆盖，部分失败保留原始日志；不要为重跑抹去失败记录。该入口会运行一次新的实验，不能拿来覆盖已完成的同名checkpoint。

下载位置、模型文件、输入清单和配置路径见configs/finqa-b012.json及实际收据；新机器先准备同一版本资产并按SHA核对，再执行。当前本机CUDA wheel文件名为torch-2.10.0+cu128-cp312-cp312-win_amd64.whl，官方SHA256为fbde8f6a9ec8c76979a0d14df21c10b9e5cab6f0d106a73ca73e2179bc597cae。

## 数学与边界

BM25在每页原始候选范围内计算IDF（k1=1.2、b=0.75），固定原文同分顺序后取top20。B1为已在MS MARCO训练、未经本项目FinQA微调的现成cross-encoder。B2从同一权重重新初始化，使用全部训练gold正例和BM25未标注弱负例，不把它们称为经金融专家确认的冲突。

微调目标为L=mean(softplus(z)-y*z)，每个logit的导数为(sigmoid(z)-y)/N。实现使用数值稳定的BCEWithLogitsLoss；累积窗口把每个微批的损失之和除以该窗口真实样本数，最后不足16个样本时不除以名义批量。AdamW、线性warmup/衰减和梯度范数裁剪配置固定。分数仅用于相关性排序，不作为企业风险或违约概率。

推理输入不加载gold标签；训练只读train标签；预测完成后评分进程单独读取dev标签。训练收据绑定训练时的输入、标签、准备manifest、底座模型acquisition和代码hash；预测同时核验checkpoint的config.json及safetensors，防止旧模型被套上新数据版本的成绩。

Coverage@5要求全部标注证据在前五内，漏召回和超过5gold的问题继续保留。报告CandidateCoverage@20、Recall、Hit、nDCG及公司代理组配对bootstrap。三个训练种子的波动与样本重采样不确定性分开，不把重复种子视为新增独立问题。官方dev不是最终盲测，公司/年度代理组重叠不代表已证明未见公司泛化。

金融冲突增强B3、公司外诊断和自然中文迁移另行开展；待人工复核的90条任务不会自动变成可信负例。运行中出现的失败、截断和资源限制均须保留，不保证金融微调一定优于预训练。

## 独立的市场收益预测（2026-10-30）

`research/market`现已实现A股/BTC四个简单预测基线、LightGBM及GPU DLinear三种子。与FinQA数据、目标和成绩分开；复用research/.venv但新增依赖单独锁在requirements-market.lock.txt。使用已有公开行情快照，不读取FinQA test/private_test/旧比赛保留集。

项目根运行：`research/.venv/Scripts/python.exe -X utf8 -m research.market.runner all`。先准备和真实小批，再训练/冻结预测，评分由单独进程读取评估标签。API只读取离线发布结果，不负责训练。参数变更生成新身份，拒绝覆盖不同产物。实际复杂模型未稳定超过零收益；完整协议、失败、实测和复现见[训练报告](../docs/research/2026-10-30-market-prediction-models.md)。

## 滚动验证与预训练对照（D21）

`research/rolling`保留D20原方法，扩展8季度滚动、8因果特征与4组消融、验证段块置换和label-free PSI；48个DLinear模型真实训练。后续接固定2024-03-27 Chronos-T5-tiny冻结编码器+训练段岭读出、随机T5同架构控制，只比较2025共同四折。不是零样本预测或基座微调，本轮两市场均未超过零基线。

依赖锁 `requirements-rolling.lock.txt`；项目根运行 `research/.venv/Scripts/python.exe -X utf8 -m research.rolling.pipeline all`，各阶段冻结指纹后单独评分。权重/缓存/大结果位于独立ignored目录，网页仅GET展示，既有FinQA边界不变。[完整协议、实际结果、修复与复现](../docs/research/2026-10-30-rolling-diagnostics-pretrained.md)。
