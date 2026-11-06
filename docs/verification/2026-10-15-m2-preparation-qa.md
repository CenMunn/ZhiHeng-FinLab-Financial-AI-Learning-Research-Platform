# M2.1 验收记录

日期2026-10-15；范围仅离线研究准备，无产品前后端变更。

- `python -m unittest discover -s research/tests -v`：23项通过。原5项；准备6、标签8、环境4。
- 初始三组新功能测试分别6/5/4项因缺实现失败，随后通过。
- 独立审阅用夹具复现两项Important：来源身份不核对、同数量替换固定先导。修复前两条回归包含7个失败子案例；修复后通过。另验证原先导隔离不替补。
- `python -m research.training.prepare_finqa`：6250/883可用，1/0隔离，34/7超过5gold题保留。
- 真实prepare重跑：manifest对象相同，各产物SHA256一致。来源六资产均按白名单与原获取收据校验。
- `python -m research.training.review_labels queue`：原30训练题90任务；先导ID按原始来源、隔离前规则冻结。
- `python -m research.training.review_labels check`：90pending、0确认冲突、0缺任务；不产生可信负例成绩。
- `python -m research.training.probe_environment`：资源已记录；readiness=false。应用venv缺torch/transformers，空闲物理内存低于4GiB。
- 显式`--torch-smoke`：因缺torch跳过，未执行CUDA前后向。

独立审阅只读代码/文档/测试夹具，无Critical。两项Important已由主代理修复并用回归验证；未把测试通过表述为领域标签已核验或模型效果。当前仍有人工复核、依赖安装和实际模型训练工作。
