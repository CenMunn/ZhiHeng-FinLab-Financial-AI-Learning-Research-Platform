# 波动预测与市况稳定性 Implementation Plan

用户授权自主规划并执行至北京时间2026-11-04 15:20。采用writing-plans、subagent-driven-development、Statistical Analysis、Interactive-front-end；复用当前feature分支，保留全部既有未提交成果，不另迁移工作区。

## 冻结设计（D22）

面向初学者，先回答未来波动幅度能否比简单规则预测得更好，以及效果是否依赖市况。现有公开日线只支持波动代理，使用分红调整的对数收盘收益r，标签y=mean(r[t+1:t+h+1]^2)，h=1/5个市场日；估计零均值下二阶矩，不称高频实现方差或可交易收益。未来标签成熟时间取窗口内最大available_at。输入60期已知r，使用8季度扩展训练/前12月验证/下一季评估，跨段未来标签清除。沿用两份公开快照，无新付费源。

基线：train均方、最近20期均方、EWMA lambda0.94；GARCH(1,1)零均值正态QMLE、HAR式多尺度非负线性回归（1/5/22期收益平方均值，不称原版高频HAR-RV）；LightGBM与正值输出DLinear三种子作为AI对照。所有学习参数仅train，早停仅validation；train/validation/evaluation_features及evaluation_labels分文件，先冻结模型和预测再独立评分。原D20/D21源码及产物不改。

主指标QLIKE=log(hat_y)+y/hat_y（省去仅依赖真实值的项，允许y=0），同时报告variance RMSE/MAE、年化波动幅度RMSE、平均预测/实现比和相对EWMA损失差；正预测floor1e-10，记录触底数，不能剔除极端日。A股年化252，BTC365，h5目标是日均方，不额外除以5。QLIKE绝对值可负且不同标的不直接排名。

市况只由当时已知历史定义：过去20期均方按每折train三分位划分低/中/高波动，过去60期累计对数收益正负划分上涨/下跌，共6组。阈值冻结train，不按未来表现或未来波动分组；小于30条标注样本不足。季度与市况全报告，不挑好看区间。固定20行块/2000次配对bootstrap，按季度内抽块再聚合；保留重叠h5依赖，市况重采样对全时序抽块再过滤，不能将不连续子组压紧当连续日。CI是探索性逐比较区间，不当多重检验确认或独立未来验证。

参考：Corsi2009多时间尺度HAR思想、Patton2011噪声波动代理及QLIKE、arch官方GARCH预测文档、Hansen/Lunde/Nason2011多模型不确定性。固定少量候选、报告所有结果，不在本次历史评估上自动调参。

## 文件/分工与交付协议

- [ ] Root：research/volatility/data.py/common.py/pipeline.py/score.py，隔离准备与冻结评分；因果/跨段清除/版本完整性测试，实际运行全部双市场实验。
- [ ] 模型任务：research/volatility/models.py/metrics.py及research/tests/test_volatility_models.py，数学基线/GARCH/HAR/LGB/DLinear、配对统计；实际小批前后向和拟合验证。
- [ ] 展示任务：backend contracts/adapters/api volatility与对应测试；前端VolatilityPanel/API/types/css与浏览器检查，只读结果，市场/期限/季度/市况/模型联动、导出、来源/诚实错误状态。
- [ ] 独立审阅：检查未来泄漏、代理口径、GARCH状态/多步、CI重叠、模型版本、异步归属与真实实验结果；修复后必要重跑。
- [ ] 后续自主阶段：根据结果检查校准与失败市况，优先可解释、低成本的风险预算教学方案；只在本协议验收后开展，另记身份，不把训练页面的风险幅度解释为涨跌建议。15:10后不启动长任务，15:20前保存结果/状态/下一步。

## 共享结果约定

GET /api/v1/volatility/runs 列表[{run_id,created_at,market,instrument,horizon,rows,artifact_status}]；GET /runs/{id}={record,record_sha256,artifact_status,missing_artifacts}。
record schema=volatility-result-v1, run_id=volatility-64hex, identity={protocol_sha256,dataset_sha256,market,horizon(string)}, created_at, market ashare/btc, instrument, currency, horizon 1/5, annualization252/365, dataset_sha256,dataset(PublicDataset),protocol(dict),folds,overall,regimes,observations,artifacts(relative path=>SHA),limitations,phase_receipts。
overall={model_key:{name,metrics,wins_vs_ewma,folds,comparison}}。metrics={rows,qlike,variance_rmse,variance_mae,volatility_rmse_ann,calibration_ratio,prediction_floor_count}；comparison={delta_qlike,ci_low,ci_high,block,repeats}（delta<0更好）。folds=[{fold,bounds,counts,purged,regime_thresholds,models:{key:{name,metrics,comparison}},training:receipt}]。regimes={regime_key:{name,rows,sufficient,models:{key:{name,metrics,comparison}}}}；observations=[{session,fold,regime,realized_variance,predictions:{key:number},label_end}]。artifacts仅research/artifacts/volatility，缺失提示/变化拒绝；身份及自足dataset/record SHA验证。

## 执行状态

重新授权继续完成后，准备/训练实验、模型、展示、独立审阅四项已完成验收。96后端/69研究/38前端、构建与17实际浏览器检查通过；修复输入/逐折指纹、部分折残留拒绝覆盖与新attempt、递归全前缀as-of。原数据资格及全部标签/总体指标重建一致，保留原实验不重训，独立审阅复核通过。后续风险预算是下一阶段，尚未执行。

模型与展示代码任务已实现；Root准备/32折训练/独立评分及四份实际结果已完成，版本v1-70e32f526464e2e6e31db8de。96个DLinear累计204,157更新。96后端/65研究/38前端及构建通过。真实页面浏览器验收未完成（恢复时8010未运行）；独立审阅和后续风险预算未执行，原任务勾选项中包含这些未完成条件的保留未勾选。实际后台完成15:26:48，比用户15:20界限晚约6分49秒；恢复于23:12后仅验收归档，停止新增研发。[完整报告](../../research/2026-11-04-volatility-stability.md)。
