# Skill 按功能路由

日期：2026-10-14。此文件是项目级使用映射，不重新安装或复制全局 skills。下列技能已在当前技能目录中可用；列入路线不表示已执行该技能的全部流程。

2026-10-30补充：用户指定的6个上游来源已按固定commit安装到本机，保留原许可。来源见 [版本清单](design/2026-10-30-skill-sources.json)。本轮为按功能选择，不把所有技能的模板/依赖接入应用；下一回合技能目录可发现这些本地安装，本轮已直接读取。

| 新增规范来源 | 本项目采用部分 | 调用边界 |
|---|---|---|
| Hallmark | 应用信息层级、token、静态反模板检查 | 与 Interactive-front-end 配合，不能删除业务路径；只执行所需 app 范围 |
| GSAP-Skills：core/react/timeline/performance | 作用域、清理、状态切换、减少动态效果 | 只处理视觉，不运行训练或模拟业务进度；未安装无用的全部插件 |
| Open Design：design-brief | 八维设计约束与可移交设计文档 | 本轮只下载规范文件；不安装整个桌面应用/MCP；项目保留已确定深色视觉 |
| Taste-skill | app screen 数据/排版/静态检查 | 不覆盖真实字段或强迫采用钱包业务布局 |
| Impeccable | Operate 模式和 craft floor | 引擎下载失败，未声称自动 context/audit 执行成功；采用文档规范 |
| UI/UX Pro Max | 触控、焦点、对比度、图表检查 | 两次自动系统检索均不匹配成人金融实验室，不采用营销/儿童皮肤 |

| 工作范围 | 首选 skill | 何时使用 | 不承担什么 |
|---|---|---|---|
| 新模块边界与产品设计 | `superpowers:brainstorming` | 明确需求、职责、方案与可验收切片 | 不替代数据审计或模型实验 |
| 明确架构后的实施任务 | `superpowers:writing-plans` | 将已确认设计拆为具体接口、文件与验证任务 | 不为未确认的新方向编造完整实现 |
| 控件和操作流程 | `interactive-front-end` | 所有本项目的前端交互；局部按钮可只读微交互章节 | 不计算财务值，不决定模型正确性 |
| 新视觉风格 | `frontend-design` | 字体、色彩、层次、密度和布局 | 不覆盖用户对学循交互与微交互的明确要求 |
| React 实现 | `build-web-apps:react-best-practices` | 实际编写 React 时 | 不为了优化而重构无关组件 |
| 页面行为验证 | `build-web-apps:frontend-testing-debugging` | 页面可运行后验证交互及错误恢复 | 不把截图或构建当模型验证 |
| 来源、粒度、缺失与日期 | `data-analytics:analyze-data-quality` | 数据接入、训练资格审查 | 不把清洗通过等同于财务真实性 |
| 实验方法与效应估计 | `statistical-analysis` | 模型对照、不确定性与统计报告 | 不用显著性代替实际收益或泛化 |
| 文献与结论审查 | `scientific-critical-thinking` | 判断论文结论、偏差、泄漏及可迁移性 | 不根据论文摘要声称本项目可复现其成绩 |
| 学习与训练 notebook | `data-analytics:jupyter-notebooks` | 公式、训练与评估需要可重复执行的记录 | 不把临时 notebook 状态作为线上模型 |
| 科研图表 | `scientific-visualization` | 训练曲线、校准图、区间覆盖和论文图 | 不替代应用控件设计 |

## 当前关键技能入口

- [Interactive-front-end](C:/Users/g'g/.codex/skills/interactive-front-end/SKILL.md)
- [微交互规范](C:/Users/g'g/.codex/skills/interactive-front-end/references/microinteractions.md)
- [学循源码参考](C:/Users/g'g/.codex/skills/interactive-front-end/references/source-map.md)
- [Frontend Design](C:/Users/g'g/.codex/skills/frontend-design/SKILL.md)
- [Statistical Analysis](C:/Users/g'g/.codex/skills/statistical-analysis/SKILL.md)
- [Scientific Critical Thinking](C:/Users/g'g/.codex/skills/scientific-critical-thinking/SKILL.md)

其他插件技能以当前会话技能目录定位，避免把缓存版本路径固化为依赖。技能不可用时报告缺项，保留已明确的用户要求与项目规范。

## 模块工作方式

2026-11-07 D31：按 writing-plans/executing-plans/TDD/独立审阅分离布局候选、冻结模型推理与评分；PDF技能实际核对新公司15页，Interactive-front-end/frontend-testing处理来源列/排除/拒答、比率原值、窄屏及导出。dispatching-parallel-agents仅用于互不改同文件的D27复查、结构算法、独立视觉参考与展示；参考不读模型预测。585项完整测试与9组实际Edge通过，模型无额外增益、新公司仅3/9覆盖、人工审计未完成均保留，详见[D31](research/2026-11-07-filing-semantics.md)。

2026-11-06 D30：systematic-debugging定位智投委子服务未运行及候选键序codec偏差；writing-plans/executing-plans固定研发边界；dispatching-parallel-agents只分派互不改同一文件的来源准备与只读展示；TDD固定负数/脚注、单位、错列干扰、JSON/trie和完整性。Interactive-front-end与frontend-testing-debugging处理开发对照、失败口径、人工包下载和真实窄屏；requesting-code-review作独立来源/结果审阅。前缀树是算法组件，金融同学审核与工程并行；不把人工确认升级为开发许可。实际使用与边界见[D30报告](research/2026-11-06-filing-development.md)。

2026-11-06 D29按职责使用 writing-plans / subagent-driven-development / test-driven-development 管理离线抽取与评分边界；scientific-critical-thinking用于样本、参考资格和结论限制；PDF技能用于实际逐页核验；Interactive-front-end用于只读对照、公司/字段联动与导出；verification-before-completion用于真实运行、测试和浏览器验收。模型权重及原始PDF不进入全局skill目录；不为新实验复制通用技能。实际结果见[跨公司字段核验报告](research/2026-11-06-filing-extraction.md)。

先确定本次改动属于哪个模块，再读相应技能和模块输入输出；实施后只跑与改动相关的必要检查。跨模块任务以契约和版本为连接点，不由某一个技能接管全部设计。

设计阶段使用 brainstorming、Interactive-front-end 和科学方法规范；M1计划和实现现已完成。2026-10-30前未安装第三方设计技能；本轮新增范围以上述清单为准。

每个功能切片交付时只追加一行实际使用记录，列明模块、读取的 skill、采用规则、验证证据和未验证项。路由表本身不代表已执行。

| 日期/工作 | 实际应用 | 采用内容 | 验证边界 |
|---|---|---|---|
| 2026-11-06 D28公告与事件 | writing-plans、subagent-driven-development、TDD、Scientific Critical Thinking、PDF、Interactive-front-end、verification-before-completion | 日期资格/原文页视觉核对、固定案例与OLS窗口、派生字段来源重建，深色证据/AR/CAR联动与可读导出 | 534原公告→38目录/24正文，1完整案例、3金额/5物理页核对，169后端/143研究/71前端与构建、9组实际Edge、独立数值复算；模型抽取/私有库导入/精确首次时刻未完成，真机触屏未测 |
| 2026-11-06 D27新行情前向观察 | writing-plans、TDD、Interactive-front-end、独立审阅与完成前核验 | 实际接收/预测/到期时序、冻结模型与原始字节绑定、只追加/幂等，深色五标的状态与导出，用户授权每日两次自动任务 | 5份真实新快照与全历史接续、140冻结历史预测复算、155后端/127研究/63前端与构建、8组实际Edge；真实前向0条，尚未到定时运行和到期评分 |
| 2026-11-05 D26可执行区间风险预算 | writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、requesting-code-review、verification-before-completion | 重训持有目标/四角色隔离，Decimal账户与独立复算，原始/校准/固定仓位对照，显式参数预览、异步归属、键盘/减少动态/导出 | 实际120CUDA网络70,663更新、120账户、148后端/107研究/57前端与构建、10组实际Edge；前瞻仅机制未接实时数据，真机触屏/多浏览器未测 |
| 2026-10-30 M2.2 GPU训练与三方法对照 | executing-plans、test-driven-development、statistical-analysis、scientific-critical-thinking、scientific-visualization、verification-before-completion | 固定数据/模型/环境；BCE实际窗口梯度归一化、弱负例、独立预测/评分、三种子、公司配对bootstrap；一次独立审阅2Important先失败再修复 | 目标环境36测试全部通过；GPU FP32/BF16与参数更新、小批过拟合、3×2647训练更新和全883题评分；无最终test/旧heldout/付费调用，未接管中文模型；3Minor留档 |
| 2026-10-29 本平台组合诊断 | receiving-code-review、systematic-debugging、test-driven-development、verification-before-completion、Interactive-front-end、react-best-practices、frontend-testing-debugging | 真实POST先复现再修复；准确身份合并；服务端权重统一展示/指标/建议；独立Next运行包实际验证 | 10项组合/接口回归；临时空库与无模型密钥的生产包API、Edge桌面/窄屏与键盘验证；未使用真实账号写入或付费模型 |
| 2026-10-14 架构深入审阅 | scientific-critical-thinking、receiving-code-review、interactive-front-end | 区分证据与主张，逐项核对独立审阅；细化草稿/计算/保存和微交互边界 | 文档一致性与数学夹具复算；尚无浏览器、模型训练或运行时验证 |
| 2026-10-14 M1计划/M2数据先导 | writing-plans、analyze-data-quality、test-driven-development、jupyter-notebooks | 固定接口与验收；数据粒度、来源哈希、重复和标签完整性；研究工具先失败后通过；学习复现代码 | 5项工具测试与真实train/dev审计；Notebook未用Jupyter内核运行；没有产品或模型效果验收 |
| 2026-10-14 M1实现 | executing-plans、using-git-worktrees、test-driven-development、systematic-debugging、Interactive-front-end、frontend-design、react-best-practices、frontend-testing-debugging、requesting-code-review、verification-before-completion、finishing-a-development-branch | 模块边界、Decimal/版本契约、事务幂等、修订号隔离、悬停按压和证据联动；独立整分支审阅 |28后端/7前端/5研究测试与构建；IAB真实交互及故障恢复；无真机触屏、多浏览器或训练成绩 |
| 2026-10-14 前端重做 | Interactive-front-end、frontend-design、frontend-app-builder、imagegen、react-best-practices、frontend-testing-debugging | 读取真实参考，先生成完整概念图，再实现环形导航/联动视图/控件反馈；模块化组件和原请求隔离 |9前端测试、构建与IAB桌面/窄屏/键盘/断线恢复；概念与实现view_image对照；真机触屏未验证 |
| 2026-10-15 M2.1训练准备 | writing-plans、executing-plans、analyze-data-quality、test-driven-development、requesting-code-review、verification-before-completion | 已确认路线拆为3项任务；来源/标签/划分隔离、可追溯复核与资源闸门；真实数据重跑及独立审阅 |23项研究测试、6250/883准备及hash一致、90待复核、环境收据；未安装框架/下载权重/训练，CUDA未实测 |
| 2026-10-25 智投委接入 | brainstorming、writing-plans、executing-plans、test-driven-development、systematic-debugging、Interactive-front-end、react-best-practices、frontend-testing-debugging、requesting-code-review、verification-before-completion | 核对当前完整发布版与数据保留要求；隔离框架/账号边界、导航归属、只读导入、依赖闭包和状态保留 |32后端/12前端/6导入/3Node与构建、四页浏览器及离线恢复、PDF/六股票推理；无新大模型调用或真实账号登录，额外进程回收实测被自动审批拦截 |
| 2026-10-25 页面批注清理 | Interactive-front-end、frontend-testing-debugging、test-driven-development | 局部删除重复品牌/运行状态，保留账号和真实错误恢复；HTML呈现适配与API透传隔离 |4Node/12前端与构建，四页、864×871、桌面/窄屏浏览器及主题/登录/离线恢复通过；未触发模型或写原库 |
| 2026-10-30 学习实验室总览 | Interactive-front-end、GSAP官方4项、Hallmark、Open Design design-brief、Taste、Impeccable文档、UI/UX Pro Max、React best practices、frontend-testing-debugging、writing-plans、executing-plans、TDD、requesting-code-review、verification-before-completion | 独立模块、可解释合成均线、真实开发状态、作用域动画清理；选择性使用规范，不叠加无关模板 |18前端测试/构建、21项Edge浏览器检查；Hallmark/Taste静态0 FAIL；Impeccable引擎下载失败、两个自动render缺依赖；真机触屏未测 |
| 2026-10-30 智投委配色对齐 | Interactive-front-end、frontend-design、frontend-testing-debugging | 读取真实深色token；局部调整背景/绿金语义色/选中态/面板，不扩展业务 |构建、21项Edge浏览器检查、1440px/375px截图目视检查和diff检查通过；未重跑逻辑单测，真机触屏未测 |
| 2026-10-30 共同实验底座 | brainstorming、writing-plans、executing-plans、TDD、analyze-data-quality、Interactive-front-end、react-best-practices、frontend-testing-debugging、systematic-debugging、requesting-code-review、verification-before-completion | 数据粒度/时间资格、Decimal、无未来信息、先划分再标签、训练拟合隔离、来源/引擎指纹、独立记录和响应归属 |52后端/21前端/构建、新增14及原21浏览器检查；3项P2回归修复；真实行情、真机触屏、收益回测/训练未验证或未实现 |
| 2026-10-30 Hallmark/Open Design精修 | Hallmark app规范、Open Design ui-animation/decision-framework/component-patterns、Interactive-front-end、GSAP React、frontend-testing-debugging、TDD、requesting-code-review | 参考官方完整资源；保留绿金主题，配置/结果分区、真实状态与草稿区分、可访问页签、版本选择、短动效 |23前端/构建、10新增+14底座+21原工作区浏览器检查；Hallmark静态0 FAIL/5 WARN，自动render缺依赖；无真机触屏/录屏测量 |

| 2026-10-30 公开行情/双市场入门回测 | writing-plans、executing-plans、TDD、analyze-data-quality、systematic-debugging、Interactive-front-end、frontend-testing-debugging、requesting-code-review、verification-before-completion | 独立日历/来源凭据/UTC/费用与现金账本、因果信号、下一可用开盘、不可再投分红、零值与未知分离、异步归属、复现记录 |77后端/27前端/构建，17新增+45原浏览器；实际两市场API及官方2024/25日历核对；无真机触屏/新训练/实盘，PIT与成交规则子集限制明确 |

| 2026-10-30 预测基线/LightGBM/DLinear | writing-plans、TDD、statistical-analysis、Interactive-front-end、frontend-testing-debugging、systematic-debugging、requesting-code-review、verification-before-completion | 训练前协议、可执行标签与清除、独立评估标签、固定种子/验证早停、配对移动块区间、真实GPU更新、离线只读与版本绑定 |84后端/42研究/30前端/构建，16新+62原浏览器；真实双市场训练/冻结预测/独立评分，中文路径与空目录回归；无预训练/波动模型/真机触屏/实盘 |

| 2026-10-30 滚动/诊断/冻结预训练 | brainstorming、writing-plans、TDD、statistical-analysis、Interactive-front-end、frontend-testing-debugging、requesting-code-review、verification-before-completion | 8折因果划分/验证段置换/固定PSI、消融全报告、连续账本、冻结编码器+随机控制/同队列比较、模型缓存阶段SHA校验与只读UI |86后端/48研究/33前端/构建、16新增+78原浏览器；实际48模型54,531更新及GPU嵌入/读出，审阅修复后完整重跑；非盲测/基座微调，无波动模型/真机触屏/实盘 |

| 2026-11-04 波动预测与市况稳定性 | brainstorming、writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、frontend-testing-debugging | 用户授权自主规划下冻结代理/期限/市况与统计口径；分工实现模型和只读展示，真实CUDA训练；保留复杂模型不利结果和空市况 |96后端/65研究/38前端/构建通过，四份实际产物verified；真实空状态/隔离UI夹具检查完成，完整真实结果浏览器因服务未运行失败，独立整套审阅未完成；时间超限与待办见D22报告 |

| 2026-11-04 D22补充验收 | requesting-code-review、frontend-testing-debugging、Interactive-front-end微调、TDD | 独立审阅后补训练前/逐折SHA、残留折恢复、递归全前缀可用性；实际记录逐行重建，修正校准解释 |96后端/69研究/38前端、构建、17真实Edge浏览器检查和截图；复审无剩余Important/Critical；旧身份/数值不改，未重训；无真机触屏/多浏览器 |

| 2026-11-05 D23诊断 | brainstorming、writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、frontend-testing-debugging、requesting-code-review | 验证-only比例拟合/固定分箱、全窗口/覆盖缺口、不可变诊断来源绑定、父上下文联动与异步隔离 |103后端/75研究/43前端/构建，13新增+17原实际Edge检查；独立系数与评分复算、无Critical/Important；未新增行情/重训/风险预算或真机测试 |

| 2026-11-05 D24资格与独立校准准备 | writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、frontend-testing-debugging、requesting-code-review | 预定候选、来源/校验和/规范化版本、拒绝缺失/拆股、四段标签成熟清除、前瞻待积累、只读入口 |111后端/86研究/47前端/构建及9真实Edge；7实际采集/5可准备/2拒绝，876摘要和320分区独审一致；无新模型/前瞻成绩/PIT认证/真机测试 |

| 2026-11-05 D25五标的对照 | writing-plans、subagent-driven-development、TDD、Statistical Analysis、Interactive-front-end、frontend-testing-debugging、requesting-code-review | 有限预算/四角色隔离、独立校准、固定种子、来源归档、完整评分、请求隔离和局部去重校验 |80单元240CUDA模型169378更新；123后端/96研究/50前端/构建，9新+9原资格浏览器；1280预测独审复算一致，无Important/Critical；非零样本迁移/前瞻/交易成绩 |

| 2026-11-07 D32 财报语义v2 | TDD、dispatching-parallel-agents、requesting-code-review、PDF、Interactive-front-end、verification-before-completion | 已见18开发字段、行内单位/币种局部约束、数字年份流量表头、方法freeze后新公司视觉reference、独立只读发布 | 41结构＋306完整研究、207后端、113前端与构建通过；最终开发规则/模型各15/18无AI增益，新公司规则/模型均4/9、5拒答无AI增益，评估后不调方法 |
