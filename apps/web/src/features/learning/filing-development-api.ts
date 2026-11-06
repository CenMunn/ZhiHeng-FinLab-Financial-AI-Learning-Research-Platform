import {filingAmount,filingDocumentUrl,filingRunIssue,type FilingValue} from './filing-extraction-api';

export type DevelopmentMethod='baseline_rule'|'baseline_model'|'single_free'|'single_constrained';
export interface DevelopmentReferenceValue extends FilingValue {unit_evidence_pages:number[];scope_evidence_pages:number[]}
export interface DevelopmentDocument {doc_id:string;symbol:string;name:string;period:'2024Q1';split:'development';pdf_url:string;input_pages:number[]}
export interface DevelopmentRow {case_id:string;doc_id:string;metric:string;label:string;method:DevelopmentMethod;status:'ok'|'invalid_output'|'input_too_long'|'error';prediction:FilingValue|null;checks:Record<string,boolean>;error_reasons:string[];reference:{status:'verified'|'unavailable'|'ambiguous';variants:DevelopmentReferenceValue[];input_context_complete:boolean;notes:unknown};candidate_count:number|null;candidate_covered:boolean|null;input_tokens:number|null;output_tokens:number|null;latency_seconds:number|null;split?:'development'}
export interface DevelopmentMetric {method:DevelopmentMethod;total:number;format_valid:number;answered:number;numeric_correct:number;unit_correct:number;currency_correct:number;period_correct:number;scope_correct:number;evidence_correct:number;complete_correct:number;correct_abstentions:number;candidate_covered:number|null}
export interface DevelopmentRecord {schema:'filing-development-publication-v1';run_id:string;created_at:string;documents:DevelopmentDocument[];methods:{id:DevelopmentMethod;label:string;description:string}[];metrics:DevelopmentMetric[];rows:DevelopmentRow[];sources:Record<string,string>;artifacts:Record<string,string>;model_details:{model_id:string;revision:string;generation:Record<string,unknown>;runtime:Record<string,unknown>;verification:{receipt_path:string;verified_at:string;stage:'post_prediction_pre_scoring';current_assets_checked_on_request:false}};baseline:{record_sha256:string;run_id:string};new_evaluation:{manifest_path:string;status:'sealed'|'partial'|'blocked';content_accessed:false;documents:{symbol:string;name:string;period:string;status:'sealed'|'failed';[key:string]:unknown}[]};human_review:{manifest_path:string;checklist_path:string;guide_path:string;item_count:number;completed:number;status:'pending_human_review'};limitations:string[];[key:string]:unknown}
export interface DevelopmentEnvelope {record:DevelopmentRecord|null;record_sha256:string|null;artifact_status:'empty'|'verified'|'missing';missing_artifacts:string[]}
export const developmentMethods:DevelopmentMethod[]=['baseline_rule','baseline_model','single_free','single_constrained'];
export const developmentMetrics=['revenue','net_profit_parent','operating_cashflow'];
export const developmentReason=(reason:string)=>reason==='原始显示单位不一致'?'金额与原单位的配对未通过':reason;
const checkKeys=['numeric','unit','currency','period','scope','evidence','complete','answered','correct_abstention'];
const strings=(value:unknown):value is string[]=>Array.isArray(value)&&value.every(v=>typeof v==='string');
const hash=(value:unknown)=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value);
const count=(value:unknown):value is number=>typeof value==='number'&&Number.isInteger(value)&&value>=0;
const hashes=(value:unknown)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.values(value).every(hash);
const validFields=(value:FilingValue|null)=>value&&typeof value==='object'&&(value.value===null||(typeof value.value==='string'&&/^-?\d+(\.\d+)?$/.test(value.value)&&Number.isFinite(Number(value.value))))&&(value.page===null||(count(value.page)&&value.page>0))&&(['unit','currency','period','scope','quote'] as const).every(k=>value[k]===null||typeof value[k]==='string');
const validFact=(value:FilingValue|null,metric:string)=>validFields(value)&&value&&Object.keys(value).length===8&&value.metric===metric;
const validReference=(value:DevelopmentReferenceValue)=>validFields(value)&&Object.keys(value).length===9&&!('metric' in value)&&(['unit_evidence_pages','scope_evidence_pages'] as const).every(key=>Array.isArray(value[key])&&value[key].every(page=>count(page)&&page>0)&&new Set(value[key]).size===value[key].length);
function requireValue(value:unknown,message:string):asserts value {if(!value)throw Error(message);}

export function validateFilingDevelopment(body:DevelopmentEnvelope):DevelopmentEnvelope {
 requireValue(body&&['empty','verified','missing'].includes(body.artifact_status)&&strings(body.missing_artifacts),'开发验证响应不完整。');
 if(body.artifact_status==='empty'){requireValue(body.record===null&&body.record_sha256===null&&!body.missing_artifacts.length,'开发验证空状态不一致。');return body;}
 const r=body.record;
 requireValue(r&&r.schema==='filing-development-publication-v1'&&hash(body.record_sha256)&&typeof r.run_id==='string'&&r.run_id.startsWith('filingdev-')&&typeof r.created_at==='string'&&strings(r.limitations)&&hashes(r.sources)&&hashes(r.artifacts),'开发验证发布结构无效。');
 requireValue(Array.isArray(r.documents)&&r.documents.length===3&&new Set(r.documents.map(d=>d.symbol)).size===3,'开发文档数量或身份无效。');
 requireValue(r.documents.every(d=>['600519','600036','600585'].includes(d.symbol)&&d.doc_id===d.symbol+'-2024Q1'&&d.period==='2024Q1'&&d.split==='development'&&typeof d.name==='string'&&typeof d.pdf_url==='string'&&JSON.stringify(d.input_pages)==='[1,2,3,4,5,6]'),'仅允许固定三公司2024开发文档。');
 requireValue(Array.isArray(r.methods)&&r.methods.length===4&&new Set(r.methods.map(m=>m.id)).size===4&&r.methods.every(m=>developmentMethods.includes(m.id)&&typeof m.label==='string'&&typeof m.description==='string'),'开发方法身份不完整。');
 requireValue(Array.isArray(r.rows)&&r.rows.length===36&&new Set(r.rows.map(row=>[row.doc_id,row.metric,row.method].join('/'))).size===36,'开发字段结果重复或缺失。');
 for(const row of r.rows){
  requireValue(r.documents.some(d=>d.doc_id===row.doc_id)&&developmentMethods.includes(row.method)&&developmentMetrics.includes(row.metric)&&row.case_id===row.doc_id+'/'+row.metric&&(row.split===undefined||row.split==='development')&&typeof row.label==='string'&&['ok','invalid_output','input_too_long','error'].includes(row.status),'开发字段与文档归属不一致。');
  requireValue(row.checks&&Object.keys(row.checks).length===9&&checkKeys.every(k=>typeof row.checks[k]==='boolean')&&row.checks.complete===checkKeys.slice(0,6).every(k=>row.checks[k]),'开发字段核查状态矛盾。');
  requireValue((row.prediction===null||validFact(row.prediction,row.metric))&&(row.status!=='ok'||row.prediction!==null)&&row.checks.answered===(row.status==='ok'&&row.prediction!==null&&row.prediction.value!==null)&&(row.status==='ok'||(row.prediction===null&&!Object.values(row.checks).some(Boolean))),'格式失败不能展示为已核验回答。');
  requireValue(row.reference&&['verified','unavailable','ambiguous'].includes(row.reference.status)&&typeof row.reference.input_context_complete==='boolean'&&Array.isArray(row.reference.variants)&&row.reference.variants.every(validReference)&&strings(row.error_reasons),'开发参考或错误说明不完整。');
  requireValue((row.candidate_count===null||count(row.candidate_count))&&(row.candidate_covered===null||typeof row.candidate_covered==='boolean')&&((row.candidate_count===null)===(row.candidate_covered===null))&&(!row.method.startsWith('baseline_')||(row.candidate_count===null&&row.candidate_covered===null)),'候选覆盖状态无效。');
  requireValue([row.input_tokens,row.output_tokens].every(v=>v===null||count(v))&&(row.latency_seconds===null||(Number.isFinite(row.latency_seconds)&&row.latency_seconds>=0)),'开发运行计数无效。');
 }
 requireValue(Array.isArray(r.metrics)&&r.metrics.length===4&&new Set(r.metrics.map(m=>m.method)).size===4,'开发指标分组缺失。');
 for(const m of r.metrics){
  requireValue(developmentMethods.includes(m.method)&&m.total===9,'开发指标必须保留9字段分母。');
  const rows=r.rows.filter(row=>row.method===m.method),values:Record<string,number>={format_valid:rows.filter(row=>row.status==='ok').length,answered:rows.filter(row=>row.checks.answered).length,correct_abstentions:rows.filter(row=>row.checks.correct_abstention).length};
  for(const key of checkKeys.slice(0,7))values[key+'_correct']=rows.filter(row=>row.checks[key]).length;
  requireValue(Object.entries(values).every(([key,value])=>m[key as keyof DevelopmentMetric]===value),'开发指标与逐项核查不一致。');
  requireValue(m.candidate_covered===(rows.every(row=>row.candidate_covered===null)?null:rows.filter(row=>row.candidate_covered===true).length),'开发候选覆盖计数不一致。');
 }
 const sealed=r.new_evaluation,human=r.human_review;
 requireValue(sealed&&['sealed','partial','blocked'].includes(sealed.status)&&sealed.content_accessed===false&&Array.isArray(sealed.documents)&&sealed.documents.length===3&&new Set(sealed.documents.map(d=>d.symbol)).size===3&&sealed.documents.every(d=>['000333','601318','600887'].includes(d.symbol)&&d.period==='2025Q1'&&['sealed','failed'].includes(d.status)&&typeof d.name==='string'),'新评估仅允许封存元数据。');
 requireValue(human&&human.item_count===18&&human.completed===0&&human.status==='pending_human_review','人工核验尚未完成，状态不一致。');
 requireValue(r.baseline&&hash(r.baseline.record_sha256)&&typeof r.baseline.run_id==='string'&&r.model_details&&typeof r.model_details.model_id==='string'&&typeof r.model_details.revision==='string','开发来源身份不完整。');
 const verification=r.model_details.verification;requireValue(verification&&typeof verification.receipt_path==='string'&&typeof verification.verified_at==='string'&&Number.isFinite(Date.parse(verification.verified_at))&&verification.stage==='post_prediction_pre_scoring'&&verification.current_assets_checked_on_request===false,'模型仅有评分前离线核验，不能声称逐请求检查了当前权重。');
 return body;
}

export async function readFilingDevelopment(signal?:AbortSignal){
 let response;try{response=await fetch('/api/v1/filing-development',{signal,cache:'no-store'});}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('开发验证服务暂不可用，请重试。');}
 let body;try{body=await response.json();}catch{throw Error('开发验证响应无法读取。');}
 if(signal?.aborted)throw new DOMException('aborted','AbortError');
 if(!response.ok)throw Error(body?.message||'开发验证读取失败。');
 return validateFilingDevelopment(body);
}
export const reviewDownloadUrl=(file:'checklist'|'guide')=>'/api/v1/filing-development/review?file='+file;
export async function readFilingReview(file:'checklist'|'guide',signal?:AbortSignal){
 let response;try{response=await fetch(reviewDownloadUrl(file),{signal,cache:'no-store'});}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('人工核验包暂时无法下载，请重试。');}
 if(!response.ok){const body=await response.json().catch(()=>null);throw Error(body?.message||'人工核验包下载失败，请重试。');}
 const blob=await response.blob();if(signal?.aborted)throw new DOMException('aborted','AbortError');return blob;
}
export function developmentReport(body:DevelopmentEnvelope){
 const r=body.artifact_status==='verified'?body.record:null;if(!r)return '# 财报结构化抽取开发验证\n\n来源尚未验证，不展示成绩。';
 const cell=(value:unknown)=>String(value??'未给出').replaceAll('|','\\|').replace(/\r?\n/g,' ');
 const field=(row:DevelopmentRow)=>{const issue=filingRunIssue(row.status),pred=row.prediction;return [`### ${r.documents.find(d=>d.doc_id===row.doc_id)?.name} · ${row.label} · ${r.methods.find(m=>m.id===row.method)?.label}`,`预测：${issue?'未形成可核验记录':filingAmount(pred)}。完整记录：${issue?'未能核验':row.checks.complete?'通过':'未通过'}。`,issue?issue.explanation:`期间：${pred?.period??'未给出'}；范围：${pred?.scope??'未给出'}；币种：${pred?.currency??'未给出'}。`,!issue&&pred?.page?`[预测引用第${pred.page}页](${filingDocumentUrl(row.doc_id,pred.page,true)})\n\n> ${String(pred.quote||'无引用').replace(/\r?\n/g,'\n> ')}`:'未给出可核验引用。',`参考（助手核验，待人工审计）：${row.reference.variants.map(v=>filingAmount(v)+(v.page?` [原文第${v.page}页](${filingDocumentUrl(row.doc_id,v.page,true)})`:'')).join(' / ')||'暂不可用'}。`,`核查说明：${issue?issue.label:(row.error_reasons.map(developmentReason).join('；')||'按冻结规则逐项通过')}。`].join('\n\n');};
 return ['# 财报结构化抽取开发验证','2024开发验证，共9字段；不是新评估','只比较原三公司2024Q1。2025旧样本不重评，新公司仅封存，当前没有新评估成绩。','自由JSON与有限候选约束使用相同证据块；相较D29整篇输入还改变了证据定位，不能把全部变化归因于约束解码。','约束输出格式由算法保证，候选选择仍可能错误；期间与范围是查询给定条件；单位项按金额/原单位配对核验。格式失败不代表模型的语义能力为零。','## 四方法对照','| 方法 | 格式有效 | 金额正确 | 金额/原单位配对 | 引用正确 | 完整记录正确 | 候选覆盖 |\n|---|---:|---:|---:|---:|---:|---:|\n'+r.metrics.map(m=>`| ${cell(r.methods.find(v=>v.id===m.method)?.label||m.method)} | ${m.format_valid}/9 | ${m.numeric_correct}/9 | ${m.unit_correct}/9 | ${m.evidence_correct}/9 | ${m.complete_correct}/9 | ${m.candidate_covered===null?'不适用':m.candidate_covered+'/9'} |`).join('\n'),'格式失败、拒答、运行失败与覆盖缺口均保留在9字段分母中。','权重在评分前离线核验；页面请求核验归档证据，不重新检查当前权重。','## 逐字段记录',...r.rows.map(field),'## 新评估准备',...r.new_evaluation.documents.map(d=>`${d.name}（${d.symbol}）· ${d.period} · ${d.status==='sealed'?'PDF已封存':'来源准备失败'}。`),'内容未打开；尚未标注、预测或评分。','## 人工核验','待人工核验：0/18。空白清单尚未填写，不能视为参考已获专家审计。','## 局限',...r.limitations.map(v=>'- '+v),'## 冻结身份',`实验：${r.run_id}\n\n记录SHA256：${body.record_sha256}\n\n发布时间：${r.created_at}\n\nD29基线：${r.baseline.run_id}\n\nD29记录SHA256：${r.baseline.record_sha256}`,`模型：${r.model_details.model_id}\n\n修订：${r.model_details.revision}`].join('\n\n');
}
