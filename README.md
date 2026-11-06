# 知衡 FinLab

**Financial AI Learning & Research Platform · 金融 AI 学习与实验平台**

> 让金融有据，让模型可验。

知衡面向金融与人工智能的初学者，将财报证据、双市场量化实验、模型训练和结果核验放进同一个学习工作区。项目强调可复现的计算、可定位的来源与如实保留的失败结果，适合课程研究、比赛和作品集展示。

目前以 A 股与 BTC/ETH 的日频研究为主，逐步衔接基本面与事件研究。智投委 AI、量化实验室、现金流沙盘和训练评测保持独立入口。

## 功能概览

| 模块 | 已有能力 | 当前边界 |
| --- | --- | --- |
| 智投委 AI | 公司与同行研究、多角色分析、财报核验、原页引用、研究档案、组合诊断和既有价格实验 | 独立 Next.js 子应用；账号、财报库和模型配置须在本机单独准备 |
| 量化实验室 | 数据快照与交易日历、趋势与买入持有对照、BTC 周期假设、成本设置、回放与报告导出 | 教学性历史重建；来源资格与成交假设随实验保存 |
| 模型训练与评测 | 简单基线、LightGBM、DLinear、预训练模型对照、滚动验证、波动预测、校准、市况与失败区间诊断 | 训练、早停、校准与评估隔离，复杂模型不保证超过简单基线 |
| 前向观察 | 五标的冻结模型预测登记、真实接收时间、到期独立评分、来源与模型指纹 | 不补记错过窗口；自动运行依赖另行配置的本地任务 |
| 财务语义校验 | 金额/比率/每股区分、当期与上期列归属、调整列、行内单位、日期表头和拒答解释 | 参考待人工审核；缺币种或跨页证据时可能拒答 |
| 公告与事件研究 | 公告资格审计、原文证据、正常收益模型、异常收益 AR 与累计异常收益 CAR | 单事件教学回放不建立因果结论 |
| 现金流沙盘 | 独立模块入口；已有回款延迟与稳态应收占款敏感性工具 | 逐期企业现金流预测与优化仍待开发，不能用年度财报伪造周流水 |

## 最新进展

截至 **2026-11-07**，D32 已完成行内单位和数字日期表头解析改进，并在方法冻结后评估另外三家公司的季度报告：

| 样本 | 结构规则 | 结构规则＋固定 Qwen | 拒答 |
| --- | --- | --- | --- |
| 已见六报告：18 个开发字段 | 完整正确 15/18 | 完整正确 15/18 | 各 3 项 |
| 新三报告：9 个评估字段 | 完整正确 4/9 | 完整正确 4/9 | 各 5 项 |

新报告为格力电器、兴业银行、长江电力的 2025 年一季报。拒答主要来自币种适用范围和跨页表头/单位缺口。本轮尚未证明模型相对结构规则的增益，也没有进行金融微调。D31 与更早的代码和实验结果保留原身份。

D32 本机验收记录：研究 306 项、后端 207 项、前端 113 项测试通过，生产构建通过；实际 Edge 页面、窄屏和来源一致性已验证。构建仍有约 554 KB 单包体积提示。以上为本机记录，不代表 GitHub CI 已运行。

- [D32 方法、结果与限制](docs/research/2026-11-07-filing-semantics-v2.md)
- [D32 验收收据](docs/research/2026-11-07-filing-semantics-v2-receipt.json)
- [D31 财务语义校验](docs/research/2026-11-07-filing-semantics.md)
- [完整研发状态](docs/status.md)

## 架构与目录

```text
apps/
  web/                 React + TypeScript + Vite 主平台
  committee/           独立 Next.js 智投委子应用源码
backend/
  src/platform_app/    数据契约、证据、领域计算、适配器与 FastAPI
  tests/               后端验证
research/              独立环境中的准备、训练、预测、评分与实验协议
integrations/          智投委接入与上游版本清单
scripts/               本地启动、公开数据准备与浏览器验证
docs/                  架构、研究报告、设计规范与验收记录
```

核心边界：前端负责交互；金额最终计算使用后端 Decimal；普通网页请求不启动训练；预测先封存再评分。每轮研究单独保存配置、来源、代码和模型身份，旧结果不会因新方法上线而被重新命名。

技术栈包括 React 18、TypeScript、Vite、GSAP、FastAPI、Pydantic、SQLite；智投委保留独立 React/Next 依赖。离线研究使用 PyTorch、LightGBM 等，研究依赖与应用依赖分开安装。

## 本地运行

以下示例适用于 Windows PowerShell 7。准备 Python 3.12+、Node.js 22.12+ 和 pnpm；离线研究建议独立使用 Python 3.12 环境，CUDA 依赖按本机 GPU 配置。

```powershell
git clone https://github.com/CenMunn/ZhiHeng-FinLab-Financial-AI-Learning-Research-Platform.git
Set-Location ZhiHeng-FinLab-Financial-AI-Learning-Research-Platform

python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.lock
& backend/.venv/Scripts/python.exe -m pip install --no-deps -e backend
pnpm --dir apps/web install --frozen-lockfile
```

分别在两个终端启动：

```powershell
# 终端一：API
./scripts/start_backend.ps1
```

```powershell
# 终端二：前端
./scripts/start_frontend.ps1
```

- 主平台：<http://127.0.0.1:5174/>
- 量化实验室：<http://127.0.0.1:5174/#/lab>
- 训练评测：<http://127.0.0.1:5174/#/training>
- API 文档：<http://127.0.0.1:8010/docs>

**首次克隆只包含源码、协议和可分享文档。** 实验快照、权重、已发布结果包和原账号数据库不随源码上传。未准备相应来源时，页面可能显示待准备、来源缺失或智投委未连接；这不等同于已恢复原机器上的实验与账号。

完整智投委还需要按[接入说明](docs/committee-integration.md)准备本地构建、运行配置和数据绑定。准备完成后，可使用 `./scripts/start_platform.ps1` 启动完整平台；已占用端口时脚本会退出，不结束已有进程。配置中的密钥仅保存在本机。

## 研究环境与验证

先阅读 [研究目录说明](research/README.md) 和对应实验报告。`research/requirements-*.lock.txt` 记录各阶段依赖；模型权重、公开数据的固定版本与 SHA 校验须另行准备。PDF 离线准备还需要对应 PDF 工具，不能仅凭应用依赖运行全部研究。

常用验证命令：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'backend/src'
./backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -v
pnpm --dir apps/web test --run
pnpm --dir apps/web build

# 独立研究环境与所需资产准备完成后
./research/.venv/Scripts/python.exe -m unittest discover -s research/tests -v
```

部分来源审计、归档测试和浏览器脚本需要本地实验资产或运行服务。各报告说明实际运行条件、测试范围与未覆盖项；缺失归档时的跳过不能算作对应实验复现成功。

## 数据与发布范围

仓库保存源码、依赖锁、实验配置、来源清单与小型研究/验收记录。默认排除：

- `.env`、密钥、本地账号与研究数据库；
- `.local/`、虚拟环境、依赖目录和构建缓存；
- `research/data/`、`research/artifacts/`、`backend/data/`；
- 模型权重、下载缓存、原始 PDF、行情快照及大型训练产物。

数据准备须遵守原来源使用条款；历史行情重建不等于严格的历史时点可得性认证。财报参考仍需人工审计，查询给定的期间/范围不能算作模型独立识别能力。所有拒答、无效输出与不利结果应保留在实验分母中。

## 项目路线

1. 共同实验底座：来源快照、交易日历、划分、费用、记录。
2. A 股与 BTC 入门对照：调参、历史回放、失败区间与报告。
3. 基线与真实模型训练：滚动验证、特征诊断、波动与风险预算。
4. 基本面与事件研究：财报语义校验、证据审计与公告实验。**当前重点**。
5. 后续评估横截面选股、更多模型与 Agent；高频另立阶段。

下一项研发优先处理跨页表头、单位及币种适用范围。前向观察独立积累到期样本，现有结果不构成收益保证。

## 来源与说明

智投委子应用基于 [CenMunn/zhitouwei-ai](https://github.com/CenMunn/zhitouwei-ai) 接入，版本与修改见 [接入清单](integrations/committee-manifest.json)、[上游清单](integrations/committee-upstream-manifest.json)和[复用说明](docs/reuse-inventory.md)。界面交互参考学循 FlyLoop，并采用本项目的 Interactive-front-end 规范。

项目许可证见 [LICENSE](LICENSE)；第三方源码、依赖、模型和数据分别遵循其原始许可与使用条件。
