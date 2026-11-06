# D25 五标的有限波动模型对照

用户明确授权在D24五个合格标的运行有限对照。使用writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、独立审阅。原数据/旧实验/FinQA/账号库不改，不读取密钥。

## 冻结协议

绑定D24最终资格report_id validation-4772133ea7c23f0edd8960f6e70f3e77dca6a01d61ca8e97de20a00a7bf5405c，必须源与876文件SHA一致。仅600519、600036、600585、BTCUSDT、ETHUSDT。每标的8季2024Q1–2025Q4，1/5期，共80单元；四段沿用已冻结train/early_stopping/calibration/evaluation，不重新划分。

模型固定train_mean、hist20、EWMA(.94)、GARCH11零均值正态QMLE、LightGBM Gamma和正值DLinear三种子17/42/2025及均值。数学复用D22模型函数但不改旧文件。树最多200轮/patience20；神经最多30epoch/patience6、batch64/lr.001/weight_decay.001，输入60期收益平方、train-only targetscale；此为有限预算，不声称充分调参或覆盖模型能力。网络实际CUDA前后向与更新/重载检查。所有种子保留，均值固定，不按成绩筛选。

训练只读train，早停只读early_stopping；完成模型选择后推理calibration/evaluation_features（不读评估标签），校准系数c=mean(calibration_y/max(p,1e-10))clip[.25,4]仅由独立calibration段拟合。均值集成先原始种子均值再校准，不以种子评估选优。基线/GARCH也同口径独立校准，全报告raw/calibrated。

先冻结输入、代码/环境、模型/收据/预测、校准系数，再由独立score进程读取evaluation_labels；断点完成清单逐折验证，残留未完成折保留并明确用新--attempt重新开始。来源快照是原D24已核查文件集，代码改变需新身份，不用当前源码重贴旧成绩。

指标复用QLIKE、variance RMSE/MAE、年化幅度RMSE、预测/实际均方比；原始/校准各与同样本原始EWMA比较，并calibrated-vs-raw。季度内20行/2000次配对块bootstrap仅每标的/期限，系数固定，h5重叠明确；跨标的不当独立样本合并做显著性检验。8季度每折/train阈值6市况诊断，空样本为null/不足30提示。逐标的重训是流程稳健性复现，不是模型零样本迁移；旧历史已研究非盲测，前瞻2026-11-06仍pending无成绩。无仓位/收益实盘。

## 结构与分工

research/five_asset/{common,train,pipeline,score}.py 独立ignored research/artifacts/five-asset，与旧训练源码和产物隔离。
- common负责固定配置、版本环境、来源及指纹校验。
- training任务负责准备/实际80单元训练/模型推理/独立校准/完成冻结。score模块Root负责评估发布。
- surface任务负责只读backend/API、frontend FiveAssetPanel、新旧页面边界及真实浏览器；Root独立评分和科学审阅。
- 最后独立review、缺陷回归修复、实际全套必要测试和文档；不能虚构训练通过。

## 共享接口

GET /api/v1/five-asset/runs -> [{run_id,created_at,symbol,name,market,horizon,rows,artifact_status}]。
GET /runs/{run_id} -> {record,record_sha256,artifact_status:'verified'|'missing',missing_artifacts:[]}。
record={schema:'five-asset-result-v1',run_id:'five-'+64hex,identity:{protocol_sha256,source_report_sha256,symbol,horizon:string},created_at,symbol,name,market:'ashare'|'crypto',horizon:1|5,annualization252|365,source_report_id,source_report_sha256,protocol:dict,overall:{key:{name,raw:metrics,calibrated:metrics,raw_vs_ewma:comparison,calibrated_vs_ewma:comparison,calibrated_vs_raw:comparison,wins_raw,wins_calibrated,folds:8}},folds:[{fold,bounds,counts,models:{key:{name,raw:metrics,calibrated:metrics,c,raw_c,clipped,calibration_rows,raw_vs_ewma:comparison,calibrated_vs_ewma:comparison,calibrated_vs_raw:comparison}},training:dict}],regimes:{key:{name,rows,sufficient,models:{key:{name,raw:metrics|null,calibrated:metrics|null,raw_vs_ewma:comparison|null,calibrated_vs_ewma:comparison|null,calibrated_vs_raw:comparison|null}}}},observations:[{session,label_end,fold,regime,realized_variance,raw:{key:number},calibrated:{key:number}}],artifacts:{relativepath:sha},limitations:[str]}。
metrics/compare复用D22形状，可额外rows/seed/method等。runid= 'five-'+stable_hash(identity)。API产物路径只准research/artifacts/five-asset，source通过原ValidationFoundationStore.get验证source_record_sha256，返回其missing状态；记录缺失仍标记，不改旧数据。结果包backend/data/five-asset-runs/{runid}.json envelope{record,sha256}，不会训练。

## 训练产物共享

root/protocol.json {config,sources,environment,source_report_id,source_report_sha256,created_at}；root/source.json 为D24 envelope；root/inputs.json {files:相对root路径=>sha} 冻结全部复制的输入包括dataset及四段文件。root/{symbol}/dataset.json为D24datasets普通JSON（校验来源map SHA）。root/{symbol}/{fold}/h{h}/{train,early_stopping,calibration,evaluation_features,evaluation_labels}.json，格式沿D24。root/{symbol}/{fold}/h{h}/training.json {models:{key:receipt},artifacts:{相对单元路径:sha},bounds,counts,source_inputs_sha256}。
predictions.json {models:{key:{raw:[evaluation values],calibrated:[evaluation values],c,raw_c,clipped,calibration_rows}},calibration_labels_read:true,evaluation_labels_read:false}；completed.json {inputs_sha256,files:相对单元路径=>sha}，包含模型/训练收据/预测；root/frozen.json {created_at,protocol_sha256,inputs_sha256,files:全部期待文件相对root=>sha}。Root scorer按冻结清单验证再读评估标签，用输入x和train拟合阈值划市况。模型key9个：train_mean,hist20,ewma,garch,lightgbm,dlinear_seed_17,dlinear_seed_42,dlinear_seed_2025,dlinear。

## 执行完成

actual-v3根3dabb28…39eeb完成全部80单元/240CUDA种子/169378更新，独立score发布10记录，raw和calibration_raw均冻结，415输入含8源码字节快照，1696最终文件。源资格支持归档get(report_id)，不依赖最新指针。训练前修复输入SHA约定与源码字节归档；页面实测修复重复同上下文等待，列表校验去重仍请求级鲜检。独立1280预测/系数/指标/bootstrap复算一致，无遗留Important/Critical。123后端/96研究/50前端、构建、9新+9原资格浏览器通过。[完整报告](../../research/2026-11-05-five-asset-comparison.md)。
