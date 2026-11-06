import {useEffect,useState} from 'react';
import {Unplug} from 'lucide-react';
import {TactileButton} from '../../shared/ui/TactileButton';
import {embeddedPath,isLocalOrigin,type CommitteeSection} from './routes';

interface Connection {available:boolean;state:string;origin:string;build_id:string;message:string}
export function CommitteeWorkspace({section,navigationKey}:{section:CommitteeSection;navigationKey:number}) {
  const [connection,setConnection]=useState<Connection|null>(null),[error,setError]=useState(''),[checking,setChecking]=useState(true);
  const [attempt,setAttempt]=useState(0),[frameOrigin,setFrameOrigin]=useState(''),[path,setPath]=useState('/'),[opening,setOpening]=useState(true);
  useEffect(()=>{
    const controller=new AbortController();let busy=false;
    async function check(){
      if(busy)return;busy=true;
      try{
        const response=await fetch('/api/v1/integrations/committee',{signal:controller.signal,cache:'no-store'});
        if(!response.ok)throw Error('平台连接检查失败，请确认后端服务已启动。');
        const value=await response.json() as Connection;
        if(!isLocalOrigin(value.origin))throw Error('智投委地址未通过本地服务校验。');
        if(!controller.signal.aborted){setConnection(value);setError('');if(value.available)setFrameOrigin(value.origin);}
      }catch(e){if(!controller.signal.aborted){setError(e instanceof Error?e.message:'连接检查失败。');setConnection(null);}}
      finally{busy=false;if(!controller.signal.aborted)setChecking(false);}
    }
    void check();const timer=window.setInterval(()=>void check(),10000);
    return()=>{controller.abort();window.clearInterval(timer);};
  },[attempt]);
  useEffect(()=>{const next=embeddedPath(section);if(next!==null&&next!==path){setOpening(true);setPath(next);}},[section,path]);
  const ready=!!connection?.available&&!error;
  function retry(){setChecking(true);setAttempt(n=>n+1);}
  return <section className="committee-workspace" aria-label="智投委工作区" hidden={section==='scenarios'}>
    {!ready&&<div className="committee-offline" role={checking?'status':'alert'}><Unplug size={30}/><h1>{checking?'正在打开工作区':'工作区暂时无法打开'}</h1><p>{checking?'请稍候。':error||'请稍后重新加载。'}</p><TactileButton className="primary" onClick={retry} disabled={checking}>重新加载</TactileButton></div>}
    {frameOrigin&&<div className="committee-frame-wrap" hidden={!ready}>{opening&&<div className="committee-opening" role="status">正在打开页面…</div>}
      <iframe key={navigationKey} title="智投委完整工作区" src={frameOrigin+path} onLoad={()=>setOpening(false)} sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-popups-to-escape-sandbox" allow="clipboard-write"/>
    </div>}
  </section>;
}
