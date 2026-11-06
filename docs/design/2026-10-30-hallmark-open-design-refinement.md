# Hallmark与Open Design：前端精修

用户再次提供两个官方地址，要求提高美观性和交互性。已重新核对：

- [Nutlope/hallmark](https://github.com/Nutlope/hallmark)，main仍为 `4f6a46c6dc325d40ab268c93e25c7b96676ebccd`，此前已完整安装。
- [nexu-io/open-design](https://github.com/nexu-io/open-design)，main仍为 `12d970eacc8971150e3c76470d2a9afe16dc2ed1`。此前只安装design-brief，本轮补齐ui-animation完整目录：24个文件、185437字节，包含原LICENSE、SOURCES、参考与测量脚本；未执行测量脚本。源文件hash见[下载清单](2026-10-30-open-animation-files.json)。本地安装目录open-design-ui-animation，下回合可发现，本轮直接读取。

直接匿名GitHub目录请求曾返回403限流，已改用已连接GitHub获取文件清单、从固定commit原始地址下载；未更改认证、未覆盖已有目录、未安装整个Open Design应用/MCP。

## 采用与取舍

Hallmark按app screen规范处理层级、密度、表格、焦点、真实状态和主次，保留智投委Aurora Terminal深墨蓝/翡翠绿/金色。Open Design采用ui-animation的目的/频率判断、即时按压、短上下文过渡和减少动态效果。另读取trading-terminal设计系统，只借鉴数据对齐与明暗层级，不采用面向专业交易员的全等宽、微小字、极高密度或额外买卖语义色。

## 实际改动

- 共同底座由长纵向表单改为桌面左侧配置/历史、右侧结果；窄屏顺序为配置、结果、历史，DOM与视觉阅读顺序一致。
- 未运行或修改参数时显示“尚未检查”的配置预览，训练/验证/测试数量联动。只是前端草稿计数，不代替服务端as-of和数据资格检查，非法划分不绘制合法比例。
- 已保存记录按结果概览、指标明细、来源与口径切换；支持方向键、Home/End、单一Tab入口及关联tabpanel。金额与指标仍来自保存结果；明细保留完整JSON导出。
- 选中历史保持高亮，显示实际时间与输入指纹前缀，区分同日多版本。
- 首页智投委入口采用较宽独立区，现金流/训练为较轻的并排分区；全部入口保留，没有复制智投委品牌或混合业务模块。
- 只在用户切换结果时采用180ms/4px的短过渡，现有GSAP作用域/matchMedia清理；没有新动画依赖、全页滚动揭示或假进度。实际等待时显示真实busy反馈，减少动态效果下无位移/旋转。

后端、API、金融计算、数据快照、原账号库和训练结果均未修改。保留当前工作区此前未提交成果，无源文件删除。

## 验证结果与限制

23项前端测试与生产构建通过；新增2项草稿划分测试先观察缺模块失败，再实现。新增10项真实Edge浏览器检查通过：结果切换/键盘、草稿失效、比例联动、窄屏、减少动态、历史选中与首页入口。原14项底座和21项平台浏览器回归亦通过，共45项，未出现本轮未处理页面错误。独立代码审阅无Critical/Important或需行动的Minor；审阅者未独立重跑浏览器，浏览器由主执行者实际运行。

Hallmark静态检查0 FAIL、5 WARN。短说明文本的measure提示及既有模块继承前景色提示经目视检查保留。自动render仍缺puppeteer-core，未执行该层，不能称其渲染审计通过；实际渲染以已有Playwright/Edge验证。无Browser插件，按测试技能使用现有Playwright，不新增浏览器依赖。

目视比较1440×1000、375×1000，另外检查768px；真机触屏与多浏览器未覆盖。本轮没有执行录屏动效测量，不将代码里的时长当实测性能。

复现命令：`pnpm --dir apps/web test --run`、`pnpm --dir apps/web build`、`node scripts/verify_frontend_refinement.cjs`、`node scripts/verify_foundation_browser.cjs`、`node scripts/verify_learning_browser.cjs`。新截图/收据位于系统临时目录financial-ui-refinement-20261030；before.png为修改前同一底座。
