# 总览视觉与技能应用记录

目标：成人初学者能从任务进入金融实验；保留原智投委完整工作区，不把它当成整个系统的首页。

首版曾采用中性炭黑。用户随后要求更贴近智投委AI，现按该子应用Aurora Terminal深色token调整为深墨蓝背景、翡翠绿操作与选中态、金色强调/均线、浅蓝灰辅助文字，面板采用细描边和轻微纵向层次。字体保持中文操作可读性，颜色和字体统一通过token；参数、选中、焦点与业务状态分开。模块、文案、数据和交互逻辑未改变。

GSAP-Skills采用官方 React useGSAP、作用域、matchMedia及清理，教学市场切换时小幅过渡。Interactive-front-end负责按钮悬停凸起/按压、键盘/触控及图表读数联动。减少动态效果下不移动或缩放。

Open Design的design-brief只作为设计维度规范：色板、强调、正文、标题、布局、情绪、密度、限制分别明确。本项目使用已有视觉约束和独立token，不执行其通用色板生成器。Git稀疏下载失败后，从固定commit获取该SKILL.md；完整Open Design桌面应用和MCP没有安装。

首版Hallmark和Taste按应用屏幕范围使用，首版静态检查均为0 FAIL；短说明文本的measure提示及继承前景色提示人工判断保留，悬停阴影因用户明确要求凸起而保留。它们的自动render缺puppeteer-core，未执行。随后配色调整以用户指定的智投委风格为准，未重跑这两个静态审美工具；实际重新运行21项Playwright/Edge浏览器检查及生产构建，并目视检查桌面/窄屏。没有为重复浏览器引擎再加依赖。

Impeccable上下文引擎0.1.18下载失败，走文档规定的直接读取上下文回退；没有完成该工具的自动审计。UI/UX Pro Max第一次匹配Enterprise Gateway（营销），第二次匹配Educational App（儿童/黏土风），都不符合本项目；不把结果持久化为设计系统。

所有来源按commit记录在相邻JSON；全局技能目录附UPSTREAM-LICENSE.txt。六个来源共九个本地skill目录。未安装Open Design全目录、未执行远程安装脚本、未发布。

首版当时的局限：合成信号不是回测；后续已完成合成日线底座，见研发状态。现金流逐期沙盘和网页训练仍未实现。FinQA摘要保持原任务。用户再次提供Hallmark/Open Design地址后的补充资源与页面精修见[后续记录](2026-10-30-hallmark-open-design-refinement.md)；当前为6个来源10个本地skill目录，不安装整个Open Design应用。
