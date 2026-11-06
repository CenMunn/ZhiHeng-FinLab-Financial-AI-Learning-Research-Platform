import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronRight, Clock3 } from 'lucide-react';
import { api, type CaseSnapshot, type SavedScenario } from './api';
import { RiskWorkspace } from './RiskWorkspace';
import { HistoryDrawer } from './HistoryDrawer';
import { TactileButton } from '../../shared/ui/TactileButton';

export function RiskModule() {
  const [cases,setCases]=useState<CaseSnapshot[]>([]),[history,setHistory]=useState<SavedScenario[]>([]);
  const [error,setError]=useState(''),[loading,setLoading]=useState(true),[historyOpen,setHistoryOpen]=useState(false);
  const [openScenario,setOpenScenario]=useState<SavedScenario|null>(null),[opening,setOpening]=useState('');
  const historyRevision=useRef(0),openRevision=useRef(0);
  useEffect(()=>{
    const controller=new AbortController();
    Promise.all([api.cases(controller.signal),api.scenarios(controller.signal)]).then(([items,saved])=>{
      if(!controller.signal.aborted){setCases(items);setHistory(saved);if(!items.length && saved.length)setOpenScenario(saved[0]);setLoading(false);}
    }).catch(error=>{if(!controller.signal.aborted){setError(error.message);setLoading(false);}});
    return()=>controller.abort();
  },[]);
  const refreshHistory=useCallback(async()=>{const revision=++historyRevision.current;const items=await api.scenarios();if(revision===historyRevision.current)setHistory(items);},[]);
  const onOpened=useCallback(()=>setOpenScenario(null),[]);
  async function reopen(id:string){
    const revision=++openRevision.current;setOpening(id);setError('');
    try{const saved=await api.reopen(id);if(revision===openRevision.current){setOpenScenario(saved);setHistoryOpen(false);}}
    catch(error){if(revision===openRevision.current)setError((error as Error).message);}
    finally{if(revision===openRevision.current)setOpening('');}
  }
  const workspaceSnapshot=cases[0] ?? history[0]?.result.snapshot;
  return <div className="native-risk-module">
    <div className="risk-module-toolbar"><span>智投委 <ChevronRight size={13}/> 回款压力推演</span><TactileButton className="secondary compact" onClick={()=>{setError('');setHistoryOpen(true);}}><Clock3 size={16}/>历史情景 <b>{history.length}</b></TactileButton></div>
    <main className="main-content">
      {loading?<div className="app-loading" role="status">正在载入财报案例与已保存情景…</div>:!workspaceSnapshot?<div className="app-loading" role="alert"><h1>案例暂时无法载入</h1><p>{error || '没有可用案例，请检查来源配置。'}</p><TactileButton className="primary" onClick={()=>window.location.reload()}>重新载入</TactileButton></div>:<>
        {error && <div className="error-banner" role="alert">{error}</div>}{!cases.length && <div className="error-banner" role="status">当前来源无法载入。仍可查看已保存情景；恢复来源后才能重新计算。</div>}
        <RiskWorkspace snapshot={workspaceSnapshot} canCalculate={cases.length>0} history={history} refreshHistory={refreshHistory} openScenario={openScenario} onOpened={onOpened}/>
      </>}
    </main>
    {historyOpen && <HistoryDrawer history={history} opening={opening} onOpen={reopen} onClose={()=>setHistoryOpen(false)} error={error}/>}
  </div>;
}
