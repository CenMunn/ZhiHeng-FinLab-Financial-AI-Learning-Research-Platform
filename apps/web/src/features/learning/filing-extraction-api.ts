export type FilingSplit='development'|'evaluation';
export type FilingMethod='rule'|'model';
export interface FilingValue {metric?:string;value:string|null;unit:string|null;currency:string|null;period:string|null;scope:string|null;page:number|null;quote:string|null}
export interface FilingDocument {doc_id:string;symbol:string;name:string;title:string;period:string;split:FilingSplit;pdf_path:string;pdf_sha256:string;pdf_url:string;input_pages:number[];input_sha256:string;coverage:Record<string,unknown>}
export interface FilingRow {doc_id:string;split:FilingSplit;metric:string;label:string;method:FilingMethod;prediction:FilingValue|null;status:'ok'|'invalid_output'|'input_too_long'|'error';reference:{status:'verified'|'unavailable'|'ambiguous';variants:FilingValue[];input_context_complete:boolean;notes:unknown};checks:Record<string,boolean>;error_reasons:string[]}
export interface FilingMetric {split:FilingSplit;method:FilingMethod;total:number;answered:number;abstained:number;numeric_correct:number;unit_correct:number;currency_correct:number;period_correct:number;scope_correct:number;evidence_correct:number;complete_correct:number;correct_abstentions:number;reference_verified:number;context_complete:number}
export interface FilingRecord {schema:'filing-extraction-publication-v1';run_id:string;created_at:string;documents:FilingDocument[];methods:{id:FilingMethod;label:string;description:string;model_id?:string;revision?:string}[];metrics:FilingMetric[];rows:FilingRow[];artifacts:Record<string,string>;limitations:string[];reference_status:string;model_status:string;model_details:Record<string,unknown>;[key:string]:unknown}
export interface FilingEnvelope {record:FilingRecord|null;record_sha256:string|null;artifact_status:'empty'|'verified'|'missing';missing_artifacts:string[]}
const strings=(value:unknown):value is string[]=>Array.isArray(value)&&value.every(v=>typeof v==='string');
const hash=(value:unknown)=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const validValue=(v:FilingValue|null)=>v===null||(v&&typeof v==='object'&&(v.value===null||(typeof v.value==='string'&&/^-?\d+(\.\d+)?$/.test(v.value)&&Number.isFinite(Number(v.value))))&&(v.page===null||(Number.isInteger(v.page)&&v.page>0))&&(['unit','currency','period','scope','quote'] as const).every(key=>v[key]===null||typeof v[key]==='string'));
export function validateFilingExtraction(body:FilingEnvelope):FilingEnvelope {
 if(!body||!['empty','verified','missing'].includes(body.artifact_status)||!strings(body.missing_artifacts))throw Error('字段抽取响应不完整。');
 if(body.artifact_status==='empty'){if(body.record!==null||body.record_sha256!==null)throw Error('字段抽取空状态不一致。');return body;}
 const r=body.record;
 if(!r||r.schema!=='filing-extraction-publication-v1'||!hash(body.record_sha256)||!Array.isArray(r.documents)||!r.documents.length||new Set(r.documents.map(d=>d.doc_id)).size!==r.documents.length||!Array.isArray(r.methods)||!r.methods.length||!Array.isArray(r.metrics)||!Array.isArray(r.rows)||!strings(r.limitations))throw Error('字段抽取发布结构无效。');
 if(!r.documents.every(d=>d&&typeof d.doc_id==='string'&&typeof d.name==='string'&&typeof d.title==='string'&&['development','evaluation'].includes(d.split)&&Array.isArray(d.input_pages)&&d.input_pages.every(p=>Number.isInteger(p)&&p>0)))throw Error('文档身份或输入页不完整。');
 for(const s of r.metrics){const keys=['total','answered','abstained','numeric_correct','unit_correct','currency_correct','period_correct','scope_correct','evidence_correct','complete_correct','correct_abstentions','reference_verified','context_complete'] as const;if(!['development','evaluation'].includes(s.split)||!['rule','model'].includes(s.method)||!Number.isInteger(s.total)||s.total<1||!keys.every(key=>Number.isInteger(s[key])&&s[key]>=0&&s[key]<=s.total)||s.answered+s.abstained!==s.total)throw Error('字段抽取计数或分母无效。');}
 if(new Set(r.rows.map(row=>[row.doc_id,row.metric,row.method].join('/'))).size!==r.rows.length)throw Error('字段结果重复。');
 for(const row of r.rows){const doc=r.documents.find(d=>d.doc_id===row.doc_id);if(!doc||doc.split!==row.split||!['rule','model'].includes(row.method)||!['ok','invalid_output','input_too_long','error'].includes(row.status)||!validValue(row.prediction)||!row.reference||!['verified','unavailable','ambiguous'].includes(row.reference.status)||!Array.isArray(row.reference.variants)||!row.reference.variants.every(validValue)||typeof row.reference.input_context_complete!=='boolean'||!row.checks||!['numeric','unit','currency','period','scope','evidence','complete','answered','correct_abstention'].every(k=>typeof row.checks[k]==='boolean')||!strings(row.error_reasons))throw Error('字段结果与文档归属不一致。');}
 return body;
}
export async function readFilingExtraction(signal?:AbortSignal){let response;try{response=await fetch('/api/v1/filing-extraction',{signal,cache:'no-store'});}catch(e){if((e as Error).name==='AbortError')throw e;throw Error('字段抽取服务暂不可用，请重试。');}let body;try{body=await response.json();}catch{throw Error('字段抽取响应无法读取。');}if(signal?.aborted)throw new DOMException('aborted','AbortError');if(!response.ok)throw Error(body?.message||'字段抽取结果读取失败。');return validateFilingExtraction(body);}
export const filingSplitNames:Record<FilingSplit,string>={development:'2024 · 开发检查',evaluation:'2025 · 预定评估'};
export const filingCheckNames:Record<string,string>={numeric:'金额',unit:'单位',currency:'币种',period:'期间一致性',scope:'范围一致性',evidence:'证据定位',complete:'完整记录',answered:'已回答',correct_abstention:'正确拒答'};
export function filingDocumentUrl(doc:string,page?:number|null,absolute=false){return `${absolute?'http://127.0.0.1:8010':''}/api/v1/filing-extraction/document?doc_id=${encodeURIComponent(doc)}${page?`#page=${page}`:''}`;}
export function filingAmount(v:FilingValue|null){return v?.value!==null&&v?.value!==undefined?`${v.value} ${v.unit||'单位未明'}`:'未给出金额';}
export function filingRunIssue(status:FilingRow['status']) {
 const issues={
  invalid_output:{label:'输出格式无效',explanation:'输出未满足结构要求，无法逐项核验；不代表模型未识别出任何数字。'},
  input_too_long:{label:'输入超出固定预算',explanation:'输入超出本次固定预算，未形成可逐项核验的记录；不能据此判断数值识别能力。'},
  error:{label:'运行失败',explanation:'本次运行失败，未形成可逐项核验的记录；不能据此判断数值识别能力。'},
 };
 return status==='ok'?null:issues[status];
}
export function filingReport(body:FilingEnvelope,split:FilingSplit){
 const r=body.record;if(!r)return '# 跨公司财报字段核验\n\n尚未发布。';
 const cell=(v:unknown)=>String(v??'未给出').replaceAll('|','\\|').replace(/\r?\n/g,' ');
 const fieldReport=(row:FilingRow,d:FilingDocument)=>{
  const issue=filingRunIssue(row.status);
  return `**${row.label} · ${r.methods.find(m=>m.id===row.method)?.label||row.method}**\n\n预测：${issue?'未形成可核验记录':filingAmount(row.prediction)}；完整记录${issue?'未能核验':row.checks.complete?'正确':'未通过'}。\n\n${!issue&&row.prediction?.page?`[预测引用第${row.prediction.page}页](${filingDocumentUrl(d.doc_id,row.prediction.page,true)})`:'未给出有效引用页'}\n\n> ${String(!issue&&row.prediction?.quote||'无引用').replace(/\r?\n/g,'\n> ')}\n\n参考：${row.reference.variants.map(value=>filingAmount(value)+(value.page?` [参考第${value.page}页](${filingDocumentUrl(d.doc_id,value.page,true)})`:'')).join(' / ')||'尚无可核验参考'}。输入上下文${row.reference.input_context_complete?'完整支持':'支持不完整'}。\n\n核查：${issue?issue.label+'。'+issue.explanation:(row.error_reasons.join('；')||'按冻结规则逐项通过')+'。'}`;
 };
 return ['# 跨公司财报字段核验',filingSplitNames[split],'固定前六个物理页的文本抽取先导对照。同三家公司跨年度检查，不是公司外泛化验证。','参考为助手视觉核验，待人工审计；期间、范围为给定查询口径的一致性检查。','## 方法对照','| 方法 | 完整记录正确 | 数值正确 | 已回答 | 正确拒答 |\n|---|---:|---:|---:|---:|\n'+r.metrics.filter(m=>m.split===split).map(m=>`| ${cell(r.methods.find(v=>v.id===m.method)?.label||m.method)} | ${m.complete_correct}/${m.total} | ${m.numeric_correct}/${m.total} | ${m.answered}/${m.total} | ${m.correct_abstentions}/${m.total} |`).join('\n'),'拒答、格式失败和上下文覆盖缺口不从总分母中移除。','## 逐字段证据',...r.documents.filter(d=>d.split===split).flatMap(d=>[`### ${d.name} · ${d.period}`,`[公开报告的本地副本](${filingDocumentUrl(d.doc_id,undefined,true)})；PDF SHA256：${d.pdf_sha256}`,...r.rows.filter(row=>row.doc_id===d.doc_id).map(row=>fieldReport(row,d))]),'## 局限',...r.limitations.map(s=>'- '+s),'## 版本',`实验：${r.run_id}\n\n记录SHA256：${body.record_sha256}\n\n发布时间：${r.created_at}`,'完整原始预测、参考变体及来源清单见JSON导出。'].join('\n\n');
}
