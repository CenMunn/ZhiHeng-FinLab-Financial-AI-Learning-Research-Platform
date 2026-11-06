import { useState } from 'react';
import { ArrowUpRight, Clock3, Search, X } from 'lucide-react';
import type { SavedScenario } from './api';
import { ratioToPercent } from './risk-state';
import { money, savedTime } from './format';
import { ModalFrame } from '../../shared/ui/ModalFrame';
import { TactileButton } from '../../shared/ui/TactileButton';

export function HistoryDrawer({history,opening,onOpen,onClose,error}:{history:SavedScenario[];opening:string;onOpen:(id:string)=>void;onClose:()=>void;error:string}){
  const [query,setQuery]=useState('');
  const items=history.filter(item=>`${item.title} ${item.result.snapshot.company_name}`.toLowerCase().includes(query.trim().toLowerCase()));
  return <ModalFrame titleId="history-title" className="history-dialog" onClose={onClose}>
    <header className="dialog-header"><div><span className="dialog-icon"><Clock3 size={20}/></span><h2 id="history-title">历史情景 <small>{history.length}</small></h2></div><TactileButton className="icon-button compact" aria-label="关闭历史情景" onClick={onClose}><X size={20}/></TactileButton></header>
    <p className="dialog-subtitle">重新打开时保留原始参数、来源和计算版本。</p>
    <div className="history-search"><Search size={17}/><input autoFocus aria-label="搜索历史情景" placeholder="搜索情景名称或公司" value={query} onChange={e=>setQuery(e.target.value)}/></div>
    {error && <p className="error-text" role="alert">{error}</p>}
    <div className="history-list">{items.length?items.map(item=><button key={item.scenario_id} className="history-item" disabled={opening===item.scenario_id} onClick={()=>onOpen(item.scenario_id)}>
      <div className="history-item-top"><strong>{opening===item.scenario_id?'正在打开…':item.title}</strong><ArrowUpRight size={18}/></div>
      <p>{item.result.snapshot.company_name}<span/>赊销{ratioToPercent(item.result.assumptions.credit_share)}%<span/>延迟{item.result.assumptions.delay_days}天</p>
      <div className="history-item-bottom"><span>{savedTime(item.created_at)}</span><b>{money(item.result.occupancy_change)} <small>元</small></b></div>
    </button>):<div className="history-empty"><Clock3 size={30}/><h3>{history.length?'没有匹配的情景':'还没有保存的情景'}</h3><p>{history.length?'试试其他名称，或清空搜索。':'计算后保存一次假设，即可在这里重新打开。'}</p></div>}</div>
  </ModalFrame>;
}
