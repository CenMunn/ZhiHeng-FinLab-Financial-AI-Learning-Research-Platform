# 研究数据与实验边界

遵循项目根 AGENTS.md 与 docs/research-roadmap.md。

2026-11-07 D31用户批准财务语义校验；research/filing_semantics的14来源/配置/规格已冻结，method-freeze SHA75c2b5ac166c81cfee9f22f2de3d8739278aff2dd17e82a96370c201b650d0d4。开发2024九项规则/模型各9/9，单合格候选，无已证AI增益。新三公司2025Q1已在freeze后启封，独立视觉参考与实际评估完成，两方法均3/9、6拒答；现在禁止再改本轮方法或将其重新当未读样本。输出先封存再评分，参考助手待人工审核，期间/范围是查询，结构保证不算模型能力。旧D29/D30/D27代码/结果不动，FinQA和原库边界保留。详见D31报告。

2026-11-06 D30：用户明确审核与工程可并行，`research/filing_development`独立只做原三公司2024开发9字段。新两方法共用字段证据块，候选不按参考剪裁，保留上期/扣非/比率；固定输入4096/生成384token、引用160字符、BF16 batch1 seed0。原三字段整篇D29不修改；新2025公司仅封存字节，不提取/标注/预测。canonical-options协议与15来源、参考、模型/输入、完整token和raw先冻结，再评分；codec键序修复另身份重跑，初始失败保留。当前约束格式9/9、完整5/9；不要称未知泛化、专家金标或金融微调。离线推理前后/评分前验证权重，API只验归档收据，历史可用不等当前可推理。人工18空白项在docs/research/human-review/2026-11-06，返回另存；validator只认证格式完整性。源码变更新attempt/身份，不追改已封存结果。新公司后续先固定协议再开封。详见D30报告，旧FinQA保留集/账号/M1及D27边界保留。

2026-11-06 D29：`research/filing_extraction`固定三公司两年Q1三字段，2024开发/2025评估各9条；使用独立corpus/v2与reference/v2，旧v1和失败下载现场保留。两方法严格相同前6物理页，公开输入不含参考；Qwen2.5-1.5B-Instruct固定revision989aa7980e4cf806f80c7fef2b1adb7bc71aa306、安全权重与LFS SHA，GPU BF16 batch1 greedy，输入16384/输出1024，不截断输入、不调用付费API。prepare冻结8源码（含research/market/common.py）、输入、配置、模型与参考身份，predict只读公共输入，freeze-predictions后publish才消费参考。格式失败不由规则修补、不从分母删除。参考为助手视觉核验，待人工复核；同公司跨年、给定查询口径与输入上下文缺口都必须披露。源/预测/方法变更使用新身份，保留旧输出，不能看到2025结果后追调本轮方法。产物仅research/artifacts/filing-extraction与backend/data/filing-extraction；详见D29报告。FinQA保留集、D27冻结模型与任务、旧账号/M1边界不变。

2026-11-06 D28用户批准公告资格审计与单事件教学回放。research/event_study只消费公开上交所目录、固定茅台2024Q1官方PDF及D24冻结三公司行情/日历，另获取沪深300价格指数。产物限定research/artifacts/event-study与backend/data/event-study；来源、派生值重建、视觉核验和5份源码身份绑定，旧版本/失败目录保留。目录按公告发布日期2024—2025，38条中只有1份全文案例完成；日期精度不能宣称PIT首次时刻。110日OLS与AR/CAR只描述关联，无模型抽取或准确率。智投委Fact只兼容公开证据导出，不操作其私有库。后续先准备预定跨公司核验集再比较规则/模型；详见D28报告。D27任务、冻结模型和FinQA保留集边界保持。

2026-11-06 D27用户授权新行情、冻结模型逐期记录和到期验证，并选择每天北京时间08:10/16:10自动运行。research/forward_market独立读取D26最新时间折2025Q4，冻结权重/尺度/校准与完整EWMA历史；data有界获取2025-12-15至今原价/事件/官方日历，所有真实接收时间和原字节摘要保留。journal预测先于入场，signal>=2026-11-06，退出完整日线收到后独立settle，重复调用不覆盖；来源/模型改变拒绝，不倒填历史。pipeline一次有界运行，状态发布backend/data/forward-market，产物仅research/artifacts/forward-market；任务automation-2已ACTIVE。当前真实0预测/0结果，联调不算前向成绩。先读D27报告；不得为自动任务改模型、训练、清未知锁、回填错过窗口。源码变更新协议保留旧版本，同日跨协议非独立样本。FinQA/旧库禁读写边界保持。

2026-11-05 D26用户批准可执行区间/风险预算及前瞻日志机制。research/risk_budget独立重训开盘持有目标（A股signal+1/+2开盘，crypto+2/+3），60个成熟open→open输入，固定D24来源与四角色。40单元120CUDA模型已完成；evaluation仅独立score读取，inputs/冻结模型/源码SHA不可重新认可变更，部分失败新attempt保留现场。experiments/risk_budget.py是Decimal领域账本，API预览只重放不训练；新产物仅research/artifacts/risk-budget与backend/data/risk-budget-runs。八策略、目标10%和0/1/2成本均固定，不按收益挑参；不要把较低仓位当AI优势。shadow目前仅注册和只追加验证，2026-11-06起pending/0记录，未接实时数据与推理，不倒填历史为前向结果。详见D26报告，旧FinQA/账号/M1边界不变。

2026-11-05 D25用户授权5合格标的有限模型对照。research/five_asset只消费固定D24归档report_id与876来源，独立root research/artifacts/five-asset，发布backend/data/five-asset-runs。80单元/240CUDA模型已实际训练，4角色严格隔离；calibration标签在模型早停完后读取，evaluation标签仅独立score，校准原始预测/系数、模型/输入/源码字节归档冻结。源码/环境变更新身份，不重贴旧成绩，部分失败用新attempt保留。API只读，资格源按归档ID重开，不用最新报告替换旧输入；请求内局部去重校验不跨请求持久缓存。历史已研究/逐标的重训不等盲测或零样本迁移。读D25报告后继续下一阶段风险预算；FinQA/旧库边界保持。
2026-11-05 D24用户授权多标数据资格和独立校准协议。research/validation_foundation独立采集固定7候选与准备四段，不改旧PublicDataset Literal或结果；ETH使用新crypto标识。数据/产物只在research/artifacts/validation-data及validation-foundation，摘要backend/data/validation-foundation；全部候选含失败保留，unsupported splits/missing不填补。protocol-freeze与不可变采集/规范化清单、来源链/数据SHA绑定；train/early_stopping/calibration/evaluation各司其职，评估标签另存。当前完成准备无新训练；2026-11-06前瞻仅预留等待真实观测，无自动采集/交易。具体名单/边界读D24报告。FinQA与旧库限制保持。
2026-11-05 D23用户授权校准、失败区间和样本覆盖。research/volatility_diagnostics独立只读已校验D22记录及原冻结train/validation/evaluation_features/预测；仅validation拟合比例，不能评估调系数/挑窗口。新产物research/artifacts/volatility-diagnostics和backend/data/volatility-diagnostics，immutable versions保留旧诊断，最新指针原子更新；不改D22源码/输入/成绩。覆盖是现有单股/单币审计，未扩样；成员次数/标签不重叠不等独立样本，30条非统计功效标准。API只读不导入训练，FinQA/旧库禁读边界保持。详见D23报告。
2026-11-04后续用户明确“继续完成”，已补齐D22实际页面及独立审阅验收。新波动管线训练前inputs.json与逐折completed.json必须绑定输入/预测/收据/模型；部分失败使用新--attempt，不覆盖现场；递归模型资格检查全历史前缀。旧4组产物原身份保留，已用修正代码重建标签/指标完全一致，无新训练；旧版评分需原源码，不能改其来源清单以接受新代码。风险预算为下一阶段，详见D22报告最新验收段。

2026-11-04 D22：用户授权波动预测/市况稳定性及自主后续至当日北京时间15:20，该时间窗口已结束。现有research/volatility读取同两份公开快照，日线未来1/5期收益平方均值作为二阶矩代理，不能称高频实现方差。产物仅research/artifacts/volatility与backend/data/volatility-runs，不改写D20/D21。实际四组完成，但真实结果浏览器及独立审阅待补；后续先读docs/research/2026-11-04-volatility-stability.md，不把当前报告当作继续无限自主训练的授权。FinQA保留集限制保持。

2026-10-30用户授权先滚动验证/特征诊断再接预训练（D21）：允许在research/rolling读取已有两份公开市场快照，使用research/.venv与GPU离线训练/嵌入/独立评分；允许获取固定Chronos-T5-tiny的README/config/generation_config/safetensors及许可/哈希元数据（revision129a2d204d6ab4205a0049a160402deefaf161b2），不执行远程仓库代码。大产物仅research/artifacts/rolling与rolling-model，发布结果仅backend/data/rolling-runs，小型审计收据docs/research。此授权不解除下面FinQA保留集限制。阶段清单必须绑定模型与缓存，2025预训练对照同样本且保留随机编码器控制，不能将监督读出描述为零样本。详见D21报告。

2026-10-30用户进一步授权两市场预测基线、LightGBM/DLinear：可以只读backend/data/public-market登记的两份公开快照，离线准备/训练/推理/评分，使用research/.venv与已授权NVIDIA GPU。产物独立于FinQA，放research/artifacts/market-forecast；只读展示包可写backend/data/forecast-runs。训练仅train/validation、预测不读evaluation_labels，最终评分进程才读取该文件。下面FinQA白名单限制继续适用于FinQA，不能套用为本轮公开市场数据禁止令，也不能反向解除FinQA保留集禁读。

- 当前允许获取与开发的是固定版本 FinQA 的 train.json、dev.json、README、LICENSE，以及用于核对序列化的官方代码文本；不执行下载的上游代码。
- 不获取、不读取 test.json、private_test.json 或既有 corporate-risk 保留集。文件列表元数据不等于读取测试内容。
- profile 和 M2.1 准备可以对全部 train/dev 做机器结构处理；逐题内容人工检查仍限于原固定抽样 60 题，标注包只使用其中30个训练题。不把开发先导统计称为最终效果。
- 未标为 gold 的证据只是未标注候选，不自动作为已确认负例。候选序列化只从 pre_text/post_text/table 构造，不能使用 gold 文本、model_input、答案或推理程序。
- 研究数据与大产物在 .gitignore 中排除；保留固定 commit、来源 URL、文件 hash、脚本与小型审计结果。
- M2.1只做资源与数据准备。2026-10-30用户已授权M2.2：在research/.venv配置独立环境，下载固定公开模型、安全权重与许可元数据，实测小批前向反向并开展B0/B1/B2。不使用付费服务，不改动应用依赖；B3仍等待可信人工冲突标签，不把驱动可见当CUDA算子已验证。

2026-11-07 D32独立filing_semantics_v2已冻结SHA8397b17b86fa72fe71a4819a4d1e05ac8cfeb32b11aeab0538c2d1a67123cdd6，勿改其研究14源/config/spec。已见开发六报告18字段真实规则/固定Qwen各15/18、3美的币种拒答，无AI增益。000651/601166/600900各2025Q1仅在freeze后开封，独立视觉参考与真实评估已完成，两方法均4/9、5拒答（格力3币种未知、兴业2跨页表头/单位），无AI增益，不据成绩调方法；恒瑞因freeze前搜索摘要暴露已排除并留记录。旧D31十四来源逐项未变，账号/FinQA/D27不动。见docs/research/2026-11-07-filing-semantics-v2.md。
