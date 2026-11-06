# M1 implementation ledger

Plan: docs/superpowers/plans/2026-10-14-m1-evidence-sensitivity.md
Spec: docs/superpowers/specs/2026-10-14-platform-foundation-design.md (1.1)

## Setup and rulings

- 2026-10-14: User authorized continuation and selected agent-decided runnable visual direction. Use a light professional research workspace, then iterate from actual use.
- Ruling: Work in the already dedicated new project directory on feature/m1-foundation; it is an independent repository, not an existing shared checkout. A further linked worktree would add another project path without additional isolation benefit.
- Ruling: Windows execution uses native PowerShell/Python and this persistent ledger in place of POSIX task helper scripts. Preserve task bases, RED/GREEN results, commits and decisions here.
- Pre-flight 1→2: CaseSnapshot and calculate_delay contracts consumed unchanged by evidence adapter.
- Pre-flight 2→3: CaseService owns trusted snapshots; saving resolves by ID and checks hash before authoritative recomputation.
- Pre-flight 3→4: Save needs a created/replayed outcome for HTTP201/200. Return SaveOutcome internally; SavedScenario remains the external payload.
- Pre-flight 4→5: UI consumes explicit API structures and request revision; no browser financial arithmetic.
- Ruling: Add a small server-computed delay sensitivity curve to CalculationResult and a registered-source PDF endpoint to support actual graph/evidence interactions. Curve x-axis is delay days, never calendar time or a forecast. Both remain inside M1.
- Environment: Python3.14.4; project-local venv with pinned Pydantic2.13.4/FastAPI0.141.1/httpx0.28.1/uvicorn0.46.0. Full installed dependency versions will be locked.

## Tasks

- Task1: complete — RED missing platform_app captured; GREEN 7 tests passed. Exact rounding, strict decimals, canonical input and immutable nested models verified. Base d692e89.
- Task2: complete — RED missing adapter captured; GREEN 13 backend tests passed. Actual source adapter verified R=2103585508.31 CNY,D=365,value page69 and registered PDF hash; retained pending-human/time/version states. Base 8c5d309.
- Task3: complete — RED missing persistence module; GREEN 19 backend tests passed. Transaction-failure rollback, replay/conflict/project scope and reopen after case replacement verified. Fixed Windows SQLite connection lifetime in initializer and test harness (context manager commits but does not close). Base 340de62.
- Ruling: Idempotency fingerprints canonical original request including title, not the current engine result. Replays return the recorded result before resolving current source, preserving retry behavior after source/engine changes.
- Task4: complete — RED missing API captured; GREEN25 backend tests before final review,28 after fixes. Actual loopback health/case/calculate/save/reopen verified. Defaults8010/5174; pinned transitive lock; startup guards occupied ports. Base5330094; API comparison included in e596ea9.
- Task5: complete — RED missing reducer captured; GREEN5 state tests initially,7 frontend tests after review fixes; TypeScript and production build passed. Browser verified actual80%/15d result69158975.62, baseline/saved comparisons, evidence modal/Esc/focus, save/reopen, stale drafts, offline retry with same key, narrow width and reduced motion. Base ccb2eb4; implementation e596ea9. Evidence: docs/verification/2026-10-14-m1-browser-qa.md.

## Final review and delivery

- Fresh whole-branch reviewer: gpt-6-astra, read-only range d692e89..e596ea9, no heldout/env access. Critical0; Important3 (source identity, calculation identity, history availability).
- Final: fixed source identity/availability — test_old_saved_source_never_serves_new_registered_bytes RED200→GREEN409; separate status query and SHA-bound PDF URL; saved payload remains unchanged.
- Final: fixed calculation identity — test_save_rejects_displayed_calculation_version_mismatch RED201→GREEN409; expected_input_hash verified after replay lookup and before first write; reducer mismatched-result guard RED→GREEN.
- Final: fixed history availability — test_history_survives_missing_or_invalid_current_source_configuration RED startup errors→GREEN for missing JSON, invalid JSON and malformed rows; no-current-case UI uses saved snapshots with recalculation disabled. Browser separately checked a copied DB against missing sources on8011/5175; temporary services stopped.
- Final: fixed comparison version stall — reviewer initially Minor; effect regraded Important because old-engine result could load indefinitely. api.test.ts RED resolved different identity→GREEN explicit version error. Suite28backend/7frontend/5research passed; build passed.
- Final: minor (deferred): Network failure text is currently the native “Failed to fetch”; retry works. Localize messages in next UI polish.
- Final: Ruling: Reviewer delegated browser judgment to root — completed actual browser tests and retained evidence — cost if wrong: browser coverage is limited to Codex IAB, not every browser/device.
- Final: Ruling: Reviewer did not independently re-audit original financial PDF or research audit — retain pending-human quality and unchanged original audit receipts, verify registered PDF bytes/SHA only — cost if wrong: numerical source may still need human correction; no financial certification claim.
- Ruling: Keep independent feature/m1-foundation locally; no base/main branch or remote integration requested — cost if wrong: user must choose integration destination later. Finishing skill used for verification/clean checkout; its generic integration menu is not needed for this authorized local delivery.
- All setup rulings retain these costs: independent checkout (later integration); native Windows ledger (helper scripts not automated); server curve/PDF endpoints (small contract surface); original-request idempotency (edited payload needs new key).
# 2026-10-15 M2.1 执行记录

用户批准按下一步建议执行。开始于1abb2a8，clean，继续现有独立研发目录与feature分支，不启动新的产品/训练阶段审批。使用M2.1计划逐项实施。

Task 1：6项准备测试先因缺实现失败，再全部通过。真实固定快照生成6250训练题、883开发题；RE/2010/page_120.pdf-2因text_-1隔离，未修原始数据。34/7条超过5项gold的题保留。推理与评分文件分离；另外生成仅训练部分的公司隔离诊断划分，不能与官方协议混称。

Task 2：5项标签测试缺实现失败后通过；生成原训练先导30题/90候选任务。真实check结果90 pending、0 confirmed_conflict。允许部分复核，记录缺失；结构验证不证明真人身份。BCE稳定形式、梯度、完整证据覆盖指标与同学咨询问题已写入规范。领域负例二次人工复核属于B3资格，当前不宣称已满足。

Task 3：4项环境测试缺实现失败后通过。RTX5060 Laptop8151MiB，内存约16GB但空闲不足4GiB启发式门槛；当前应用venv缺torch/transformers。默认检查不导入torch；显式请求CUDA smoke因未安装跳过。官方文档核对表明不能仅因Python3.14就判不支持，实际训练组合留待独立环境wheel解析与实算。

最终独立审阅：/root/m2_readiness_review只读审阅并用夹具复现2项Important，未读原始逐题/保留集。1）create_package未核对manifest身份；2）仅30题数量检查允许替换原抽样。两项回归先失败（7个子案例），再增加身份校验与隔离前固定ID集合后通过；另验证隔离先导题不替补。最终研究测试23项通过。真实清单重生成，30题90候选不变；准备manifest收据已更新。原始数据和应用无修改，保留本地feature分支。

# 2026-10-25 智投委完整接入

用户直接要求完整接入，异步确认保留原账号、研究历史、财报。基线c8c0d1f，继续独立研发目录和feature分支。读取指定聊天，发现实际10/18发布版比原workspace多11个功能源码，采用发布版7xwGAKDfrkCmOvgA2Yrsw，不按旧workspace截取缩水页面。

Task1：只读白名单导入213个源码/公开资产/配置；4页面26API。完整Next以隔离origin嵌入主平台，源码、运行清单、统一启动和健康契约均纳入本项目；.local运行包不入Git。Windows原依赖junction需补pnpm siblings、非可选peer与Prisma生成客户端；逐次按模块解析路径诊断、夹具复现后修复，最终15636运行文件/782663364字节全部校验，健康ready。

Task2：集成健康仅返回固定回环origin、构建ID与状态，超时/错版/错误服务不报ready；认证Origin、Cookie和下载头按原链路透传。健康4测试、Node代理2测试通过。平台可独立于原M1来源状态打开。

Task3：默认智投委，原M1推演/证据/比较/历史归于#/committee/scenarios；旧#/risk归并。保留frame与M1组件以保护草稿；4页与M1实际浏览器往返、离线恢复、键盘/窄屏/减少动态通过。浏览器发现favicon404，补图标后复测仅有预期503故障注入日志。

Task4：独立审阅3项Important：敏感文件类型、父级junction越界、部分启动失败恢复。前两项红绿回归；后者增加本轮进程登记、PID/创建时刻/角色/项目校验和仅自有树回收，身份单测通过。额外真进程回收测试被自动审批blocked by policy拦截，未执行、未绕过，按未验证记录。

实际验证：32后端、12前端、6导入、3Node通过，生产构建通过；6冻结股票推理、合成PDF解析、原库Prisma只读计数通过。原8用户/81研究、311分析/200辩论等表计数前后相等，M1四情景保留。无新大模型调用、原库写入、原项目源码改写或公网发布。原价预测实验不作为本平台FinQA训练成果；当前用户需求调整优先，后续再回到M2.2。

## 同日页面批注：清理重复品牌与运行状态

删除平台连接工具条与本地状态标签；通过集成网关为四个HTML页面加载统一presentation.css，隐藏子应用重复品牌、导航、时钟、团队署名和页面品牌抬头，保留账号/登录/主题及免责声明。原发布包和来源hash不改写，API、下载和模型输入不做文本替换。HTML头部流式插入样式链接，移除变动响应的Content-Length/ETag；JSON与请求体透传回归通过。

Node新增HTML呈现回归先失败后通过；3网关+1停止身份测试、12前端与构建通过。浏览器四页无可见旧品牌/团队字样，登录弹层与主题切换可用；M1计算69158975.62、草稿保留、窄屏与离线恢复通过。1440×1000、864×871、390×844截图检查通过，无外层重复滚动条。控制台仅故意注入的503，无pageerror。只重启本轮自有集成服务，未改原公网或数据库。

# 2026-10-29：本平台组合重复持仓修复

用户将任务范围改为只修当前financial-risk-platform。已在内置智投委POST复现HHI3400而应为5200的问题；按唯一股票身份合并后计算，模糊名称不参与合并，未知标签仅精确去重。结果新增可选holdings，图表直接消费服务端结果；原输入、历史数据和认证路径保留。补10项不依赖模型密钥的计算/接口测试，包括实际归一化30%边界；本地重构建并打包独立生产版本，保留上游清单与数据绑定。另补本地包依赖闭包回归，解决首次Turbopack产物缺PDF及Prisma别名生成客户端问题。实际验证与限制见[记录](verification/2026-10-29-portfolio-duplicates.md)。未推送GitHub，未创建PR。

# 2026-10-30：M2.2独立GPU环境与真实三方法对照

用户授权M2.2并明确允许NVIDIA GPU；在research/.venv独立安装Python3.12.10/torch2.10.0+cu128/Transformers4.57.1，官方wheel与7个模型资产均核验hash。RTX5060实测原生sm_120、FP32/BF16前后向、非零有限梯度、参数更新及小批过拟合；smoke权重不复用。6250训练题/883官方dev的B0/B1/B2三个独立种子完整执行，B2共3×2647更新，Coverage@5均值80.52%、种子SD0.11个百分点，B0/B1为72.03%/74.86%。同候选、标签隔离、弱负例、完整分母及公司配对bootstrap均保留；2项重要审阅缺口先失败再修复。目标环境36测试、pip check、各检查点/预测/日志及最后13样本累积窗口校验通过，图表导出并实际查看。收据、环境锁定和限制见[结果](research/2026-10-30-m2-experiments.md)。官方dev有96重叠公司代理，不称未见公司泛化；B3/中文迁移/公司隔离诊断和3项Minor待后续。不改应用依赖/数据库，不读取最终测试，不发布公网或调用收费模型。

