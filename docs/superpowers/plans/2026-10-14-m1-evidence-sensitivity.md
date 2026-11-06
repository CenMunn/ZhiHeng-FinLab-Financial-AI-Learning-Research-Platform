# M1 Evidence and Receivables Sensitivity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. 本计划只覆盖 M1；M2 数据先导是独立研究工作，不将其成绩作为 M1 完成条件。

**Goal:** 用户能查看惠天 2025 年报依据，输入回款延迟假设，计算、比较、保存和重开稳态应收占款情景。

**Architecture:** 一个 React 前端和模块化 Python API；领域计算不依赖 HTTP 或数据库。来源通过白名单适配为不可变快照；SQLite 同事务保存输入、结果、来源与幂等记录。单机单使用者，服务绑定 127.0.0.1。

**Tech Stack:** React + TypeScript + Vite；Python >=3.12、FastAPI/Pydantic、SQLite、Decimal；Python unittest 与 HTTP 契约测试；前端 Vitest 和浏览器操作验证。实际依赖版本在实现任务中核对环境、安装并锁定，不使用未核查的“最新版”编号。

**Spec:** [平台架构 1.1](../specs/2026-10-14-platform-foundation-design.md)。

## Global Constraints

- 金额与参数以普通十进制字符串传输；拒绝数值 JSON、NaN/Infinity、科学计数法、超长/超精度值。
- R 非负、最多 18 位有效数字/6 位小数；q∈[0,1]、最多6位小数；Δd∈[0,90]、最多2位小数；字符串最长32字符。
- Decimal 精度34，先乘 R×q×Δd 再除 D，最终 ROUND_HALF_UP 到0.01；R/D 来自服务端案例，客户端不能替换。
- 来源性质、假设、公式计算与质量维度分开；惠天供暖季节性在结果旁常显。首版仅完整年度报告。
- 主输出为稳态应收占款变化；未获得基准账期不开放提前回款，未设置 q 不给真实企业默认值。
- 必须使用 Interactive-front-end；悬停凸起、按压、键盘、触屏和减少动态效果按该技能实施。
- 不改旧项目源码或复核资格，不访问保留集，不安装模型或发起训练。
- 当前新目录还不是 Git 仓库。实际实施前在本目录建立独立版本管理并提交文档基线；不在其他项目执行 Git 操作，不自动 push。

## Review Focus

1. 单位重复换算或客户端伪造 R：适配测试与严格请求结构保证只用可信规范值。
2. 源文件变化/丢失：保存旧快照仍可读；证据状态变化不改写旧结果。
3. 慢计算或保存返回时草稿已修改：迟到响应不得更新当前参数的状态。
4. 同键异参/保存中断：冲突与事务验证，不留下半条记录或重复情景。
5. q 的百分比输入、空白暂态和窄屏操作：只转换一次，缺值不填零，鼠标/键盘均可完成。

## 共享接口：在 Task 1 定义，之后统一消费

`contracts/models.py` 使用冻结的 Pydantic 模型，外部请求 `extra='forbid'`，十进制字段先验证原始输入是字符串再解析；不依赖 Pydantic 的自动类型转换替代语法检查。

| 类型 | 字段与语义 |
|---|---|
| EvidenceLocator | source_id、source_url、source_sha256、value_page、header_pages、printed_page、excerpt、review_status、availability_status、version_status |
| CaseSnapshot | snapshot_id、snapshot_sha256、company_id/name、report_id、period_start/end、currency='CNY'、scope='consolidated'、revenue、days、evidence、limitations |
| DelayAssumptions | credit_share、delay_days；均为规范化十进制字符串 |
| CalculationRequest | snapshot_id、expected_snapshot_sha256、assumptions；不接受收入、天数、结果或用户自报成功状态 |
| CalculationResult | schema_version、formula_version、engine_version、input_hash、snapshot、assumptions、occupancy_change、cash_equivalent_change、unrounded_occupancy_change、formula、limitations |
| SaveScenarioRequest | CalculationRequest 的字段加 title（1—80字符）；幂等键由 HTTP 头传入 |
| SavedScenario | scenario_id、project_id、title、created_at、result；保存后的计算内容不可变 |

版本初值：schema_version=`1`，formula_version=`receivables-delay-v1`，engine_version=`decimal34-halfup-v1`。输入 hash 包含上述版本与规范化快照/参数；不包含 title、时间或请求键。幂等请求另保存 payload_fingerprint（包含 title），避免标题变更被误当同一请求重试。日期使用 ISO YYYY-MM-DD，created_at 使用带时区的 UTC ISO 字符串；界面按用户当地时间展示。

## Task 1：金融输入契约与纯计算

**Files:** Create `backend/pyproject.toml`、`backend/src/platform_app/contracts/models.py`、`backend/src/platform_app/risk/receivables.py`、包入口；Test `backend/tests/test_receivables.py`。

**Interfaces:** `calculate_delay(snapshot: CaseSnapshot, assumptions: DelayAssumptions) -> CalculationResult`；`canonical_input(snapshot, assumptions) -> dict`。计算函数不读取文件/数据库，不启动网络。

- [x] Step 1 写夹具与边界测试：R=3650000、q=.8、D=365、Δd=15 得120000.00；R=100、q=1、D=365、Δd=90 得24.66；零q/零延迟为0；闰年366天；延迟增加占款非减。
- [x] Step 2 写输入测试：拒绝负延迟、91天、q>1、数值JSON、指数、非有限、超精度和超长值；0.80与0.8产生相同输入身份，-0规范化为0。
- [x] Step 3 运行 `python -m unittest discover -s backend/tests -p test_receivables.py -v`，确认新增行为尚不存在而失败，保存首次输出摘要。
- [x] Step 4 固定并锁定兼容环境依赖，按共享类型实现领域计算。只最终量化到分；规范化 JSON 用 sort_keys、紧凑分隔符和 UTF-8。
- [x] Step 5 重跑对应测试，确认金额、语义、hash规则通过；提交该任务相关文件。

## Task 2：惠天只读适配与不可变案例快照

**Files:** Create `backend/src/platform_app/adapters/corporate_risk.py`、`backend/src/platform_app/evidence/service.py`；Test `backend/tests/test_case_adapter.py`。

**Interfaces:** `load_huitian_2025(source_json: Path, corporate_root: Path) -> CaseSnapshot`；`CaseService.get(snapshot_id: str) -> CaseSnapshot`。适配器是唯一可知道旧项目路径和 query 名称的模块。

已核查入口为 `D:/留学准备/corporate-risk/reports/pilot-report-app-v4/src/data.json`，仅白名单 `workspace_cases / workspace_metrics / workspace_evidence`。

选择条件：stock_code=`000692`、report_id=`1225240687`、period_kind=`annual`、scope=`consolidated`；metric=`revenue`、period_role=`current`；期间2025-01-01至2025-12-31，规范收入2103585508.31 CNY。该金额是已有助理核对的来源观测，尚无独立人工验收，不升级质量状态。

关联 metrics.current_evidence_id 到 evidence.evidence_id；保留金额页69、unit_evidence_page及page_contexts定位。从 evidence 原值/倍率复核规范值与 metrics.current 相同，后续只使用规范值一次。案例本身的 PDF hash 与观测来源 hash 必须一致。

- [x] Step 1 为准确选行、重复选择、缺来源、倍率不一致、期间错误、合并/母公司混淆写测试；使用小型复制夹具，不修改旧数据。
- [x] Step 2 跑 `python -m unittest discover -s backend/tests -p test_case_adapter.py -v` 确认失败。
- [x] Step 3 实现适配，拒绝非唯一/不完整匹配；从实际日期派生365天；快照身份覆盖实际使用的观测和来源，不使用展示标题作为业务ID。
- [x] Step 4 在白名单路径内校验 PDF 是否存在/hash是否匹配；不能让客户端传任意文件路径。原文缺失保留引用并标识不可核对；新输入快照不冒称已核对原文件。
- [x] Step 5 重跑测试，并对实际只读数据运行一次适配审计，核查 R、D、币种、口径、页码及原状态保留；提交。

## Task 3：SQLite 原子保存、幂等与版本重开

**Files:** Create `backend/src/platform_app/adapters/scenario_store.py`、`backend/src/platform_app/risk/scenario_service.py`；Test `backend/tests/test_scenario_store.py`。

**Interfaces:** `ScenarioService.save(request: SaveScenarioRequest, idempotency_key: str, project_id='local') -> SavedScenario`；`get(scenario_id: str) -> SavedScenario`；`list(project_id='local') -> list[SavedScenario]`。服务内部消费 CaseService 与 calculate_delay。

SQLite 两张业务表：scenarios（ID、项目、标题、UTC时间、快照/输入/结果JSON），idempotency（project_id、operation、request_key、payload_fingerprint、scenario_id；前三项唯一）。外键启用，事务提交前不得发成功响应。测试用临时数据库，不写入已有项目。

- [x] Step 1 写保存/重开结果一致、同键同payload返回同ID、同键异payload冲突、不同项目作用域测试。
- [x] Step 2 写客户端伪造结果/快照hash被拒、写入第二表前故障回滚、外部来源变化后仍可重开旧结果测试。
- [x] Step 3 跑 `python -m unittest discover -s backend/tests -p test_scenario_store.py -v` 确认失败。
- [x] Step 4 服务读取可信快照并重算，以一个事务写入全部内容；同键异参或改标题返回冲突，用户编辑应使用新请求键。存量情景按原版本读取，不自动用当前公式重算。
- [x] Step 5 重跑测试并提交。只存相对来源引用和定位信息，API不暴露任意系统文件读取能力。

## Task 4：HTTP 契约与本机启动

**Files:** Create `backend/src/platform_app/api/app.py`、`backend/tests/test_api.py`、`scripts/start_backend.ps1`、`scripts/start_frontend.ps1`；Modify backend依赖锁文件。

**Interfaces:**

| 方法/路径 | 输入/输出 |
|---|---|
| GET /api/v1/health | 当前服务状态及契约版本；不声明模型就绪 |
| GET /api/v1/cases | 可用案例ID、快照hash及摘要 |
| GET /api/v1/cases/{snapshot_id} | CaseSnapshot |
| POST /api/v1/risk/receivables-delay | CalculationRequest → CalculationResult |
| POST /api/v1/scenarios | SaveScenarioRequest（含 expected_input_hash）+ Idempotency-Key → SavedScenario |
| GET /api/v1/scenarios | 已保存情景摘要 |
| GET /api/v1/scenarios/{scenario_id} | 原版本 SavedScenario |
| POST /api/v1/risk/receivables-compare | 当前参数及可选已存参照 → 同基础差额 |
| GET /api/v1/sources/{source_id}/status?expected_sha256=… | 当前文件相对于该情景来源版本的状态 |
| GET /api/v1/sources/{source_id}?expected_sha256=… | 仅返回匹配指定指纹的注册原文 |

状态：非法字段/参数422；不存在404；版本或幂等冲突409；成功计算200；首次保存201、幂等重试200；存储故障500且无成功文案。错误体含稳定 code 和用户可读 message，不回传堆栈/本机敏感路径。

- [x] Step 1 写TestClient契约测试覆盖以上状态与多余字段，含服务端拒绝篡改收入字段。
- [x] Step 2 运行API测试确认失败，随后接入领域服务；仅绑定127.0.0.1，前端开发使用Vite代理，无需开放任意来源CORS。
- [x] Step 3 启动脚本默认API8010、前端5174；端口占用报明确错误，不杀其他进程。实际端口如调整须同步启动说明。
- [x] Step 4 跑后端测试集，实际请求健康/案例/计算/保存/重开；核查第二次请求返回相同ID；提交。

## Task 5：交互页面与端到端验收

**Files:** Create `apps/web/package.json`、锁文件、Vite/TS配置；`src/app/App.tsx`；`features/risk/RiskWorkspace.tsx`、`risk-state.ts`、`api.ts`；`shared/ui/TactileButton.tsx`、`EvidenceDrawer.tsx`；`styles/tokens.css`、`workspace.css`；Test `features/risk/risk-state.test.ts`。

**Interfaces:** web api.ts 只消费Task4结构，计算返回带请求版本归属；`risk-state.ts` 管理 incomplete/dirty/calculating/calculated-unsaved/saving/saved/error 和比较锚点，不实现金融公式。

- [x] Step 1 读 Interactive-front-end 与 frontend-design，制作实际业务内容的页面方向草图。先向用户展示具体视觉方案以收集偏好；计算与数据任务可继续，不依赖此反馈。
- [x] Step 2 写状态测试：15天请求未返回时改20天，旧成功/错误不改变当前草稿；旧保存响应不清掉新草稿；保存失败可重试原请求键。
- [x] Step 3 运行 `pnpm --dir apps/web test --run` 确认状态行为尚未实现；实现API状态与页面。q默认空，界面百分比转API比例一次；无来源参数不冒称企业实际值。
- [x] Step 4 主要计算/保存按钮悬停抬升与缩放、按压回落；密集按钮降低幅度。提供数字框、键盘、触屏和减少动态效果。证据抽屉焦点进入/Esc/恢复正确。
- [x] Step 5 对比固定同快照、q及Δd=0参照；展示参数差异和“为什么变了”。不同数据基础禁止直接差值，联合参数变化不伪造单因素贡献。
- [x] Step 6 构建并在浏览器走通选择、证据、计算、比较、保存、重开；验证错误重试、缺q、原文失效、窄屏与减少动效。图表关键数值有表格等价入口。
- [x] Step 7 保存必要的截图与检查结果，更新README/status并提交；明确已验证与未验证项。开发调试可迭代，不额外扩展M2/M3。

## 实施顺序与完成条件

Task1→2→3→4→5按依赖推进；M2 数据先导可独立推进。M1完成以真实案例的可操作链路及对应测试/浏览器验收为准，不能以本计划、构建通过或数学夹具复算替代。

2026-10-14：以上M1实现任务已完成，实际验收与偏差见 docs/implementation-log.md 和 docs/verification/2026-10-14-m1-browser-qa.md。用户授权开发者先决定视觉方案。保存请求新增 expected_input_hash；原文请求绑定 expected_sha256，并增加当前可用性查询。保存失败同键重试由真实浏览器断网请求验证。
