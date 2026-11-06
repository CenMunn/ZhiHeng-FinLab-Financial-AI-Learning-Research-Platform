import {useEffect,useState} from 'react';
import {Activity,BookOpenCheck,ChartNoAxesCombined,FileUp,FlaskConical,Landmark,Microscope,WalletCards,LayoutGrid} from 'lucide-react';
import {CommitteeWorkspace} from '../features/committee/CommitteeWorkspace';
import {committeeHash,type CommitteeSection} from '../features/committee/routes';
import {RiskModule} from '../features/risk/RiskModule';
import {LearningHome} from '../features/learning/LearningHome';
import {ModuleOverview} from '../features/learning/ModuleOverview';
import {platformRoute} from './platform-routes';
import '../styles/platform.css';
import '../styles/learning.css';
import '../styles/learning-refinement.css';

const sections=[{key:'research',label:'投研工作台',icon:Landmark},{key:'evidence',label:'财报核验与比较',icon:BookOpenCheck},
  {key:'filings',label:'财务原页',icon:FileUp},{key:'forecast',label:'价格预测实验',icon:ChartNoAxesCombined},
  {key:'scenarios',label:'回款压力推演',icon:Activity}] as const;
const modules=[{key:'home',label:'总览',href:'#/',icon:LayoutGrid},{key:'lab',label:'量化实验室',href:'#/lab',icon:ChartNoAxesCombined},
  {key:'committee',label:'智投委 AI',href:committeeHash('research'),icon:Landmark},{key:'cashflow',label:'现金流沙盘',href:'#/cashflow',icon:WalletCards},
  {key:'training',label:'训练评测',href:'#/training',icon:FlaskConical}] as const;

export default function App(){
  const [route,setRoute]=useState(()=>platformRoute(window.location.hash));
  const [section,setSection]=useState<CommitteeSection>(()=>route.module==='committee'?route.section:'research');
  const [committeeVisited,setCommitteeVisited]=useState(route.module==='committee');
  const [riskVisited,setRiskVisited]=useState(route.module==='committee'&&route.section==='scenarios');
  const [navigationKey,setNavigationKey]=useState(0);
  useEffect(()=>{
    function update(){const next=platformRoute(window.location.hash);setRoute(next);
      if(next.module==='committee'){setSection(next.section);setCommitteeVisited(true);if(next.section==='scenarios')setRiskVisited(true);}
      document.getElementById('platform-content')?.scrollTo({top:0});
      document.getElementById('platform-content')?.focus({preventScroll:true});
    }
    window.addEventListener('hashchange',update);return()=>window.removeEventListener('hashchange',update);
  },[]);
  const committeeActive=route.module==='committee';
  return <div className="platform-shell learning-shell">
    <a className="skip-link" href="#platform-content" onClick={event=>{event.preventDefault();document.getElementById('platform-content')?.focus();}}>跳到工作区</a>
    <header className="lab-header"><a className="lab-brand" href="#/" aria-label="知衡 FinLab 首页"><Microscope size={26}/><strong>知衡 FinLab</strong></a>
      <nav className="lab-navigation" aria-label="功能模块">{modules.map(({key,label,href,icon:Icon})=><a key={key} href={key==='committee'?committeeHash(section):href} aria-current={route.module===key?'page':undefined}><Icon size={16}/><span>{label}</span></a>)}</nav>
    </header>
    {committeeActive?<nav className="committee-navigation" aria-label="智投委功能">{sections.map(({key,label,icon:Icon})=><a key={key} href={committeeHash(key)} onClick={()=>{if(section===key&&key!=='scenarios')setNavigationKey(n=>n+1);}} aria-current={section===key?'page':undefined}><Icon size={17}/><span>{label}</span></a>)}</nav>:null}
    <main id="platform-content" tabIndex={-1}>
      {route.module==='home'?<LearningHome/>:null}
      {route.module==='lab'||route.module==='cashflow'||route.module==='training'?<ModuleOverview key={route.module} module={route.module}/>:null}
      {committeeVisited?<div className="committee-module-host" hidden={!committeeActive}><CommitteeWorkspace section={section} navigationKey={navigationKey}/></div>:null}
      {riskVisited?<div hidden={!committeeActive||section!=='scenarios'}><RiskModule/></div>:null}
    </main>
  </div>;
}
