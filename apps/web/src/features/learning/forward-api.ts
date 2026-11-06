export type ForwardState='waiting_signal'|'waiting_outcome'|'blocked'|'scored';
export interface ForwardPrediction {forecast_id:string;signal_session:string;created_at:string;decision_at:string;entry_at:string;exit_at:string;predictions:Record<string,{raw:number;calibrated:number}>;outcome:null|{realized_variance:number;log_return:number;scored_at:string;errors:Record<string,{raw_qlike:number;calibrated_qlike:number}>}}
export interface ForwardAsset {symbol:string;name:string;market:'ashare'|'crypto';state:ForwardState;reason:string;latest_session:string|null;source_retrieved_at:string|null;forecast_count:number;scored_count:number;predictions:ForwardPrediction[]}
export interface ForwardEnvelope {record:null|{schema:'forward-market-status-v1';updated_at:string;status:'waiting'|'active'|'blocked';items:ForwardAsset[];limitations:string[];artifacts:Record<string,string>};record_sha256:string|null;artifact_status:'verified'|'missing'|'empty';missing_artifacts:string[]}
export const forwardStateNames:Record<ForwardState,string>={waiting_signal:'等待合格信号',waiting_outcome:'等待区间到期',blocked:'数据待核验',scored:'已有到期验证'};
const time=(v:unknown):v is string=>typeof v==='string'&&/(Z|[+-]\d{2}:\d{2})$/.test(v)&&Number.isFinite(Date.parse(v));
const count=(n:unknown)=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=0;
const strings=(a:unknown):a is string[]=>Array.isArray(a)&&a.every(v=>typeof v==='string');
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const finite=(v:unknown)=>typeof v==='number'&&Number.isFinite(v);
const record=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function prediction(p:ForwardPrediction){return p&&typeof p.forecast_id==='string'&&typeof p.signal_session==='string'&&p.signal_session>='2026-11-06'&&[p.created_at,p.decision_at,p.entry_at,p.exit_at].every(time)&&Date.parse(p.decision_at)<=Date.parse(p.created_at)&&Date.parse(p.created_at)<Date.parse(p.entry_at)&&Date.parse(p.entry_at)<Date.parse(p.exit_at)&&record(p.predictions)&&Object.keys(p.predictions).length>0&&Object.values(p.predictions).every(v=>v&&finite(v.raw)&&v.raw>0&&finite(v.calibrated)&&v.calibrated>0)&&(p.outcome===null||(p.outcome&&time(p.outcome.scored_at)&&Date.parse(p.outcome.scored_at)>=Date.parse(p.exit_at)&&finite(p.outcome.realized_variance)&&p.outcome.realized_variance>=0&&finite(p.outcome.log_return)&&record(p.outcome.errors)&&Object.keys(p.outcome.errors).sort().join()===Object.keys(p.predictions).sort().join()&&Object.values(p.outcome.errors).every(v=>v&&finite(v.raw_qlike)&&finite(v.calibrated_qlike))));}
export function validateForward(body:ForwardEnvelope):ForwardEnvelope {
 if(!body||!['verified','missing','empty'].includes(body.artifact_status)||!strings(body.missing_artifacts))throw Error('前向观察响应格式不完整。');
 if(body.artifact_status==='empty'){if(body.record!==null||body.record_sha256!==null||body.missing_artifacts.length)throw Error('前向观察空状态不一致。');return body;}
 const r=body.record;
 if(!r||r.schema!=='forward-market-status-v1'||!time(r.updated_at)||!['waiting','active','blocked'].includes(r.status)||!hash(body.record_sha256)||!strings(r.limitations)||!record(r.artifacts)||!Object.keys(r.artifacts).length||!Object.values(r.artifacts).every(hash)||!Array.isArray(r.items)||new Set(r.items.map(a=>a.symbol)).size!==r.items.length||!r.items.every(a=>a&&['600519','600036','600585','BTCUSDT','ETHUSDT'].includes(a.symbol)&&typeof a.name==='string'&&a.market===(a.symbol.endsWith('USDT')?'crypto':'ashare')&&Object.hasOwn(forwardStateNames,a.state)&&typeof a.reason==='string'&&(a.latest_session===null||/^\d{4}-\d{2}-\d{2}$/.test(a.latest_session))&&(a.source_retrieved_at===null||time(a.source_retrieved_at))&&count(a.forecast_count)&&count(a.scored_count)&&Array.isArray(a.predictions)&&a.forecast_count===a.predictions.length&&a.scored_count===a.predictions.filter(p=>p.outcome!==null).length&&a.predictions.every(prediction)&&new Set(a.predictions.map(p=>p.forecast_id)).size===a.predictions.length))throw Error('前向观察记录格式或时间顺序不一致。');
 return body;
}
export async function readForward(signal?:AbortSignal):Promise<ForwardEnvelope>{
 let response:Response;
 try{response=await fetch('/api/v1/forward-market/status',{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('前向观察服务暂不可用，请重试。');}
 let body;try{body=await response.json();}catch{throw Error('前向观察响应无法读取。');}
 if(signal?.aborted)throw new DOMException('aborted','AbortError');
 if(!response.ok)throw Error(typeof body?.message==='string'?body.message:'前向观察读取失败，请重试。');
 return validateForward(body);
}
export function forwardTime(value:string|null){return value?new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value))+' 北京时间':'尚无接收记录';}
export function forwardAge(value:string|null,now=Date.now()){if(value===null)return '尚未接收';const minutes=Math.floor((now-Date.parse(value))/60000);return minutes<0?'接收时间待核对':minutes<60?`${minutes} 分钟前接收`:minutes<1440?`${Math.floor(minutes/60)} 小时前接收`:`${Math.floor(minutes/1440)} 天前接收`;}
export function forwardReport(body:ForwardEnvelope){const r=body.record;return ['# 前向观察记录',r?`状态更新时间：${forwardTime(r.updated_at)}`:'尚未发布前向观察记录。',`产物核验：${body.artifact_status}`,`记录摘要：${body.record_sha256||'无'}`,'按实际写入时间留下预测，持有区间到期后才补记结果。预测误差不等于交易收益。',...(r?.items.map(a=>`- ${a.name}（${a.symbol}）：${forwardStateNames[a.state]}；${a.forecast_count} 条预测，${a.scored_count} 条到期验证。${a.reason}`)||[]),...(r?.limitations||[]),'```json',JSON.stringify(body,null,2),'```'].join('\n\n');}
