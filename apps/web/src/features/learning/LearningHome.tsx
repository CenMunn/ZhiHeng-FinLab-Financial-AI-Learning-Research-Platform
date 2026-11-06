import {ArrowRight,ArrowUpRight,BookOpen,ChartNoAxesCombined,FlaskConical,Landmark,WalletCards} from 'lucide-react';
import {SignalLesson} from './SignalLesson';
export const ROADMAP=[
  {title:'共同实验底座',text:'固定数据快照、时间划分、交易规则和实验记录。'},
  {title:'双市场入门实验',text:'A 股趋势与买入持有；BTC 减半周期与趋势。'},
  {title:'真实模型训练',text:'简单基线、LightGBM、DLinear，再加入预训练模型。'},
  {title:'基本面与事件',text:'投资论点、估值敏感性，以及数据就绪后的 PEAD。'},
  {title:'更深入的研究',text:'横截面选股、更多模型与 Agent；高频另行评估。'},
];
export function LearningHome(){
  return <div className="learning-home">
    <section className="home-introduction"><div><h1>把投资想法，<br/>变成一次有依据的实验。</h1><p>从看懂一条信号开始，学习数据、策略与模型。<br className="desktop-break"/>A 股与比特币，两条研究路径，同样认真地验证。</p><a className="lab-button lab-primary" href="#/lab">探索量化实验室<ArrowRight size={17}/></a></div><div className="home-manifesto"><BookOpen size={20}/><p>先理解，<br/>再实验，<br/><strong>最后才是结论。</strong></p><span>为刚开始的你，也为想深入的你。</span></div></section>
    <section className="home-first-experiment" aria-label="入门交互与学习方法"><SignalLesson/><aside className="learning-method"><span className="method-index" aria-hidden="true">?</span><h2>一个好问题，<br/>是实验的起点。</h2><p>“价格高于均线，<br/>就值得买入吗？”</p><ol><li><b>提出假设</b><span>把直觉写成能验证的规则。</span></li><li><b>建立对照</b><span>和简单基线公平比较。</span></li><li><b>检查失败</b><span>看回撤、成本和失效区间。</span></li></ol><a className="text-action" href="#/lab">了解第一组实验<ArrowUpRight size={16}/></a></aside></section>
    <section className="home-modules" aria-labelledby="module-heading"><div className="home-section-heading"><h2 id="module-heading">从你想研究的方向进入</h2><span>各自独立，也能彼此连接。</span></div><div className="module-entries">
      <a className="module-entry committee-entry" href="#/committee/research"><div className="module-entry-top"><Landmark size={25}/><span>已有工作区</span><ArrowUpRight size={19}/></div><h3>智投委 AI</h3><p>从公司财报到投研结论。核验证据、比较公司、诊断组合，继续已有研究。</p><ul className="committee-capabilities"><li>财报与原页核验</li><li>多角色投研分析</li><li>组合诊断与研究报告</li></ul><span className="module-bottom">进入投研工作台<ArrowRight size={16}/></span></a>
      <a className="module-entry cashflow-entry" href="#/cashflow"><div className="module-entry-top"><WalletCards size={25}/><span>独立场景</span><ArrowUpRight size={19}/></div><h3>现金流沙盘</h3><p>理解收付款时间怎样影响现金余额，逐步推演企业资金安排。</p><span className="module-bottom">查看模块规划<ArrowRight size={16}/></span></a>
      <a className="module-entry training-entry" href="#/training"><div className="module-entry-top"><FlaskConical size={25}/><span>离线实验已有结果</span><ArrowUpRight size={19}/></div><h3>训练与评测</h3><p>理解模型如何学习，比较基线与微调，检查每一次提升的证据。</p><span className="module-bottom">查看训练进展<ArrowRight size={16}/></span></a></div></section>
    <section className="home-roadmap" aria-labelledby="roadmap-heading"><div className="home-section-heading"><h2 id="roadmap-heading">一步一步，把实验做扎实</h2><span>接下来的研发路线</span></div><ol>{ROADMAP.map((step,index)=><li key={step.title}><span>{index+1}</span><div><h3>{step.title}</h3><p>{step.text}</p></div></li>)}</ol></section>
    <footer className="learning-footer"><span><ChartNoAxesCombined size={16}/>金融实验室</span><p>提出假设，保留依据，接受不确定性。</p><a href="#/lab">开始了解<ArrowUpRight size={15}/></a></footer>
  </div>;
}
