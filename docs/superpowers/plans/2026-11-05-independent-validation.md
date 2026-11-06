# D24 多标的数据资格与独立校准协议

用户已批准按专家建议推进，先交付本切片；采用writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end。沿用当前featurecheckout，保留所有旧数据/未提交改动。无付费API/交易/旧账号库操作。

## 冻结范围

教学候选组（人工选择的当前存续标的，明确幸存/选择偏差，不称历史全市场抽样）：A股600519消费、600036银行、600900公用事业、600585周期、600276医药；crypto BTCUSDT原锚、ETHUSDT迁移。2018-01-01至2025-12-31，先登记名单再取数据，无按成绩换标的。BTC/茅台复用原已校验公开快照，其余获取原价OHLC、分红/拆股事件与日历；Binance月档+CHECKSUM。ETH不能标成BTC，采用本切片独立market=ashare/crypto契约，不改旧Literal。

数据合格只表示在公开历史重建假设下可准备研究数据，非PIT审计通过。腾讯原价OHLC+Yahoo事件，不能证明公司行为完整；停牌/缺交易日/拆股事件处理不了则拒绝并列出原因，禁止前填。缺日对比固定XSHG社区日历。Binance连续UTC日线、单位变更、发布者哈希。资格报告需所有7候选（失败也保留）、各来源哈希/时间、行数/缺失/异常/事件/许可限制。不按未来模型成绩筛选或无声剔除。

8季度2024Q1–2025Q4；每折train从2018开始，early_stopping为评估前第12至第7个月，calibration为前6个月，evaluation为下一季度，各段互斥且标签成熟/未来1或5日完整在本段，lookback60只用已知输入；标准化train-only、早停仅early_stopping、比例校准仅calibration、评分独立进程才读evaluation_labels。预备阶段不训练/读取评估标签作选择。

本轮优先完成资格与四段样本准备/标签隔离，不强行在尚不合格数据上模型训练。历史2024/25不是未知盲测；前瞻信号起点固定2026-11-06，协议冻结SHA与UTC时间先落盘，未来等待真实观测，当前不能展示前瞻成绩。该时间不自动触发采集/交易，也无定时任务。

## 文件与分工

- acquisition任务：research/validation_foundation/acquire.py，固定候选来源，独立ignored research/artifacts/validation-data/v1/，产出datasets/{symbol}.json、acquisition.json，失败也登记。不得改旧fetch/公开快照，网络有界缓存SHA、每资产失败隔离。
- Root：research/validation_foundation/protocol.py/qualify.py/prepare.py，TDD纯函数质量/四段清除、原始和发布输入指纹；真实运行7候选、发布独立准备摘要（不装成训练成绩）。
- surface任务：只读GET /api/v1/validation-foundation/report，backend/data/validation-foundation/latest.json envelope{record,sha256}，record={schema:'validation-foundation-v1',report_id:'validation-'+64hex,created_at,protocol:dict,protocol_sha256,assets:[{symbol,name,market,role,status:'qualified'|'rejected',rows,issues:[str],warnings:[str],coverage:{expected,missing,extra},events:{dividends,splits},folds:[{fold,bounds:{train:[start,end],early_stopping:[...],calibration:[...],evaluation:[...]},horizons:[{horizon:1|5,counts:{train,early_stopping,calibration,evaluation},purged:{same}}]}],source_receipts:[dict]}],artifacts:{path:sha},limitations:[str]}。report_id=validation-stable_hash({protocol_sha256,assets,artifacts})。接口验证SHA/身份/路径/缺产物，网页只读不获取行情/训练。
- UI Training页面独立小面板ValidationFoundationPanel：7候选资格、失败原因、四段时间轴/期限/季度、来源、前瞻未开始/无成绩、JSON/MD导出；遵循现有绿金/原交互、异步归属/空错重试/窄屏。
- 最后独立审阅、实际数据/测试/构建/浏览器，更新报告与下一阶段训练协议。

## acquisition共享输入

dataset JSON={symbol,name,market:'ashare'|'crypto',role,bars:[{session,open,high,low,close,volume,close_at,available_at}],expected_sessions:[date],dividends:[{session,amount}],splits:[{session,ratio}],receipts:[{file(relative to DATA root),url,sha256,retrieved_at,publisher_checksum?:sha}],warnings:[str]}。原600519/BTC可从原PublicDataset.model_dump转换，receipt file不能跨目录；推荐复制/引用原快照并核验source_sha256，简化receipts仅一份已校验源snapshot，本切片不得移动旧文件。全部新raw在DATA root。acquisition.json={assets:[{symbol,status:'acquired'|'failed',dataset_file?:str,error?:str}],...}；失败不写伪造dataset。

## 执行完成

7候选实际采集，5资格通过、600900缺11日/6002764拆股拒绝；80准备单元/320角色分区完成。876摘要/5规范化源码/四段边界独立复审通过，无Critical/Important；111后端/86研究/47前端/构建与9实际浏览器通过。修复可变采集清单、空来源证明、预检晚于落盘和规范化版本记录，保留旧审阅版本，以validation-4772133…bf5405c为最终报告。本轮范围止于资格和准备，不称完成新模型训练。[结果与复现](../../research/2026-11-05-independent-validation.md)。
