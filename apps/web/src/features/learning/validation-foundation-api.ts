export const validationSegments=['train','early_stopping','calibration','evaluation'] as const;
export type ValidationSegment=typeof validationSegments[number];
export const segmentNames:Record<ValidationSegment,string>={train:'训练',early_stopping:'早停',calibration:'独立校准',evaluation:'评估'};
export interface ValidationFold {fold:string;bounds:Record<ValidationSegment,[string,string]>;horizons:{horizon:1|5;counts:Record<ValidationSegment,number>;purged:Record<ValidationSegment,number>}[]}
export interface ValidationAsset {symbol:string;name:string;market:'ashare'|'crypto';role:string;status:'qualified'|'rejected';rows:number;issues:string[];warnings:string[];coverage:{expected:number;missing:number;extra:number};events:{dividends:number;splits:number};folds:ValidationFold[];source_receipts:Record<string,unknown>[]}
export interface ValidationFoundationEnvelope {record:{schema:'validation-foundation-v1';report_id:string;created_at:string;protocol:Record<string,unknown>;protocol_sha256:string;assets:ValidationAsset[];artifacts:Record<string,string>;limitations:string[]};record_sha256:string;artifact_status:'verified'|'missing';missing_artifacts:string[]}
const hash=(s:unknown)=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const texts=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(s=>typeof s==='string');
const count=(n:unknown)=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=0;
function validAsset(a:ValidationAsset){return a&&typeof a.symbol==='string'&&typeof a.name==='string'&&['ashare','crypto'].includes(a.market)&&['qualified','rejected'].includes(a.status)&&count(a.rows)&&texts(a.issues)&&texts(a.warnings)&&a.coverage&&['expected','missing','extra'].every(k=>count(a.coverage[k as keyof typeof a.coverage]))&&a.events&&count(a.events.dividends)&&count(a.events.splits)&&Array.isArray(a.source_receipts)&&a.source_receipts.every(r=>r&&typeof r==='object')&&Array.isArray(a.folds)&&a.folds.every(f=>typeof f.fold==='string'&&f.bounds&&validationSegments.every(s=>Array.isArray(f.bounds[s])&&f.bounds[s].length===2&&f.bounds[s].every(d=>typeof d==='string'))&&Array.isArray(f.horizons)&&f.horizons.length===2&&f.horizons.every(h=>[1,5].includes(h.horizon)&&h.counts&&h.purged&&validationSegments.every(s=>count(h.counts[s])&&count(h.purged[s]))));}
export async function readValidationFoundation(signal?:AbortSignal):Promise<ValidationFoundationEnvelope>{
 let response:Response;
 try{response=await fetch('/api/v1/validation-foundation/report',{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('数据资格报告服务暂不可用，请稍后重试。');}
 let body;try{body=await response.json();}catch{throw Error('数据资格报告响应无法读取，请重试。');}
 if(signal?.aborted)throw new DOMException('aborted','AbortError');
 if(response.status===404)throw Error('尚未发布数据资格与四段准备报告；当前没有可展示的准备结果。');
 if(!response.ok)throw Error(typeof body?.message==='string'?body.message:'数据资格报告读取失败，请重试。');
 const r=body?.record,expected=['600519','600036','600900','600585','600276','BTCUSDT','ETHUSDT'].sort();
 if(r?.schema!=='validation-foundation-v1'||!/^validation-[a-f0-9]{64}$/.test(r.report_id)||!hash(body.record_sha256)||!hash(r.protocol_sha256)||typeof r.created_at!=='string'||!r.protocol||typeof r.protocol!=='object'||!r.artifacts||typeof r.artifacts!=='object'||!texts(r.limitations)||!Array.isArray(r.assets)||r.assets.length!==7||!r.assets.every(validAsset)||r.assets.map((a:ValidationAsset)=>a.symbol).sort().join()!==expected.join()||!texts(body.missing_artifacts)||!['verified','missing'].includes(body.artifact_status))throw Error('数据资格报告格式不完整，请重试。');
 return body as ValidationFoundationEnvelope;
}
export function validationFoundationReport(body:ValidationFoundationEnvelope){const r=body.record;return ['# 多标的数据资格与四段准备',`报告身份：${r.report_id}`,`报告摘要：${body.record_sha256}`,`协议摘要：${r.protocol_sha256}`,'候选为人工选择的当前存续标的，存在幸存与选择偏差。资格仅表示公开历史重建条件下可准备研究数据，不等于 PIT 审计通过；本报告没有模型训练成绩。','前瞻信号起点：2026-11-06，等待真实观测；无前瞻成绩，不会自动采集或交易。','| 候选 | 数据资格 | 日线行数 | 缺日 |','| --- | --- | --- | --- |',...r.assets.map(a=>`| ${a.name} (${a.symbol}) | ${a.status==='qualified'?'可准备':'拒绝'} | ${a.rows} | ${a.coverage.missing} |`),'## 限制',...r.limitations.map(s=>`- ${s}`),`产物核验：${body.artifact_status}；缺失：${body.missing_artifacts.join('、')||'无'}`,'## 全部资产、四段计数、清除数、来源与冻结协议','```json',JSON.stringify(r,null,2),'```'].join('\n\n');}
