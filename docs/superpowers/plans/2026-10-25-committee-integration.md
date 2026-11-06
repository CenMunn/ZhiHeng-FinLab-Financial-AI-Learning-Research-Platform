# 智投委完整接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** 完整保留成型智投委，统一平台入口与重复功能归属，沿用数据。
**Architecture:** 原生M1 + 隔离Next子应用 + 版本/运行清单 + 本地启动与健康探测。
**Tech Stack:** 既有React18/Vite、Next16/React19、Python/FastAPI、Node标准库。
**Spec:** ../specs/2026-10-25-committee-integration-design.md

## Global Constraints

- 旧源码/配置/数据不修改；敏感配置只由运行进程消费，不复制到新仓库。
- 不读取任何保留集、不发起新模型训练或收费请求、不启用公网。
- 新导航使用Interactive-front-end；子应用保留原设计、账号和权限边界。
- 基线c8c0d1f，clean，继续当前独立项目feature分支。

## Review Focus

运行包错版/缺文件；源目录敏感文件混入；非回环URL和错误服务被误判online；模块切换销毁草稿；来源不可用使整个首页失败。

### Task 1: 快照和启动

Files: scripts/import_committee.py、scripts/start_committee.mjs、scripts/start_platform.ps1、integrations/committee-manifest.json、apps/committee、tests/test_committee_import.py。

- [x] 先写导入白名单、敏感路径、hash/重复执行测试，观察失败。
- [x] 实现固定发布版导入；实际执行并生成源与运行包hash。
- [x] 启动器验证运行包、回环端口、数据路径，避免输出敏感配置和覆盖旧进程。提供整平台启动。

### Task 2: 集成健康契约

Files: backend/src/platform_app/integrations/committee.py、api/app.py、backend/tests/test_committee.py。

- [x] 测试离线、错误服务、固定origin和就绪响应，观察失败。
- [x] 实现轻量GET健康契约；不读账号/历史内容。

### Task 3: 平台导航和归并

Files: apps/web/src/app/App.tsx、features/committee/*、features/risk/RiskModule.tsx、styles/*。

- [x] 路由归属/旧路径归并/未知路径单测先失败后通过。
- [x] 默认智投委、四个原应用页面导航、原生回款推演/历史归入智投委。
- [x] 异步状态、离线重试、模块保留和移动布局；构建与相关测试。

### Task 4: 运行验收与记录

- [x] 本地服务启动；实际浏览器走通页面与原生推演、模块往返及离线恢复。
- [x] 独立整分支审阅，修复重要问题；更新状态、功能矩阵、使用说明与验证记录。
- [x] 提交本地分支；清单记录未实测的原功能，不能把接入当作新一轮模型效果验证。

## Ledger

2026-10-25：已读关联聊天与源码；实际发布版比workspace多11源文件，选择发布版为完整能力来源。用户已确认沿用数据。依赖1→2：本地配置port/runtimeDir；2→3：健康契约origin/available；原M1 API数据路径不变。

完成记录：32后端/12前端/6导入/3Node与生产构建通过；浏览器四页、原生推演、状态保留和断线重试通过；原库计数不变，PDF/六股票推理通过。3项独立审阅Important已修复。运行包默认完整hash校验可能较慢，整平台启动等待上限180轮。真进程回收额外实测被自动审批拦截，不计通过；该项仅身份单测和控制流检查。具体证据见docs/verification/2026-10-25-committee-integration.md。
