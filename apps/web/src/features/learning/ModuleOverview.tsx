import {ArrowLeft,ArrowUpRight,Check,FlaskConical,WalletCards} from 'lucide-react';
import {ROADMAP} from './LearningHome';
import {SignalLesson} from './SignalLesson';
import {FoundationPanel} from './FoundationPanel';
import {PublicBacktestPanel} from './PublicBacktestPanel';
import {ForecastPanel} from './ForecastPanel';
import {RollingPanel} from './RollingPanel';
import {VolatilityPanel} from './VolatilityPanel';
import {RiskBudgetPanel} from './RiskBudgetPanel';
import {ForwardPanel} from './ForwardPanel';
import {EventStudyPanel} from './EventStudyPanel';
import {FilingExtractionPanel} from './FilingExtractionPanel';
import {FilingDevelopmentPanel} from './FilingDevelopmentPanel';
import {FilingSemanticsV2Panel} from './FilingSemanticsV2Panel';
import {FilingSemanticsPanel} from './FilingSemanticsPanel';
import {FiveAssetPanel} from './FiveAssetPanel';
import {ValidationFoundationPanel} from './ValidationFoundationPanel';
export function ModuleOverview({module}:{module:'lab'|'cashflow'|'training'}){
  return <div className="module-overview"><a className="module-back" href="#/"><ArrowLeft size={16}/>回到总览</a>
    {module==='lab'?<><div className="module-page-heading"><h1>量化学习实验室</h1><p>从一个信号，到一份可复核的实验。A 股和 BTC 同等推进。</p></div>
      <EventStudyPanel/><PublicBacktestPanel/><section className="forecast-lab-link"><h2>简单规则之后，看看模型能学到什么。</h2><p>A 股与 BTC 的简单预测基线、LightGBM 和 DLinear 已完成首轮离线训练。预测误差与仓位账户分别评价，保留 GPU 更新、验证早停和真实失败结果。</p><a className="lab-button lab-secondary" href="#/training">查看两市场预测模型实验<ArrowUpRight size={16}/></a></section>
      <FoundationPanel/>
      <SignalLesson/><section className="module-next-steps"><h2>从规则对照走向模型实验</h2><p>公开日线回测与合成管线检查分别保存。下一步在固定数据和时间划分下比较简单基线、LightGBM、DLinear，再评估一个预训练模型。</p><ol>{ROADMAP.map(step=><li key={step.title}><b>{step.title}</b><span>{step.text}</span></li>)}</ol></section></>:null}
    {module==='cashflow'?<><div className="module-page-heading"><WalletCards size={30}/><h1>现金流沙盘</h1><p>收入不等于到账。先看懂时间，再讨论资金安排。</p></div><section className="module-status-panel"><h2>独立模块，逐步建设</h2><p>计划从公开或合成的应收、应付和付款事件出发，建立逐期现金平衡，查看延迟回款、提前付款与资金安排的影响。</p><div className="cashflow-flow"><span>期初现金</span><b>＋</b><span>实际收款</span><b>－</b><span>实际付款</span><b>＝</b><span>期末现金</span></div><p>当前逐期沙盘尚未实现。已有的年度回款敏感性案例保留在智投委，用于估算稳态应收占款变化。</p><a className="lab-button lab-secondary" href="#/committee/scenarios">打开已有回款案例<ArrowUpRight size={16}/></a></section></>:null}
    {module==='training'?<><div className="module-page-heading"><FlaskConical size={30}/><h1>训练与评测</h1><p>不只问模型有没有变好，也问怎样比较才可信。</p></div><FilingSemanticsV2Panel/><FilingSemanticsPanel/><FilingDevelopmentPanel/><FilingExtractionPanel/><ForwardPanel/><RiskBudgetPanel/><ValidationFoundationPanel/><FiveAssetPanel/><VolatilityPanel/><RollingPanel/><ForecastPanel/><section className="module-status-panel"><h2>第一组金融证据排序实验已完成</h2><p>以下是 2026-10-30 保存的离线结果摘要，任务为 FinQA 给定页内证据排序，指标为官方开发集 Coverage@5。</p><table className="training-results"><caption>FinQA 证据排序，883 题；非股票预测成绩</caption><thead><tr><th scope="col">方法</th><th scope="col">Coverage@5</th></tr></thead><tbody><tr><th scope="row">BM25 词法基线</th><td>72.03%</td></tr><tr><th scope="row">预训练模型</th><td>74.86%</td></tr><tr><th scope="row">金融微调，三种子均值</th><td>80.52%</td></tr></tbody></table><p className="result-boundary">微调种子标准差 0.11 个百分点。尚未完成公司外诊断与中文迁移验证，不替换线上中文排序。</p><div className="training-receipt"><Check size={17}/><span>NVIDIA GPU 前后向与参数更新已经实测</span></div></section><section className="module-next-steps"><h2>量化模型与金融证据排序分别记录</h2><p>上方已接入两市场一步收益预测的真实离线结果。滚动验证、特征诊断与冻结预训练编码器对照现已接入上方独立记录；波动预测与市况稳定性现提供独立只读记录；基座微调仍待验证。网页展示离线训练记录，并可重放风险目标与费用参数；不会直接启动模型训练。</p></section></>:null}
  </div>;
}

