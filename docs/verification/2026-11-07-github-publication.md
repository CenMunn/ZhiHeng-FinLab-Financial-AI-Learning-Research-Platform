# 知衡 FinLab 公开源码发布记录

日期：2026-11-07。目标：CenMunn/ZhiHeng-FinLab-Financial-AI-Learning-Research-Platform，公开 main。

## 发布范围与审计

- 初始清点 721 个 tracked 与 nonignored untracked 候选；排除 6 张历史智投委本机截图及 1 个旧评审 ZIP 归档，增加本记录，发布 716 文件（含保留的远端 LICENSE）。源码、配置、锁文件、文档及小型研究收据保留。
- 不包含 .env、原账号数据库、上传财报、research/data、research/artifacts、backend/data、.local、虚拟环境、node_modules、权重、数据集、快照及机器截图。未打开私有数据库或 FinQA 保留集。
- 凭据/邮件扫描命中经核对为 risk- 运行标识、矩阵乘法、URL userinfo 拒绝测试；无真实密钥发现。注册测试密码改为每次随机生成。本机来源路径作为 provenance 保留，冻结研究源码/配置/规格及收据未清洗重写。
- 原始 .git 历史含已排除截图，因此公开仓库使用独立发布快照，不推送原历史。原 checkout 和实验数据保持；本地发布快照在被忽略的 .local/publish-zhiheng。
- 依赖、上游许可和来源清单保留；保留用户在远端初始化的 LICENSE；第三方代码仍按各自许可及来源清单使用。

## 验证与交付

- 发布前前端 20 文件/113 测试通过；生产构建成功，保留已有大 chunk 提示。注册验收脚本 node --check 通过，未执行注册写入。完整研究和后端验证属于 README 标明的本机历史记录。
- CLI 到 github.com:443 连接失败，GitHub 连接器写入返回 403 后改用现有本机代理恢复 CLI 网络；读取远端已有 Initial commit（LICENSE 与占位 README），以它为父提交追加源码快照，无 force 覆盖。
- 发布后检查远端 main commit、完整树和 README 字节摘要；实际 SHA 与核对结果由交付消息记录，避免报告自引用哈希。
- 无远程部署或服务上线；clone 后需按 README 安装依赖并独立准备经授权数据，历史账户及训练归档不会随仓库提供。
