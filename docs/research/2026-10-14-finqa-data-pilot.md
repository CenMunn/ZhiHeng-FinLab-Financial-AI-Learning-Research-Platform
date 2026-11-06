# FinQA 数据先导与词法诊断

日期：2026-10-14。用途：决定首个金融证据排序任务的数据与划分路线。结构检查覆盖全部 train/dev；词法先导固定60题；未训练模型，未获取/读取测试集内容。

## 来源与复现

官方仓库 [FinQA](https://github.com/czyssrs/FinQA/tree/0f16e2867befa6840783e58be38c9efb9229d742)，固定 commit `0f16e2867befa6840783e58be38c9efb9229d742`。已获取 train.json、dev.json、README、LICENSE、用于静态核对的两个utils文件；没有执行上游代码。仓库根 LICENSE 为MIT，已保留原文；本轮不进行数据再分发或公开发布。

- [下载脚本](../../research/ingest/fetch_finqa.py)：显式白名单、固定版本、文件哈希及缓存校验。
- [审计脚本](../../research/evaluation/audit_finqa.py)：仅从原文字段构建候选，标签另用于诊断。
- [验证用例](../../research/tests/test_finqa_audit.py)：已运行5项通过；写实现前先观察对应失败。
- [机器可读结果](finqa-audit-summary.json)：保留来源URL/hash、字段计数、分组与诊断定义。
- [学习与复现 notebook](../../research/notebooks/01_finqa_data_audit.ipynb)：提供分步复现；本机无Jupyter依赖，未运行Jupyter内核。底层脚本已实际执行。

复现命令（项目根目录）：

```powershell
python -X utf8 research/ingest/fetch_finqa.py
python -X utf8 -m unittest discover -s research/tests -v
python -X utf8 research/evaluation/audit_finqa.py
```

原数据约89MB，下载后保存在被Git排除的 research/data。完整抽样片段/标签在 research/artifacts 中保留用于研究，不进入应用检索库。Notebook如需实际内核执行，在具备 nbformat/nbclient/ipykernel/Jupyter 的研究环境中运行 `python -m jupyter nbconvert --execute --to notebook --inplace research/notebooks/01_finqa_data_audit.ipynb`。

## 结构与分组

| 检查 | Train | Dev |
|---|---:|---:|
| 问题数 | 6251 | 883 |
| 不同公司ID | 135 | 97 |
| 不同公司—年度组 | 741 | 224 |
| 不同页面ID | 2110 | 299 |
| 重复问题ID额外行 | 0 | 0 |
| 源候选构造失败 | 0 | 0 |
| gold为空/缺问题文本 | 0 | 0 |
| gold包含不存在的候选ID | 1 | 0 |
| gold与重建源文本字面不同的问题 | 157 | 30 |
| gold超过5条的问题 | 34 | 7 |

公司—年度组是从 company/year/page_N.pdf-example 解析出的代理分组，没有据此认证具体报表版本。不能把页面ID等同于完整年度报告ID。

Train/Dev交集：公司ID96个、公司—年度组197个、页面ID0个、问题ID0个、候选上下文hash0个、规范化问题文本16个。相同问题文本可能只是不同公司的通用提问，本轮不把它直接判为泄漏。

**结论：** 官方页内任务可继续开发；官方Train/Dev并不构成未见公司或未见公司—年度组验证。原论文的“input reports不重叠”应与其输入页面粒度区分，不用本结果指控官方协议错误。后续要回答未见报告/公司的泛化问题，另建分组协议并保留官方协议结果。

## 标签与序列化

1. 训练题 `RE/2010/page_120.pdf-2` 包含 `text_-1`，显式候选集合中没有这个ID。训练前单列隔离/复核，不能用Python负索引把它悄悄映射到末尾句子，也不能把gold文本补进候选来掩盖问题。原数据保持不改。
2. 157+30道问题的字面差异在保留标点token的比较下全部具有相同token序列；抽查一例为 `december 31,` 与 `december 31 ,`。这支持格式差异解释，不能据此声称金融内容错误，也不能把token相同当作专业复核。
3. 为避免正负例格式成为标签捷径，正式训练的正例和负例都从源字段按相同规则构造，再按gold ID关联标签；不采用gold_inds的文本作为正例专用输入。
4. 数据包含 answer、steps、program、model_input 和官方retrieved字段。候选构造函数不读取这些字段，仅使用 pre_text、post_text、table。已用污染字段夹具验证隔离。
5. 超过5条标注证据的41题在Coverage@5中天然不能完整覆盖；保持分母、单列上限与题数，不能为了好成绩删题。该指标是完整标注集覆盖，不等于答案正确率或全部真实充分依据覆盖。

## 固定60题词法先导

每个split按 SHA256(commit,split,question_id) 升序取30题。BM25采用页内IDF、k1=1.2、b=.75、英文小写词与数字分词；保留表头并按统一模板文本化表格，包含上游推理候选中的表头行。不做词干化/停用词过滤，不使用gold构建候选，分数相同时按源顺序打破平局。

| 抽样部分 | 完整标注证据Coverage@5 | 候选完整Coverage@20 | 构造/评分错误 |
|---|---:|---:|---:|
| Train先导 | 18/30 | 29/30 | 0 |
| Dev先导 | 26/30 | 29/30 | 0 |

这是自主实现的词法开发诊断，未复现官方模型、不比较论文榜单、没有神经网络训练或最终测试。样本小，Train与Dev难度可能不同，不根据26/30推断泛化性能。top20仍有遗漏，后续重排序需要分别报告候选上限和端到端结果，不向候选注入gold。

## 金融混淆负例可行性

在固定样例中读到的候选线索：

- `UNP/2011/page_41.pdf-1`：查询应收证券化融资额度，候选中同时有另一信贷额度的使用信息。工具/额度指代需要区分。
- `ETR/2017/page_441.pdf-4`：查询特定核燃料实体的credit facility利用率，候选含money pool应收等相似实体的其他财务概念。
- `RSG/2015/page_126.pdf-1`：查询未确认税收利益余额下降，靠前候选包含影响税率的相关税收金额及利息；词面相关不保证支持同一计算。
- `DRE/2002/page_40.pdf-1`：表格同行包含多个列组及随后日期的分红文本，不能以“出现另一年份”自动标负。

这些只是助理查看到的候选类型，**尚未完成可信负例标注与独立复核**。原gold之外的片段仍是未标注，不是确认负例。先导表 `negative_label_review_status` 全部保持unreviewed。

路线决定：B0—B2基础任务可继续；B3金融混淆增强为条件性试验。先固定标签规范，对自然候选做正例/负例/不确定三分复核，统计各类型、独立页面/公司—年度组及可用数量；不确定项不强制标负。若标签不足，保留普通困难负例路线和错误分析，不强造年份/口径错误。

## 下一步关卡

- 隔离1条不合法gold引用，保留原数据及理由；训练资格清单与官方评测分母分开，不无声删题。
- 固定正负例同源序列化，明确company/year代理与页面ID；根据研究问题设计独立公司/年度分组验证。
- 把金融混淆类型标注规范和少量已复核例子写清，再确定B3规模与训练配置。
- 检查本地训练硬件和兼容模型，中文迁移诊断另做；本轮没有确认模型版本或资源预算。
