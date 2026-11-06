# D23 校准、失败窗口和样本覆盖

用户授权推进，沿用已确认路线，自主决定常规实现。使用writing-plans、Statistical Analysis、Interactive-front-end与subagent-driven-development；不改旧训练/预测/成绩，不读取保留集/密钥/原账号库。

## 冻结协议

独立research/volatility_diagnostics包，只消费已校验D22原始发布记录及其被冻结的每折validation标签/预测/preparation。验证段同时用于原模型早停，因此不是独立校准集。每折每模型正比例校准c=mean(validation_y/max(validation_pred,1e-10))，clip[.25,4]，只对后续该折evaluation乘c。报告raw_c、c、是否截断、验证样本和前后QLIKE/方差RMSE/均值比；保留全部模型/全部折，不按评估筛选。此比例是在正比例族最小化验证QLIKE的解析解，不重新训练网络。

可靠性分箱：每折原始验证预测的五分位边界，去重边界，评估用相同边界并保留空箱；分箱记录count/预测均值/实际均方均值/均值比，未知为null。不是概率校准或覆盖率承诺。

失败窗口：每折按原评估顺序连续20条非重叠窗口，最后不足20条保留，窗口不跨季度。记录原始/校准/同窗口EWMA QLIKE和差值、最大实际方差、y>4pred次数。完整所有窗口与按原始差值降序的worst3，明确事后描述，不作为可事前识别区间。h5重叠依赖明确。

样本覆盖：按原折train阈值，训练/验证/评估各6市况数；每季度评估各组同时报告标签不重叠窗口数（贪心选择后续label_start>上一个label_end，不能称统计独立）、30条展示门槛缺口和训练/评估份额差。单股/单币、未扩新数据；不能把30条当统计功效充分或补合成数据冒充覆盖。总体各组nonoverlap_count为季度内计数之和。

## 共享结果契约

GET /api/v1/volatility/runs/{run_id}/diagnostics -> {record,record_sha256,artifact_status:'verified'|'missing',missing_artifacts:[]}。
record={schema:'volatility-diagnostics-v1',diagnostic_id:'vdiag-'+64hex,source_run_id,source_record_sha256,created_at,market,horizon,protocol:dict,sources:dict[path,sha],artifacts:dict[path,sha],models:dict[key,{name,raw:metrics,calibrated:metrics,comparison:dict,folds:[{fold,raw_c,c,clipped,validation_rows,raw:metrics,calibrated:metrics,bins:[{lower:number|null,upper:number|null,rows,prediction_mean:number|null,realized_mean:number|null,ratio:number|null}]}],windows:[{fold,start,end,rows,raw_qlike,calibrated_qlike,ewma_qlike,raw_delta,calibrated_delta,underforecast_count,max_realized_variance}],worst_windows:[same]}],coverage:[{regime,name,train_rows,validation_rows,evaluation_rows,nonoverlap_count,missing_to_30,train_share,evaluation_share,share_change}],coverage_folds:[{fold,regimes:[samecoverage]}],limitations:[str]}。metrics复用D22字段；comparison复用paired_comparison(current y,calibrated,raw,folds)，以负值表示改进。

离线输出backend/data/volatility-diagnostics/{source_run_id}.json envelope{record,sha256}，大中间输入/运行身份在ignored research/artifacts/volatility-diagnostics；只读API不得导入研究numpy/torch。source_record_sha256绑定原记录，store调用原VolatilityStore.get验证源和来源文件，不接受任意URL/路径；无结果404诚实提示，变更409，缺源产物继承missing。

## 任务与验收

- Root：分析纯函数与来源绑定离线runner、真实四组诊断与报告。RED→GREEN覆盖验证-only拟合、零truth/重复bins/空箱/固定窗口季度边界/非重叠计数。
- Backend/UI任务：独立store/API及前端追加VolatilityDiagnostics组件，跟随父record/model，三个native按钮视图“校准分析/失败区间/样本覆盖”，可选季度/窗口联动、原始与校准并列、导出JSON/MD、空/错误/重试/晚到响应/窄屏键盘。维持绿金主题与原页面功能。
- 独立审阅后修复，实际运行全套必要测试/构建和新旧波动浏览器；记录所有真实不利结果和未实现内容。

## 执行收据

全部三项完成。四组真实诊断已发布，最终小收据2026-11-05-diagnostics-0c2ade6116b1.json；新旧版本按身份归档。103后端/75研究/43前端与构建、13新增+17原波动浏览器通过。独立审阅无Critical/Important，已修正分箱区间文案，无数值改动；逐折全部模型系数/评分独立复算一致。覆盖只完成审计，新增标的/时期需下一阶段数据协议，未宣称已扩样。[报告](../../research/2026-11-05-volatility-diagnostics.md)。
