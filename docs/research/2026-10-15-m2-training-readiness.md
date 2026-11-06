# M2.1 训练准备结果与运行说明

2026-10-15（Asia/Shanghai）。本轮执行用户批准的数据、标注和环境准备，尚未下载权重或训练神经网络。

## 数据准备

来源：FinQA固定commit `0f16e2867befa6840783e58be38c9efb9229d742`，只读取既有白名单train/dev与来源许可资产。6个资产逐项校验URL、大小与SHA256；来源和输出目录不得相互包含。

| 结果 | train | dev |
|---|---:|---:|
| 原始问题 | 6251 | 883 |
| 可用于标注集评分的问题 | 6250 | 883 |
| 隔离 | 1 | 0 |
| 超过5条gold，仍保留 | 34 | 7 |

唯一隔离题为`RE/2010/page_120.pdf-2`：`text_-1`不在源候选中。没有按Python负索引补证据，也没有修改源文件。其原始记录hash、缺失ID与理由单列在quarantine.jsonl。

推理输入白名单仅含问题、ID/分组、同源候选、序列化版本和BM25 top20；评分gold另存。所有正负候选共用表头感知序列化；无gold文本、答案、程序、上游model_input或retrieved文本注入。每个实际输出文件hash进入manifest；真实数据重跑得到完全相同manifest和产物hash。manifest另存按原规则在隔离前选定的先导ID，标注包要求来源身份和固定ID集合均一致；若原先导题被隔离则拒绝生成，不以其他题替补。

另外生成仅使用官方训练部分的公司隔离开发诊断：135个公司代理组按SHA顺序取27个验证公司，4896题拟合/1354题验证，问题和公司交集均为0。它是另外的开发协议，**不是官方dev，也不是新的盲测**。同公司不同报告版本、同名实体真实性未获认证。使用此协议时，负例挖掘和训练标签必须再按fit_ids过滤，不能把验证题的标注用于拟合。

可追溯收据：[数据manifest](2026-10-15-m2-preparation-receipt.json)。原始数据、大清单和工作包位于被git忽略的research/artifacts，不进入源码提交。

## 标注与算法资格

原固定先导的30个训练题生成90个候选任务。全是pending；确认负例0，B3增强资格尚未满足。构造工作包不会自动认证领域标签。规范、数学推导和给金融同学的问题见[标注规范](2026-10-15-labeling-protocol.md)。

验证器绑定task、问题、片段、上下文、序列化和来源版本；只有具有人类复核人、理由及合法冲突类型的completed confirmed_conflict才能导出。support/uncertain不作金融负例。填写身份仍需外部责任和二次复核，程序不能鉴定真人身份或裁决金融含义。

B0—B2不依赖B3已经获得可靠领域负例；B2若使用非gold候选，须明确是弱负例，抽查并报告假阴性。条件性B3后续再检查领域标签数量、类别和与普通负例的难度/长度匹配。

## 本机资源与独立训练环境方案

CPU：i9-14900HX，24核/32线程（CIM）；内存总量16890322944字节，约15.73GiB。GPU为RTX5060 Laptop，8151MiB显存、查询时7800MiB空闲，驱动582.05，compute capability实查12.0。D盘约122.88GiB可用。可用物理内存瞬时波动，检查时约0.23—1.17GiB，低于本项目小规模试跑采用的4GiB余量门槛。

标准资源检查[收据](2026-10-15-training-environment.json)显示当前Python3.14.4应用venv内未安装torch/transformers。显式请求--torch-smoke后因缺torch跳过；**CUDA前向和反向没有执行，环境不报告ready**。4GiB系统内存、4GiB空闲显存、10GiB磁盘均只是小规模试跑启发式门槛，不保证某个模型适配。

下一阶段使用research/.venv独立环境和单独锁文件；不向backend/.venv安装训练依赖。先核对选定版本的Windows/Python/CUDA wheel，安装验证成功再锁定版本，不提前生成声称可用的锁文件。小型cross-encoder是候选；暂定最大长度256、微批2、梯度累积8、num_workers=0作为探测起点，实际依据长度分布、截断gold比例、显存峰值和耗时调整。混合精度在实测后启用；序列截断策略必须一致，不能为了适配显存而静默截掉表头或gold。

先释放不必要应用占用，再重新检查；不由脚本终止用户进程。完成CUDA算子检查、模型前向反向和小批过拟合试验后，才扩大到完整训练。资源不足时先保留数据和CPU可跑的B0；收费云资源另行确认。

## 官方资料核对

- [PyTorch安装文档](https://pytorch.org/get-started/locally/)当前Windows说明支持Python3.10—3.14，因此不能仅凭3.14就断言不兼容；具体依赖仍以wheel解析和运行验证为准。
- [PyTorch发行兼容矩阵](https://github.com/pytorch/pytorch/blob/main/RELEASE.md)列出不同CUDA构建的架构支持，包括Blackwell12.0；不能把CUDA12.6等不同构建视为等效。main是可变开发文档，安装时还需固定发行版。
- [NVIDIA能力表](https://developer.nvidia.com/cuda/gpus)列出RTX5060为12.0，与本机查询一致。

查询日2026-10-15。安装页抽取的选择器与发行矩阵版本展示不同，因此本轮不依据单页选择器宣布最新稳定版本，也不更新驱动。

## 复现

在项目根运行，当前这些工具仅用标准库：

```powershell
& backend/.venv/Scripts/python.exe -m research.training.prepare_finqa
& backend/.venv/Scripts/python.exe -m research.training.review_labels queue
& backend/.venv/Scripts/python.exe -m research.training.review_labels check
& backend/.venv/Scripts/python.exe -m research.training.probe_environment
& backend/.venv/Scripts/python.exe -m unittest discover -s research/tests -v
```

queue重跑保留已经编辑的reviews.jsonl；源任务改变则要求新建版本目录，避免覆盖复核。准备清单重跑采用最后写manifest的发布方式；下游必须按manifest校验产物hash，拒绝中断后混合版本。

## 验证与下一步

23项研究工具测试通过（原5+本轮18）；本轮三组新功能测试均观察缺实现失败后通过。独立审阅发现来源身份与固定样本替换两项Important，均以回归先失败再通过修复；另补一项既有隔离不替补行为验证。真实准备、重跑一致性、90条待复核校验和环境检查已实际运行。未改产品前后端，不以旧浏览器测试当本轮训练验证。详见[验收记录](../verification/2026-10-15-m2-preparation-qa.md)。

M2.2先固定现成cross-encoder的模型版本和许可证，配置独立训练环境，验证CUDA和模型小批前后向；随后运行相同候选集合的B0/B1/B2，记录预测、分组指标、耗时、种子和错误。B3等可信领域标签，中文工作台默认模型等中文迁移诊断；本轮均未推进。
