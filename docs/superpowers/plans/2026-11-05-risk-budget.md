# D26 可执行区间对齐与风险预算教学

执行收据（2026-11-05）：单标的切片后扩展5标的，40单元/120CUDA网络/70,663次更新、独立评分和120账户已完成；来源、输入、模型、源码冻结。API/UI与实际10组Edge验收完成，148后端/107研究/57前端和构建通过；独立复审无剩余Important/Critical。前瞻仅注册/只追加验证完成，未连接实时源/推理，0预测/pending。详细实际结果与限制见 `docs/research/2026-11-05-risk-budget.md`，下文保留实施前协议，不用结果改写参数。

用户批准上轮建议：先单标的最小切片，再扩展现有5合格标的，前瞻建立日志机制。使用writing-plans/subagent-driven-development/TDD/Statistical Analysis/Interactive-front-end/独立审阅。当前feature工作区复用、旧数据/成绩不改；无实盘、付费API或自动任务。

## 冻结实验

来源固定D24归档validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c，5标的600519/600036/600585/BTCUSDT/ETHUSDT，2018–2025，原四段/8季度边界保留。本轮只预测一个可交易持有区间，不复用D25收盘收益标签或旧权重。

信号bar_i close_at+1分钟决策；A股entry=i+1开盘、exit=i+2开盘，crypto entry=i+2、exit=i+3（下一UTC开盘已过去）。严格decision<entry<exit。目标log((open_exit+div_exit)/open_entry)^2，排除入场日分红；标签保守以exit完整bar.available_at成熟。输入为60个已成熟的同口径历史open→open对数总收益u_j=log((open_j+div_j)/open_(j-1))，只用j<=i并要求整个prefix fullbar available<=decision；不偷看尚未完整发布的后续bar.open。目标是u_(i+lead)^2，Alead2/crypto3。已知但未使用的当前intraday变化不补成未来信息。

模型train_mean、EWMA .94、LightGBM Gamma、DLinear种子17/42/2025+固定均值，7输出；无GARCH/h5扩展，聚焦风险预算。训练仅train/缩放，early_stopping选停止，模型确定后calibration独立比例mean(y/p)clip[.25,4]，evaluation标签仅独立score。神经30epoch/patience6/batch64/lr.001，树200轮/patience20，不按新结果调参数。40单元120CUDA种子。预测、c、输入、源码、环境、来源SHA冻结；部分失败保留并新attempt。

## 执行引擎约定

纯Decimal账户，单标的独立，不混币种。A初始1000000CNY，crypto100000USDT，现金利率0，目标年化10%默认/可预览5%–30%，杠杆/做空禁止，权重min(1,target/sqrt(max(var,1e-10)*252或365))，调仓缓冲绝对5个百分点。订单在entry开盘按当时权益/已知open计算数量，是日线近似成交，不承诺竞价可实现。

策略8个：hold_full（同eligible日历/季度边界固定满仓）、fixed_risk（训练均方决定的季度固定风险仓位，防止把少持仓误当AI优势）、ewma_raw/ewma_calibrated、lightgbm_raw/lightgbm_calibrated、dlinear_raw/dlinear_calibrated。所有用同一现金/费用/日期规则。

季度最后eligible行exit日尝试清仓；没有新入场信号的purged/gap日目标现金。拒单时保留真实仓位/风险，不假设已清仓，连续本金不按季度重置。日线只用执行open、前已发布close/当日已发生分红做保守10%边界过滤，不用当日high/low/volume判断已成交（避免日内未来泄漏）。A买入100股整手、卖出不超过旧仓，T+1限制；crypto教学step BTC .00001/ETH .0001，非历史交易所过滤器认证。分红ex日按开盘调仓前持股计不可再投应收，不提前支付/计税。滑点作为单独现金成本，不同时改成交价以免重复扣费。

教学费用A佣金3bps/min5，卖出税5bps、过户.1bps、滑点2bps；crypto佣金10bps/min0、税/过户0、滑点2bps。固定区间假设，不冒充历史法定/券商费率。0/1/2倍成本敏感性，固定预测/参数重算账本，不重新拟合。

估值和风险指标统一开盘账户曲线（含当时成交费和已发生分红应收），不能把close曲线收益冒充预测持有区间。指标return/max_drawdown/costs/turnover/exposure（金额Decimal字符串）、annualized_volatility（净简单收益样本SD×sqrt annual）、target_error_abs、rolling20_volatility_rmse、最差20期、费用/拒单/每日cash/qty/receivable/actualweight。现金日期也保留，全期风险偏差含边界现金的实际影响，不挑只持仓日期。年化风险是估计、20窗口重叠非独立；未宣称VaR校准/收益保证。

## 模块与分工

- engine任务 owns backend/src/platform_app/experiments/risk_budget.py + backend/tests/test_risk_budget_engine.py。函数 simulate(dataset:plainD24,observations:list, strategy:str,target_volatility:str='0.10',cost_multiplier:int=1)->{metrics,curve,trades,rejections,config}。observations含 signal_session,decision_at,entry_session,entry_at,exit_session,exit_at,fold,raw:{model:var},calibrated:{model:var}。fixed_risk用raw.train_mean。engine不得读取realized_variance/未来收益决定交易。API调用同一引擎预览。
- training任务 research/risk_budget/{common,data,train,pipeline}.py + tests，实际40单元训练/预测/冻结；root owns research/risk_budget/score.py统计/发布与shadow.py前瞻日志。引擎+scorer数值代码稳定/早期审阅后再真实训练。
- surface任务 backend risk_budget_store/api + frontend RiskBudgetPanel，读实际记录、原/校准策略表、权益/仓位/风险/费用联动、目标风险/成本draft→POST预览、结果与draft区分、拒单/来源/导出；纯参数预览不训练/不存原库，异步归属/窄屏/键盘/减少动态。
- 最后reviewer独立复算，真实browser/测试，报告所有不利结果。

## 训练共享产物

root/protocol.json {config,sources,environment,source_report_id,source_report_sha256,created_at}，source.json原D24 envelope，inputs.json{files:相对root=>sha}含protocol/source/dataset/source-code快照/所有输入文件；root/{symbol}/dataset.json；root/{symbol}/{fold}/{train,early_stopping,calibration,evaluation_features,evaluation_labels}.json（rows元数据含所有entry/exit/decision时间、x60、标签仅y字段；evalfeatures无y）。training.json{models:{key:receipt},bounds,counts,...}；predictions.json{models:{key:{raw:[eval],calibration_raw:[cal],calibrated:[eval],c,raw_c,clipped,calibration_rows}},evaluation_labels_read:false}。completed.json{inputs_sha256:fileSHA,files}，root/frozen.json{created_at,protocol_sha256,inputs_sha256,files}。40单元/7模型key train_mean,ewma,lightgbm,dlinear_seed_17,dlinear_seed_42,dlinear_seed_2025,dlinear。默认对照只使用3模型原校+2基准。

## 发布与API共享契约

GET /api/v1/risk-budget/runs ->[{run_id,created_at,symbol,name,market,rows,artifact_status}]；GET /runs/{id}->{record,record_sha256,artifact_status,missing_artifacts}。
record={schema:'risk-budget-result-v1',run_id:'risk-'+64hex,identity:{protocol_sha256,source_report_sha256,symbol},created_at,symbol,name,market:'ashare'|'crypto',annualization252|365,source_report_id,source_report_sha256,protocol:dict,dataset:plainD24,models:{key:{name,raw:metrics,calibrated:metrics}},folds:[{fold,bounds,counts,training,calibration:{key:{c,raw_c,clipped,calibration_rows}}}],observations:[{signal_session,decision_at,entry_session,entry_at,exit_session,exit_at,fold,realized_variance,raw:{key:positive},calibrated:{key:positive}}],scenarios:{'0':{strategy:account},'1':{strategy:account},'2':{strategy:account}},artifacts:{path:sha},limitations:[str],shadow:{status:'pending',start:'2026-11-06',records:0,...}}。runid=risk-stable_hash(identity)，identity protocol_sha256=stable_hash(rootprotocol)。record_sha/envelope{record,sha256}发布backend/data/risk-budget-runs/{id}.json；artifacts仅research/artifacts/risk-budget；source原资格归档get(id)，缺源继承missing，SHA变更409。API训练依赖禁止。
POST /runs/{id}/preview body{target_volatility:'0.10',cost_multiplier:0|1|2}调用领域engine按全部8策略确定性重放，返回{source_run_id,source_record_sha256,config:{target_volatility,cost_multiplier},engine_sha256,strategies:{key:account}}，只在当前引擎SHA匹配原protocol.sources中路径时允许，不改旧结果；source缺失/损坏拒绝计算。目标5%–30%，金额/费用最终由后端Decimal，前端仅绘图。默认情景GET可直接展示，调整参数需显式应用，不假装已重算。

前瞻日志本轮只建立不可变注册与append验证：固定start2026-11-06、真实created_at、源/模型/预测SHA、decision与未来entry、可用输入时间及新鲜度校验；旧数据拒绝作为新预测，当前records0/pending。没有实时数据适配前不产生真实前瞻成绩、不创建自动任务。
