# 当前平台组合重复持仓修复

2026-10-29，作用范围为financial-risk-platform内置智投委。用户明确撤销对公开仓库的修复要求；没有向GitHub推送或创建PR。初步核对的远端main为ea9f540，仅作为定位线索。本平台源码中的同类问题已由实际路由测试复现。

## 计算与展示口径

归一化之前，按唯一的市场+股票代码归并。复用findStock并增加可选exact模式，不改变普通研究查询的模糊匹配。代码、完整名称、完整别名及前端的名称(代码)选择标签均可识别；标签名称与代码冲突、市场后缀冲突、模糊子串或不唯一别名不能推定为同一股票。未识别条目只合并去除两端空白后完全相同的标签，不猜测其市场或名称关系。

合并后的权重为HHI、单票最大权重、风险等级、行业暴露、已识别计数、LLM提示词及无模型降级建议的共同输入。接口保持原result字段，新增可选holdings，前端直接绘制该服务端权重；不在浏览器从原行重新计算。数据库仍保存原始输入和新结果，历史诊断不重算、不改写。

用最大输入权重缩放后求和，避免有限但很大的数相加溢出。固定身份排序和组内求和次序，避免输入行排列改变输出/建议。归一化百分比保留15位有效数字，去除30.000000000000004这类算术噪声；已用实际POST回归检查恰好30%的边界。风险阈值保持原政策：HHI>=4500或最大单票>40为Very High；HHI>=3000或单票>30为High；HHI>=1800为Medium，其余Low。HHI仍按既有口径取整数。

## 自动化验证

- tests/portfolio.test.cjs直接加载真实POST路由及股票/组合计算，仅隔离账号认证、持久化写入和LLM外部调用；保存到内存而非现有数据库。先观察到3400!=5200，再修复通过。
- 10项组合测试覆盖重复、不同股票/同业、代码/名称/别名/选择标签/市场限定、未知和冲突身份、模糊误合并、别名歧义、顺序、归一化、极大权重、空/非法输入、行业/建议/存储/模型提示一致性、风险阈值及恰好30%时的浮点噪声。
- Node根测试命令node --test tests/portfolio.test.cjs tests/*.test.mjs：14通过。
- 导入/打包unittest：7通过，其中新夹具验证原账号绑定与上游清单保留、独立新包和显式PDF外部依赖补齐。原6项导入安全测试继续通过。
- 后端unittest：32通过；有现有Starlette/httpx弃用警告。
- 主前端Vitest：12通过；TypeScript和Vite生产构建通过。
- 智投委typecheck:app、4个改动实现文件定向ESLint通过；Next16.3.7 webpack生产构建通过。原配置跳过Next内置类型检查，因此另运行typecheck:app，不把构建成功冒称类型检查。

## 运行包与数据边界

保留原发布版清单integrations/committee-upstream-manifest.json，当前清单记录本地源码hash与新构建身份。本地打包工具将public/static和PDF/Prisma的生成客户端及依赖闭包实体化到新的版本目录，原运行包不覆盖。账号数据库、财报目录和环境文件路径继续沿用；打包不读取.env或数据库内容。

第一次Turbopack包未通过依赖检查：缺pdf-parse且Prisma别名包未带生成客户端。该版本未交付；改用webpack构建并补齐显式外部依赖后重新验证。不隐藏这些初次失败，也不把旧运行包测试当作新包通过。

scripts/verify_portfolio.cjs在操作系统临时目录新建空SQLite，使用该独立测试账号执行真实注册、认证、组合POST和浏览器。模型密钥为空，市场行情请求在浏览器隔离。脚本不使用本地配置中的原数据库/财报/.env路径，只读取新运行包位置。

## 最终生产包实测

当前本地发布为Committee-PortfolioIdentityFix-20261029，webpack构建ID为8qbH7PFegsy1GDb7aQjfJ，实体运行包15851文件/815077202字节。启动器已核验运行hash并实际启动平台5174与智投委3155/3165。

`node scripts/verify_portfolio.cjs`在该运行包下通过真实HTTP与页面验证：

- 临时账号注册201；真实组合POST200，HHI5200、单票60%、Very High，服务端holdings两项。
- 30/20/20/20/10的真实POST为HHI2200、Medium，不因浮点噪声升档。
- 未登录401、跨源写403。
- Edge/Playwright实际进入组合体检、添加三行、键盘提交、观察两条60.0%/40.0%持仓、行业名单；Escape关闭。1440×1000及390×844、减少动态模式均验证；pageerror和控制台错误均为0。Browser插件未提供，因此使用本机Playwright。
- [桌面截图](<C:/Users/g'g/AppData/Local/Temp/platform-portfolio-rCb5Hd/desktop.png>)、[窄屏截图](<C:/Users/g'g/AppData/Local/Temp/platform-portfolio-rCb5Hd/mobile.png>)、[机器收据](<C:/Users/g'g/AppData/Local/Temp/platform-portfolio-rCb5Hd/report.json>)保存在操作系统临时目录。页面无空白或框架错误覆盖层。

`node scripts/verify_committee_runtime.cjs`在最终新包下通过：合成一页PDF实际解析、Prisma原数据库只读计数User8/ResearchSession81、六股票冻结模型hash与六次实际树模型推理。数据库写入0、语言模型调用0。有既有Node typeless module警告，不影响检查。

最终另外执行`node scripts/verify_committee_browser.cjs`：平台入口四页、原生M1计算69158975.62、历史抽屉、草稿保留、登录弹层、窄屏、减少动态、键盘、断线重试均通过；此前去除品牌/连接栏的效果保留。pageerror为0，控制台仅有故意注入的健康503。全部214个当前源码/资产hash与清单一致。浏览器验证完成后再次以SQLite只读连接确认原账号8个、研究81条。

测试创建与写入的SQLite仅为临时空库；原research.db没有执行迁移、删除、回填或重新计算。没有登录原真实账号，不验证真实付费模型输出；未用实体触屏或覆盖其他浏览器。不将集中度规则称为模型训练或收益预测。
