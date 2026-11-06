# 智投委模块与功能归属

2026-10-25。用户明确要求接入目前完整智投委，并沿用现有账号、研究历史和已导入财报。

## 接入来源

基础版本为已发布的DeepSeekFlash-DecisionNewsFix-20261018，原Next构建ID `7xwGAKDfrkCmOvgA2Yrsw`。该版本在原workspace基础上增加了评分复核、新闻刷新、报告下载响应校验等11个源码文件。源码在`apps/committee`，2026-10-29已加入本平台组合重复持仓修复；当前文件SHA、构建身份和4页面/26API路由见[integration manifest](../integrations/committee-manifest.json)，原版清单保留于[上游快照](../integrations/committee-upstream-manifest.json)。实际依赖按发布包解析，并保留各开源许可证。

以独立Next.js子应用保留全部页面、API和原交互，主平台内嵌完整工作区；本地网关保留Cookie、请求体、下载和流式响应，限定回环访问并限制允许的父页面。React18/Vite平台与React19/Next运行时不混装。源码已纳入项目，编译运行包和环境绑定位于被Git忽略的.local，不是只保存外部网站链接。

另保留原价格实验的训练、冻结准备和验证三份脚本，便于后续理解LightGBM特征、时间划分和参数冻结。它们依赖原冻结实验结构，本轮未执行、未读取其旧评测路径；新的训练仍按当前research独立协议设计。

## 功能归并

| 归属 | 功能与设计 | 实现位置/入口 |
|---|---|---|
| 智投委·投研工作台 | 标的识别、单公司/同行研究、阶段状态、多角色洞察、辩论、条件性研究决议 | 原首页及research APIs |
| 智投委·评分复核 | 条件性评分、资料补充、人工复核与审计记录 | research/[id]/score-review |
| 智投委·行情与新闻 | 行情/K线/指数、指数百科、快照库、实时公司新闻与刷新 | 首页、indices/quote/kline/universe/board、research/[id]/news |
| 智投委·个人工作区 | 原账号登录/注册/管理、历史研究、自选与组合 | 原Auth/Session/Watchlist/Portfolio链路 |
| 智投委·财报核验与比较 | 已登记事实、财务口径、引用原文、计算核对、同行比较、报告导出 | #/committee/evidence → 原/evidence |
| 智投委·财务原页 | PDF原页导入、页码映射、问答/生成/复核与重开 | #/committee/filings → 原/filings |
| 智投委·价格预测实验 | 已有六股票LightGBM模型、冻结快照/实时日线推理、误差与限制 | #/committee/forecast → 原/forecast |
| 智投委·回款压力推演 | 原M1来源查看、赊销/延迟假设、敏感性曲线、情景比较/保存/历史 | #/committee/scenarios → 原生RiskModule与M1 API |
| 现金流沙盘 | 未来收付款事件、现金平衡、预测与优化 | 独立模块，尚未实现 |
| 金融AI训练评测 | FinQA证据排序、训练/实验协议与评测 | research已有M2.1离线准备；应用页面/神经模型尚未实现 |

财报证据、比较、研究历史统一由智投委入口承载；原M1“企业风险推演”不再作为平级重复入口。M1金额计算、SQLite档案和hash保持原值，领域代码继续留在risk/evidence，供未来复用。价格预测实验是原智投委已有模型，不能称为本平台FinQA训练成果或收益保证。

## 数据和账号

Next子应用直接绑定原运行目录的research.db与filing-documents；不复制账号库，不清空历史，不修改原公网启动器。配置文件由进程从原位置加载，不读取到交付文本或复制密钥。

M1仍读取backend/data/scenarios.sqlite3，旧情景不丢失。它是原平台的单机本地档案，尚未按智投委账户分配owner；本次只是归并功能入口，不宣称跨系统单点登录或M1多用户授权。不要将当前本地服务直接部署为多人公网系统。

源码/运行包导入拒绝.env、数据库/私钥文件、upload/heldout/evaluation等目录；不读取旧保留题或比赛评测答案。原始财报和已有模型产物保持各自来源语义，不加入FinQA训练管线。

## 本机启动

已配置机器在项目根运行：

```powershell
& ./scripts/start_platform.ps1
```

打开 http://127.0.0.1:5174/#/committee/research 。服务分别为平台5174、M1 API8010、智投委网关3155、内部Next3165，均绑定127.0.0.1。启动器不结束已占用端口的旧进程；本轮启动失败时只回收本轮登记且进程身份匹配的自有进程树。手动停止整平台启动器登记的进程：

```powershell
node scripts/stop_platform.mjs
```

停止入口核对PID、创建时刻、项目路径与角色脚本，拒绝结束PID被复用或路径不匹配的服务。通过独立开发命令启动的服务不在此清理范围。

单独运行智投委：`node scripts/start_committee.mjs`。单独平台前后端仍可使用原scripts/start_backend.ps1与start_frontend.ps1。智投委未启动时显示真实离线/版本状态与重试；不阻断原生回款推演。

## 运行包与可迁移性

首次在这台工作区准备运行包：`python scripts/import_committee.py`。采用发布版白名单目录和显式Next构建目录；重复导入核对hash，遇到本地修改拒绝覆盖。Windows目录junction需实体化，并补齐pnpm依赖和非可选peer依赖的闭包，不能只复制链接表面。

本地配置位于`.local/committee/config.json`，字段：runtimeDir、databasePath、filingsDir、envFile、port、upstreamPort、platformOrigin。新机器需重新提供运行包、合法模型配置和原数据绑定；Git源码快照不包含私有账号库、上传文件或密钥。当前不是脱离这些数据文件的空库通用部署包。

本平台源码修复后的本地重新打包方式：先在apps/committee执行`pnpm install --frozen-lockfile --ignore-scripts`、`pnpm exec prisma generate`、`pnpm run typecheck:app`，设置`NEXT_BUILD_DIR=.next-portfolio-webpack`后执行`pnpm exec next build --webpack`。服务停止时，在根目录执行`backend/.venv/Scripts/python.exe scripts/import_committee.py --local-build --build-name .next-portfolio-webpack --release <本地版本名>`。工具复用白名单和依赖闭包规则，创建新的版本目录并更新运行清单/配置，保留原账号与财报绑定；不修改原项目。每个BUILD_ID只能打包一次，拒绝覆盖已有版本。

## 验证边界

原发布版的历史测试/评测不自动作为此次接入的新成绩。接入验收分别记录本轮导入、健康/代理/导航测试、生产构建和实际浏览器路径；新研究模型调用、所有股票外部源和全部历史记录语义不由一次接入证明。详见后续验收记录。
