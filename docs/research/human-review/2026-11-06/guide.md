# 原六报告三字段：独立人工复核填写指南

此包共 6 份原报告、18 项。所有人工答案为空，状态 unreviewed，已完成数为 0。
助手旧参考仍是待人工审核的视觉参考，本包未附参考值，也不读取或覆盖它。
本包仅覆盖原公司 600519/600036/600585 的 2024Q1 与 2025Q1；不含新封存公司。

先另存 checklist.csv 为自己的审核文件，再独立阅读 source_url 或 local_pdf 指向的完整原始 PDF。
不要先看助手参考或模型输出。source_url 是原始链接，local_pdf 是相对项目根目录的原 PDF 路径。
保留 case_id、doc_id、company、metric、source_url、local_pdf 六列身份信息，不能增删或复制行。
PDF 全文可能超过模型输入的前六页；人工应阅读足以确认金额和口径的所有页面。

## 核对口径

1. revenue：营业收入；net_profit_parent：归属于母公司/上市公司股东的净利润；
   operating_cashflow：经营活动产生的现金流量净额。先核对行名，不把相近指标当成目标。
2. 核对目标季度累计流量及“本报告期/当期”列，不抄“上年同期/上期”或增减百分比。
   manual_period 必须独立确认后填写 2024Q1 或 2025Q1；它不得从其他行自动填入。
3. 先区分合并/集团与母公司单体报表。目标为合并集团口径，manual_scope 写 consolidated。
   只找到母公司时可记 parent，但状态必须 uncertain 或 disputed，并在 notes 保留原因。
   不能只凭前页摘要推断合并范围；表头或后续报表页的范围证据也要核对并记页。
4. 归母净利润不得混用“扣除非经常性损益后的归母净利润”、总净利润、少数股东损益或同比比率。
5. 读取金额所在表的币种和单位，不让每股收益的“元/股”覆盖财务表头的“百万元”等单位。
   manual_unit 逐项填写 元/千元/万元/百万元/亿元 之一；manual_currency 在原文确认人民币后填写 CNY。
   manual_value 保留原表单位下的十进制数，不自动乘单位、不带千分位逗号/货币符号/百分号/科学计数法。
   括号负数转换为负号（如 -12.50），要区分脚注括号与负值括号；未知或无法确认不能填 0。
6. value_page 写金额所在 PDF 物理页码，从文件第一页数作 1，不用印刷页码或阅读器偏移页码。
   header_pages 记单位、期间、范围的证据物理页，可在金额页之后；多页用英文逗号分隔，如 2,8,9。
   quote 独立抄录足以定位金额/当期列及口径的简短原文；引用来自后页时在 notes 说明各页作用。

## 状态与交付

- unreviewed：未开始，所有人工列保持空白。
- in_progress：已开始，可暂留空项；有值的列仍须符合格式。
- completed：金额、单位、币种、期间、合并范围、金额页、表头页、引用、reviewer、reviewed_at 均已填写并核对。
- uncertain：证据不足，未知项留空；必须填写 reviewer、reviewed_at、notes，不能算完成。
- disputed：口径或答案有异议，保留双方原记录和说明；必须填写 reviewer、reviewed_at、notes，不能算完成。

reviewed_at 用带时区的 ISO 时间，例如 2026-11-06T15:00:00+08:00；reviewer 写实际审核人。
有分歧时分别另存带审核人/版本的文件，不删除不同意见，不覆盖助手旧参考。后续合议也需新增记录。
用 `research/.venv/Scripts/python.exe -X utf8 -m research.filing_development.preparation validate-review 审核文件.csv`
进行只读格式校验。校验只确认身份、完整性与格式，不证明财务答案或引用正确，也不写回旧参考。
未全部完成的文件始终是 pending_human_review，不能称已审核金标；本轮工程研发不等待人工填写。
