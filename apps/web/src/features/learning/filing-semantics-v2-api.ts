import {filingAmount,type FilingValue} from './filing-extraction-api';
export type SemanticsMethod='structure_rule'|'structure_model';
export interface SemanticsCandidate {candidate_id:number;field:FilingValue;block_id:string;original_token:string;position:unknown;semantic:{financial_type:string;period_role:string;adjustment_role:string;scope_role:string};eligible:boolean;reasons:string[];header_evidence:{page:number;quote:string;bbox:unknown}[];unit_evidence:string;bbox:unknown}
export interface SemanticsCase {case_id:string;doc_id:string;metric:string;query:unknown;blocks:unknown[];candidates:SemanticsCandidate[];eligible_ids:number[];rule_field:FilingValue;rule_reasons:string[]}
export interface SemanticsRow {case_id:string;doc_id:string;metric:string;label:string;method:SemanticsMethod;status:string;prediction:FilingValue|null;checks:Record<string,boolean>;reference:{status:string;variants:{value:string|null;unit:string|null;currency:string|null;period:string|null;scope:string|null;page:number|null;quote:string|null;unit_evidence_pages:number[];scope_evidence_pages:number[]}[];input_context_complete:boolean};error_reasons:string[];selected_candidate_ids:number[];candidate_covered:boolean;input_tokens:number|null;output_tokens:number|null;latency_seconds:number|null}
export interface SemanticsMetric {method:SemanticsMethod;total:number;format_valid:number;answered:number;abstained:number;numeric_correct:number;unit_correct:number;currency_correct:number;period_correct:number;scope_correct:number;evidence_correct:number;column_correct:number;complete_correct:number;candidate_covered:number}
export interface SemanticsStudy {run_id:string;split:'development'|'evaluation';created_at:string;documents:{doc_id:string;symbol:string;name:string;title:string;period:string;split:string;pdf_sha256:string;source_url:string;page_count:number;identity:{qualified:boolean;checks:unknown;basis:unknown}}[];cases:SemanticsCase[];rows:SemanticsRow[];metrics:SemanticsMetric[];methods:{id:SemanticsMethod;label:string;description:string}[];model_details:{model_id:string;revision:string;generation:unknown;runtime:unknown;verification:unknown};method_freeze_sha256:string|null;sources:Record<string,string>;artifacts:Record<string,string>;prediction_sha256:Record<SemanticsMethod,string>;input_sha256:string;reference_sha256:string;limitations:string[]}
export interface SemanticsEnvelope {artifact_status:'verified'|'empty'|'missing';record:null|{schema:'filing-semantics-publication-v1';created_at:string;studies:SemanticsStudy[];limitations:string[]};sha256:string|null;missing_artifacts:string[];verified_artifacts:number}
export const semanticsChecks:Record<string,string>={numeric:'金额',unit:'金额/原单位配对',currency:'币种',period:'期间（给定约束）',scope:'范围（给定约束）',evidence:'原文引用',column:'来源列',complete:'完整记录'};
export const semanticsScores={format_valid:'格式有效',answered:'已回答',abstained:'拒答/未答',numeric_correct:'金额正确',unit_correct:'金额/原单位配对',evidence_correct:'引用正确',column_correct:'来源列正确',complete_correct:'完整正确',candidate_covered:'候选覆盖'};
const requireValue=(v:unknown,message='财务语义记录结构或归属不一致。')=>{if(!v)throw Error(message);};
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export function validateFilingSemantics(body:SemanticsEnvelope):SemanticsEnvelope {
 requireValue(body&&['empty','verified','missing'].includes(body.artifact_status)&&Array.isArray(body.missing_artifacts)&&Number.isInteger(body.verified_artifacts));
 if(body.artifact_status==='empty'){requireValue(body.record===null&&body.sha256===null);return body;}
 if(body.artifact_status==='missing'){requireValue(body.missing_artifacts.length>0);return body;}
 const r=body.record;requireValue(r&&r.schema==='filing-semantics-publication-v1'&&hash(body.sha256)&&Array.isArray(r.studies)&&r.studies.length>0&&Array.isArray(r.limitations));
 const studies=r!.studies;requireValue(new Set(studies.map(s=>s.split)).size===studies.length);
 for(const s of studies){
  const n=s.split==='development'?18:9;
  requireValue(['development','evaluation'].includes(s.split)&&typeof s.run_id==='string'&&s.documents.length===n/3&&s.cases.length===n&&s.rows.length===n*2&&s.methods.length===2&&s.metrics.length===2);
  const symbols=s.split==='development'?['600519','600036','600585','000333','601318','600887']:['000651','601166','600900'];
  requireValue(new Set(s.documents.map(d=>d.doc_id)).size===n/3&&s.documents.every(d=>symbols.includes(d.symbol)&&d.period===(['600519','600036','600585'].includes(d.symbol)?'2024Q1':'2025Q1')&&d.split===s.split&&d.doc_id===d.symbol+'-'+d.period&&hash(d.pdf_sha256)));
  requireValue(s.methods.every(m=>['structure_rule','structure_model'].includes(m.id))&&new Set(s.methods.map(m=>m.id)).size===2);
  requireValue(new Set(s.cases.map(c=>c.case_id)).size===n&&new Set(s.rows.map(row=>row.case_id+'/'+row.method)).size===n*2);
  for(const c of s.cases){requireValue(['revenue','net_profit_parent','operating_cashflow'].includes(c.metric)&&s.documents.some(d=>d.doc_id===c.doc_id)&&c.case_id===c.doc_id+'/'+c.metric&&Array.isArray(c.candidates)&&Array.isArray(c.eligible_ids)&&Array.isArray(c.rule_reasons));requireValue(new Set(c.candidates.map(v=>v.candidate_id)).size===c.candidates.length&&c.eligible_ids.every(id=>c.candidates.some(v=>v.candidate_id===id&&v.eligible)));}
  for(const row of s.rows){requireValue(s.cases.some(c=>c.case_id===row.case_id&&c.doc_id===row.doc_id&&c.metric===row.metric)&&s.methods.some(m=>m.id===row.method)&&['ok','invalid_output','input_too_long','error'].includes(row.status)&&row.reference&&Array.isArray(row.reference.variants)&&Array.isArray(row.selected_candidate_ids)&&Array.isArray(row.error_reasons));requireValue(['answered',...Object.keys(semanticsChecks)].every(k=>typeof row.checks[k]==='boolean'));const c=s.cases.find(c=>c.case_id===row.case_id)!;requireValue(row.selected_candidate_ids.every(id=>c.eligible_ids.includes(id)));requireValue(row.status==='ok'||(!row.prediction&&!Object.values(row.checks).some(Boolean)));}
  for(const score of s.metrics){const rows=s.rows.filter(row=>row.method===score.method);requireValue(score.total===n&&rows.length===n&&score.format_valid===rows.filter(row=>row.status==='ok').length&&score.answered===rows.filter(row=>row.checks.answered).length&&score.candidate_covered===rows.filter(row=>row.candidate_covered).length);for(const key of Object.keys(semanticsChecks))requireValue(score[(key+'_correct') as keyof SemanticsMetric]===rows.filter(row=>row.checks[key]).length);}
  if(s.split==='evaluation')requireValue(hash(s.method_freeze_sha256),'新公司结果缺少方法冻结身份。');
 }
 return body;
}
export async function readFilingSemantics(signal?:AbortSignal){let response;try{response=await fetch('/api/v1/filing-semantics-v2',{signal,cache:'no-store'});}catch(error){if((error as Error).name==='AbortError')throw error;throw Error('财务语义服务暂时不可用，请重试。');}if(!response.ok){const body=await response.json().catch(()=>null);throw Error(body?.message||'财务语义来源核验失败，请重试。');}return validateFilingSemantics(await response.json());}
export const semanticsPdfUrl=(docId:string,page?:number)=>'/api/v1/filing-semantics-v2/pdf?doc_id='+encodeURIComponent(docId)+(page?'#page='+page:'');
export function semanticsReport(body:SemanticsEnvelope){
 if(body.artifact_status!=='verified'||!body.record)return '# 财务语义校验\n\n来源尚未验证，不展示成绩。';
 const rows=(study:SemanticsStudy)=>study.rows.map(row=>{
  const c=study.cases.find(c=>c.case_id===row.case_id)!;
  return [
   `### ${study.documents.find(d=>d.doc_id===row.doc_id)?.name} · ${row.label} · ${study.methods.find(m=>m.id===row.method)?.label}`,
   `状态：${row.status}；预测：${row.prediction?.value??'拒答 / 无有效输出'} ${row.prediction?.unit??''}；期间/范围（给定约束）：${row.prediction?.period??'未给出'} / ${row.prediction?.scope??'未给出'}。`,
   Object.entries(semanticsChecks).map(([k,label])=>label+'：'+(row.status!=='ok'?'未能核验':row.checks[k]?'通过':'未通过')).join('；'),
   `选择候选：${row.selected_candidate_ids.join('、')||'无'}；规则说明：${c.rule_reasons.map(semanticsReason).join('；')}；差异：${row.error_reasons.map(semanticsReason).join('；')||'无记录'}`,
   `助手参考（待人工审计）：${row.reference.status}；前6页口径支持${row.reference.input_context_complete?'完整':'有缺口'}。`,
   ...row.reference.variants.map(v=>`参考：${v.value??'未给出'} ${v.unit??''}；引用：${v.quote??'无'}；单位依据页：${v.unit_evidence_pages.join('、')}；范围依据页：${v.scope_evidence_pages.join('、')}。`),
   ...c.candidates.map(v=>`候选 ${v.candidate_id}：${v.original_token}；${v.semantic.financial_type} / ${v.semantic.period_role} / ${v.semantic.adjustment_role} / ${v.semantic.scope_role}；${v.eligible?'合格':'排除'}：${v.reasons.map(semanticsReason).join('；')}；表头：${v.header_evidence.map(h=>'第'+h.page+'页 '+h.quote).join('；')}；单位依据：${v.unit_evidence}；原行：${v.field.quote}`)
  ].join('\n\n');
 });
 return ['# 财务语义校验','助手视觉参考待人工审计；期间与范围是给定查询约束。结构合法性属于规则贡献，不能计作模型语义提升。',`发布SHA256：${body.sha256}`,...body.record.studies.flatMap(s=>[
  `## ${s.split==='development'?'开发验证 · 2024Q1':'新公司评估 · 2025Q1'}`,
  `运行：${s.run_id}\n\n方法冻结：${s.method_freeze_sha256??'尚未冻结'}`,
  ...s.metrics.map(m=>`${s.methods.find(v=>v.id===m.method)?.label}：格式 ${m.format_valid}/${m.total}；回答 ${m.answered}/${m.total}；拒答/未答 ${m.abstained}/${m.total}；完整正确 ${m.complete_correct}/${m.total}。`),...rows(s),...s.limitations
 ]),...body.record.limitations].join('\n\n');
}
const reasonLabels:Record<string,string>={header_coverage_unknown:'本轮解析器未建立可靠表头归属，列待核',unsupported_currency:'来源币种不在当前方法支持范围',scope_header_unknown:'合并/母公司列范围无法明确归属',column_scope:'列对应的合并/母公司范围需核对',before_adjustment:'调整前列，不作为当期最终金额',unknown_unit:'本轮解析器未确认原始单位',unknown_currency:'当前结构证据未确认币种',parent_scope:'来源属于母公司口径',deducted_nonrecurring:'扣非净利润，非当前查询字段',parent_profit_label_unknown:'缺少归属于母公司股东的字段依据',quote_budget_exceeded:'原行超出引用预算，保留待核',unique_consistent_source_amount:'仅有一个一致的合格当期金额',conflicting_eligible_amounts:'多个合格来源金额冲突，规则拒答',no_eligible_amount:'没有合格当期金额，规则拒答',layout_unavailable:'缺少可靠布局，无法确认来源列'};
export function semanticsReason(reason:string){const label=reasonLabels[reason]||(reason.startsWith('not_amount:')?'财务类型不是金额':reason==='period:prior'?'表头属于上期，排除':reason.startsWith('period:')?'表头期间无法确认，排除':null);return label?`${label}（${reason}）`:reason;}







export function semanticsCandidateValue(candidate:SemanticsCandidate){
 const kind=candidate.semantic.financial_type;
 if(kind==='amount')return filingAmount(candidate.field);
 if(kind==='rate'||kind==='ratio'||kind==='percentage')return candidate.original_token+' · 比率（单位见表头）';
 if(kind==='per_share')return candidate.original_token+' · 每股指标（单位见表头）';
 return candidate.original_token+' · 类型待核';
}

