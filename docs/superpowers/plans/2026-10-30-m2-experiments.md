# M2.2 独立环境与三方法对照实施记录

用户2026-10-30明确授权执行。基于已有M2.1清单与研究路线，任务限FinQA英文给定页证据排序，不替换中文线上模型，不访问最终测试或旧保留集。

1. 独立Python3.12环境research/.venv；选择官方Windows CUDA12.8 PyTorch2.10.0与Transformers4.57.1；实际安装与CUDA算子/模型小批前后向通过后记录完整锁定依赖。
2. 固定cross-encoder/ms-marco-MiniLM-L6-v2模型commit 233902d25c440f23af6f7d6e94d2946bac0bee0a（Apache2.0，原MS MARCO排序训练，22.7M参数），仅下载显式白名单的safetensors/tokenizer/config/model card，无远程代码。检查实际文件hash、许可证及长度/截断比例。
3. 实现可测试的来源清单校验、推理/评分隔离、训练弱负例构造、排序指标及公司分组配对bootstrap。数据仍6250train/883dev，1隔离/超过5gold的问题处理不变。独立公司诊断划分保留，不混称官方dev。
4. 同一底座做小批BCEWithLogitsLoss前向/反向、非零有限梯度与参数更新、固定小批过拟合。模型smoke结束重新加载原始权重，不能污染B1或B2初始化。
5. 在评分前冻结配置：页内BM25 top20；同序列化/token上限256，保留问题、截断证据尾部；B1原模型；B2全部合格训练题的全部gold正例+每正例最多3条BM25未标注弱负例，不能称人工确认负例。B2三个固定种子42/43/44、各1epoch、AdamW lr2e-5/wd.01、微批2/累积8、梯度裁剪1、10%线性warmup及线性衰减。先以实测小批资源与耗时决定是否可完整运行；失败和范围调整必须保留。
6. 预测脚本只读推理白名单；训练过程不读dev gold，不按dev选checkpoint，单epoch最终权重固定。评分进程再单独加载dev labels，Coverage@5为主，CandidateCoverage@20/Recall/Hit/nDCG/条件覆盖与延迟为辅；按公司代理组配对bootstrap，种子波动另列。只作开发对照，不宣布假设已通过，不承诺微调优于预训练。
7. 实际运行工具测试、模型smoke及完整可执行实验，更新状态和证据，做一次独立整体验证审阅。环境/权重/预测/检查点均git忽略，源码/锁文件/小型收据保留。

本机初查：RTX5060 Laptop空闲显存8151MiB，系统可用内存约2GiB，D盘32GiB。旧4GiB RAM为通用启发式，并非模型实算结论；只在受控小模型试验中观察实际可用内存/峰值和失败，不结束用户进程。若无法安全实算则记录阻塞，先完成BM25和可执行代码。不得通过收费云或伪造结果填补。

## 执行日志

- 基线：原23项标准库工具测试通过；独立Python3.12已建立；模型7个文件完成固定revision下载，全部核对上游Git blob/LFS SHA。Transformers4.57.1等已安装且pip check通过；CUDA wheel尚在下载时不称训练环境ready。
- 数据/评分实现：新增推理白名单、训练fit过滤、弱负例、完整gold指标、公司配对bootstrap及候选顺序回归。JSON按key排序会改变BM25同分顺序，已恢复text/table数字原文顺序，全部883题复算top20与准备版完全一致。
- B0：883题Coverage@5=0.7202718007，CandidateCoverage@20=0.9558323896；gold>5的7题仍在分母。CPU页内BM25重算均值0.2504ms/题，不能与只计重排阶段的模型耗时直接当同端到端速度对照。
- 数据规模：6250训练题、10689正例、31660弱负例，42349配对，微批2/累积8时每种子2647更新。Token审计：训练60配对超过256（含9正例），dev候选5配对超过256、已召回正例0条超过256；最长问题85 token可完整保留。完整长度只作审计，不作为排序特征。
- 单次独立整体验证：0Critical、2Important。Final: fixed 训练数据来源未绑定 — valid_new_preparation_cannot_relabel_an_old_training_checkpoint RED→GREEN。Final: fixed checkpoint config.json未绑定 — model_config_tampering_is_rejected_even_with_identical_weights RED→GREEN。训练起止冻结准备manifest、train输入/标签和原模型acquisition；预测核验并透传训练收据，config.json与safetensors均核验。现有系统Python3.14+torch2.12CPU实际运行35/35通过；目标Python3.12环境尚无torch时33通过/2跳过，不能冒称CUDA通过。
- Final: minor (deferred): token长度审计的独立收据尚未绑定全部配置/数据/tokenizer hash；当前与主实验同目录保留并按明确运行记录解释，不作为独立可认证产物。
- Final: minor (deferred): 部分窗口梯度单测覆盖真实损失函数与等效批数学，没有直接驱动完整训练循环；实际训练smoke/日志另行验证。
- Final: minor (deferred): B0检索与B1/B2重排耗时不是同端到端口径；原始分阶段耗时保留，不能据此宣布整体加速倍数。
- 环境任务完成：官方CUDA wheel全文件SHA通过后安装，独立Python3.12.10/torch2.10.0+cu128锁定全部25个实际包；pip check通过。目标环境35/35通过，无跳过。通用4GiB RAM门槛保留false/skipped，受控22.7M模型实测另记。
- 模型验证完成：RTX5060原生sm_120、FP32和BF16有限前后向、非零梯度/真实参数更新、小批25更新loss下降通过；峰值已分配约590.5MiB，smoke权重未保存/复用。
- 完整对照完成：B0/B1/三个B2种子预测各883题；3×2647更新、各42349配对、最后窗口13配对、全部loss/grad范数有限。训练合计1268.04秒，代码/数据身份一致、权重hash互异。Coverage@5为72.0272%/74.8584%/80.5210%均值，种子SD0.1133个百分点。
- 最终验证：检查点config+weights、数据与原模型身份再次核验；全部预测hash与评分一致，0缺失预测；目标环境重新运行35/35与pip check通过。结果、收据、模型身份、小型CSV/图表已保存；导出PNG实际查看，无轴截断/图例遮挡。公司区间、退步题数、96重叠公司代理及3项Minor均在报告保留。未进行收费训练、应用数据库写入、中文模型替换或外部发布。
- 交付前保护：发现重复运行完整入口可能先覆盖完成状态/B1预测再由训练目录拒绝；用无Python/无wheel的独立PowerShell夹具先复现状态被覆盖，再把已有种子目录检查前置。回归先失败后通过，未触碰真实已完成实验；目标环境最终36/36、0跳过，pip check通过。真实pipeline-state继续保持completed。
