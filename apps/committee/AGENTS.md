# 智投委发布版源码

此目录基于已发布的DeepSeekFlash-DecisionNewsFix-20261018完整源码白名单快照，受根AGENTS.md约束。原始文件hash保留在../../integrations/committee-upstream-manifest.json；当前本地修复后的hash与构建身份在../../integrations/committee-manifest.json。

- 用户要求保留完整功能与原交互。对本应用的修改需读当前安装Next版本的node_modules/next/dist/docs相关指南；现有锁文件与实际发布版对应。
- 主平台运行.local/committee/config.json所绑定的独立生产包。修改本目录源码后，必须重新构建、补齐PDF/Prisma/pnpm依赖闭包并更新运行清单，不能宣称源码编辑已自动更新生产包。当前使用.next-portfolio-webpack的webpack构建，scripts/import_committee.py --local-build打包到新的.local/committee/releases/<BUILD_ID>；不覆盖原运行包。
- 主平台导航/桥接改动优先留在apps/web/features/committee和scripts；不为了接入修改原workspace或原公网启动器。
- 真实账号、研究历史与PDF保存在本地绑定的原运行数据目录；不把数据库、.env、上传文件、保留题和凭据加入此目录或提交。
- 原LightGBM预测实验与新平台FinQA训练任务不同，保留误差和用途边界，不把原模型成绩冒称本轮成果。
- scripts中的三份原价格训练/冻结/验证脚本保留为方法源码，依赖原实验目录与锁定流程；不自动运行、不读取其引用的旧评测/保留集。新训练先按当前research协议建立独立清单。
