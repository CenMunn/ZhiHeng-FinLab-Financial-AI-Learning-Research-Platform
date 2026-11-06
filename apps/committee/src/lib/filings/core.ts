import { z } from 'zod';
import {sourcePeriods,periodLabel,metricPeriodQuestion} from './period.ts';
import {extractStatementBlocks} from './statements.ts';
import type {TextItem} from './layout.ts';
import {reviewCalculation,calculationContract} from './calculations.ts';
import {buildAdoptedReport,type AdoptedReport} from './adoption.ts';
import {stripNote,metricLabel} from './labels.ts';
import {sourceCitation,type SourcePageMapEntry} from './source-pages.ts';
import type {HeaderEvidence} from './statements.ts';
import type {ProtocolExport} from './protocol.ts';
export {buildAdoptedReport} from './adoption.ts';

export type Page = { page: number; uploadedPage?:number; text: string; layoutRows?:{text:string}[];layoutItems?:TextItem[];physicalPageDeclared?:boolean };
export type Fact = { sourceId: string; page: number; label: string; year: number; period?:string;periodAliases?:string[]; annualFlow?:boolean; scope: 'consolidated'|'parent'; unit: string; value: string;currency?:'人民币'|null; quote?: string;statementId?:string;headerSourceIds?:string[];headerEvidence?:HeaderEvidence[];tableTitle?:string;unitEvidence?:string };
const factSchema=z.object({sourceId:z.string().max(150),label:z.string().min(1).max(150),year:z.number().int().min(1990).max(2100),period:z.string().regex(/^20\d{2}(?:-\d{2}-\d{2})?$/).optional(),scope:z.enum(['consolidated','parent']),unit:z.enum(['元','千元','万元','百万元','亿元','元/股']),value:z.string().max(40)}).strict();
const calculationSchema=z.object({label:z.string().min(1).max(150),operation:z.enum(['difference','sum','ratio','growth','unit_conversion','percentage_point_change','difference_ratio','absolute_ratio','average_denominator_ratio']),operands:z.array(z.number().int().nonnegative()).min(1).max(8),value:z.string().max(40),unit:z.string().max(20)}).strict();
export const draftSchema=z.object({answer:z.string().max(10000),facts:z.array(factSchema).max(100),calculations:z.array(calculationSchema).max(30),limitations:z.array(z.string().max(2000)).max(20),refused:z.boolean()}).strict();
export type Draft=z.infer<typeof draftSchema>;
export function parseDraft(content:string):Draft{return draftSchema.parse(JSON.parse(content));}
export function parsePageMap(input:string,count:number):number[]{
  if(!input.trim())return Array.from({length:count},(_,i)=>i+1);
  const result:number[]=[];
  for(const part of input.split(/[,，]/)){const m=part.trim().match(/^(\d{1,5})(?:\s*-\s*(\d{1,5}))?$/);if(!m)throw new Error('原页码格式：188-190,193');const a=Number(m[1]),b=Number(m[2]??m[1]);if(a<1||b<a||b-a>40)throw new Error('原页码范围不合法');for(let i=a;i<=b;i++)result.push(i);}
  if(result.length!==count||new Set(result).size!==count||result.some((v,i)=>i>0&&v<=result[i-1]))throw new Error('页码须按上传顺序填写，数量与 PDF 一致且递增不重复');return result;
}
function amount(value:string):string|null{
  let s=value.trim().replace(/[,，\s]/g,'');if(/^[-–—]+$/.test(s))return null;
  if(/^\([\d.]+\)$/.test(s))s='-'+s.slice(1,-1);
  if(!/^-?\d+(?:\.\d+)?$/.test(s))return null;
  return s.replace(/^(-?)0+(?=\d)/,'$1');
}
const norm=metricLabel;
function qualifiedChild(f:Draft['facts'][number],source:Fact,page:Fact[]){
 const m=f.label.replace(/\s/g,'').match(/^其他应收款(?:项下|下)?(?:其中[：:]?)(应收股利|应收利息)$/);
 if(!m||norm(source.label)!==m[1]||!source.statementId)return false;
 // A known main-statement hierarchy must also exist in this actual block,
 // same column and source order. An arbitrary prefix is never discarded.
 const column=page.filter(s=>s.statementId===source.statementId&&s.scope===source.scope&&s.year===source.year&&s.period===source.period&&s.unit===source.unit);
 const childIndex=column.indexOf(source),parentIndex=column.findIndex(s=>norm(s.label)==='其他应收款');
 return parentIndex>=0&&childIndex>parentIndex&&column.slice(parentIndex+1,childIndex).every(s=>['应收股利','应收利息'].includes(norm(s.label)));
}
function declaredLabel(f:{label:string;scope:Fact['scope'];year:number;period?:string;unit:string},tableTitle?:string){
  const m=f.label.trim().match(/^(.*)[（(]([^（）()]+)[）)]$/);if(!m)return norm(f.label);
  const extra=m[2].replace(/(合并|本集团|母公司|本银行|本行|本公司|公司)\s*\/\s*(?=合并|本集团|母公司|本银行|本行|本公司|公司)/g,'$1,').replace(/[\s,，、;；]/g,''),tokens:string[]=[];let remaining=extra;
  while(remaining){const token=tableTitle&&remaining.startsWith(tableTitle)?tableTitle:remaining.match(/^((?:合并|母公司|本公司|银行|公司)(?:资产负债表|利润表|损益表|现金流量表)|本集团|本银行|本行|本公司|母公司|合并|公司|20\d{2}(?:年\d{1,2}月\d{1,2}日|年(?:末|度|比较列)?|-\d{2}-\d{2})?|(?:人民币)?(?:百万元|千元|万元|亿元|元\/股|元))/)?.[0];if(!token)return norm(f.label);tokens.push(token);remaining=remaining.slice(token.length);}
  let recognized=false;
  for(const t of tokens){
    if(/(?:资产负债表|利润表|损益表|现金流量表)$/.test(t)){
      if(!tableTitle)return norm(f.label);
      const declaredScope=t.startsWith('合并')?'consolidated':'parent';
      const exactJoint=tableTitle===t&&/^(?:合并及|合并.*(?:及|和))/.test(t);
      if(!exactJoint&&(declaredScope!==f.scope||!(tableTitle===t||tableTitle.startsWith(t+'及')||tableTitle.startsWith(t+'和'))))return null;
      recognized=true;continue;
    }
    if(['本集团','合并','母公司','本银行','本行','本公司','公司'].includes(t)){const scope=['本集团','合并'].includes(t)?'consolidated':'parent';if(scope!==f.scope)return null;recognized=true;continue;}
    if(/^20\d{2}(?:年\d{1,2}月\d{1,2}日|-\d{2}-\d{2})$/.test(t)){const dates=sourcePeriods(t);if(dates.length!==1||dates[0]==='invalid'||dates[0]!==f.period||Number(t.slice(0,4))!==f.year)return null;recognized=true;continue;}
    if(/^20\d{2}(?:年(?:末|度|比较列)?)?$/.test(t)){if(Number(t.slice(0,4))!==f.year)return null;recognized=true;continue;}
    if(/^(?:人民币)?(?:元|千元|万元|百万元|亿元|元\/股)$/.test(t)){const unit=t.replace(/^人民币/,'');if(unit!==f.unit&&!(unit==='元'&&f.unit==='元/股'&&/每股/.test(m[1].replace(/\s/g,''))))return null;recognized=true;continue;}
    return norm(f.label); // Other parentheticals are substantive row text.
  }
  return recognized?norm(m[1]):norm(f.label);
}
// Facts are emitted only from a resolved statement block; provenance is internal.
export function extractFacts(pages:Page[],sha256:string):Fact[]{
  const result:Fact[]=[];
  for(const block of extractStatementBlocks(pages,sha256)){
    if(block.status!=='parsed'||!block.unit)continue;
    const n=block.columns.length,numeric='(?:\\(?-?\\d[\\d,，]*(?:\\.\\d+)?\\)?|[-–—])';
    const rowRegex=new RegExp('((?:'+numeric+'[ \\t|]+){'+(n-1)+'}'+numeric+')[ \\t|]*$');
    for(const row of block.rows){
      const line=row.text,m=line.match(rowRegex);
      const positionedCells=row.cells?.length===n&&!!row.label;
      if(!positionedCells&&(!m||m.index===undefined))continue;
      let label=positionedCells?row.label!:line.slice(0,m!.index).trim().replace(/[|\s]+$/,'');
      label=stripNote(label);
      const compactLabel=label.replace(/\s/g,''),eps=/每股/.test(compactLabel);
      if(!/[\u4e00-\u9fff]/.test(label)||/附注|单位/.test(label)||/^20\d{2}\s*年\s*(?:末|度)$/.test(label)||(/人民币/.test(label)&&!eps))continue;
      if(eps){
        const units=[...(label+' '+(row.unitEvidence??'')).matchAll(/[（(]([^（）()]+)[）)]/g)].map(m=>m[1].replace(/\s/g,'')).filter(v=>/[元分股]/.test(v));
        if(!units.length||units.some(u=>!/^(?:人民币)?元(?:\/股)?$/.test(u)))continue;
      }
      const tokens=positionedCells?row.cells!:m![1].split(/[\s|]+/).filter(Boolean);if(tokens.length!==n)continue;
      tokens.forEach((v,i)=>{if(v===null)return;const value=amount(v);if(value===null)return;const col=block.columns[i];
        const endBalance=/现金流量表$/.test(block.name)&&/(?:期末|年末)现金及现金等价物余额/.test(metricLabel(label));
        const openingBalance=/现金流量表$/.test(block.name)&&/(?:期初|年初)现金及现金等价物余额/.test(metricLabel(label));
        const period=block.annualPeriodConfirmed&&col.period?.length===4&&(endBalance||openingBalance)?`${col.year}-${endBalance?'12-31':'01-01'}`:col.period;
        result.push({sourceId:`pdf:${sha256}:p${block.page}`,page:block.page,label,year:col.year,period,periodAliases:col.periodAliases,annualFlow:block.annualPeriodConfirmed===true&&/(?:利润表|损益表|现金流量表)$/.test(block.name)&&!endBalance&&!openingBalance,scope:col.scope,unit:eps?'元/股':block.unit!,currency:block.currency??null,value,quote:line.trim(),statementId:block.id,headerSourceIds:block.headerSourceIds,headerEvidence:block.headerEvidence,tableTitle:block.name,unitEvidence:row.unitEvidence});});
    }
  }
  return result;
}
type Check={kind:'fact'|'calculation';index:number;ok:boolean;reason:string;code?:string;normalizedValue?:string};
function decimal(value:string){const s=amount(value);if(s===null)throw new Error('金额格式不合法');const [a,b='']=s.split('.');const sign=a.startsWith('-')?-BigInt(1):BigInt(1);return {n:BigInt(a.replace('-','')+b)*sign,d:BigInt(10)**BigInt(b.length)};}
function equalValue(a:string,b:string){try{const x=decimal(a),y=decimal(b);return x.n*y.d===y.n*x.d;}catch{return false;}}
export function reviewDraft(draft:Draft,facts:Fact[],options:{question?:string}={}){
  const checks:Check[]=[],acceptedFacts:Draft['facts']=[],acceptedIndices=new Set<number>(),acceptedCalculations:Draft['calculations']=[],factSources:{originalIndex:number;source:Fact}[]=[];
  draft.facts.forEach((f,i)=>{
    const sourcePage=facts.filter(s=>s.sourceId===f.sourceId);
    const label=declaredLabel(f,sourcePage[0]?.tableTitle),periodQuestion=metricPeriodQuestion(options.question??'',[f.label,label??f.label]);
    const dates=sourcePeriods(periodQuestion).filter(p=>p.length>4&&Number(p.slice(0,4))===f.year);
    const requiredPeriod=f.period&&f.period.length>4?f.period:(new Set(dates).size===1?dates[0]:undefined);
    const sameLabel=sourcePage.filter(s=>{const candidate=declaredLabel(f,s.tableTitle);return candidate!==null&&(declaredLabel(s,s.tableTitle)===candidate||qualifiedChild(f,s,sourcePage));});
    const sameScope=sameLabel.filter(s=>s.scope===f.scope),sameUnit=sameScope.filter(s=>s.unit===f.unit);
    const candidates=sameUnit.filter(s=>s.year===f.year||!!f.period&&f.period.length===10&&s.periodAliases?.includes(f.period));
    const periods=new Set(candidates.map(s=>s.period??String(s.year)));
    // This corrects only a redundant year-end cutoff attached to a source-proven
    // annual flow asked explicitly for that annual period. No general date alias.
    const annualCutoff=(s:Fact)=>s.annualFlow===true&&s.period===String(f.year)&&f.period===`${f.year}-12-31`&&periodQuestion===`${f.year}年度`;
    const periodCandidates=candidates.filter(s=>!requiredPeriod||(s.period??String(s.year))===requiredPeriod||s.periodAliases?.includes(requiredPeriod)||annualCutoff(s));
    const invalidAnnotation=label===null&&!sameLabel.length,invalidYear=!!f.period&&Number(f.period.slice(0,4))!==f.year,ambiguous=!requiredPeriod&&periods.size>1;
    const source=invalidAnnotation||invalidYear||ambiguous?undefined:periodCandidates.find(s=>equalValue(s.value,f.value));
    const failure=invalidAnnotation?['ANNOTATION_CONFLICT','指标括注与结构化年度、期间、范围或单位冲突']:invalidYear?['PERIOD_YEAR_CONFLICT','候选期间与候选年度冲突']:!sourcePage.length?['SOURCE_PAGE_UNRESOLVED','所引来源页无已解析事实；需核对来源编号与表头解析']:!sameLabel.length?['LABEL_UNMATCHED','所引来源页未匹配指标行名，不能删除实质性限定词后强行采用']:!sameScope.length?['SCOPE_MISMATCH','同名来源行与候选报表范围不一致']:!sameUnit.length?['UNIT_MISMATCH','来源单位与候选单位不一致']:!candidates.length?['YEAR_MISMATCH','来源年度与候选年度不一致']:ambiguous?['PERIOD_AMBIGUOUS','同年度存在多个来源时点，候选未明确期间']:!periodCandidates.length?['PERIOD_MISMATCH','来源完整期间与候选或题目所问期间不一致']:['VALUE_MISMATCH','来源金额与候选金额不一致；不自动替换模型数值'];
    const success=source&&annualCutoff(source)?`来源明确为${f.year}年度发生额，题目明确询问该年度；候选年末截止日规范为年度期间${source.period}，原候选保留审计`:source&&f.period&&source.periodAliases?.includes(f.period)?`来源、行名、范围、单位与数值一致；依据明确年末报表的期初比较列，将${f.period}规范为${source.period}，原候选保留审计`:'来源、行名、年度/完整期间、范围、单位、数值一致';
    checks.push({kind:'fact',index:i,ok:!!source,code:source?'SOURCE_MATCHED':failure[0],reason:source?success:failure[1]});
    if(source){acceptedFacts.push({...f,year:source.year,period:source.period});acceptedIndices.add(i);factSources.push({originalIndex:i,source});}
  });
  const contract=calculationContract(options.question??'');
  const canonicalFacts=draft.facts.map((f,i)=>{const source=factSources.find(s=>s.originalIndex===i)?.source;return {...f,year:source?.year??f.year,period:source?.period??f.period,label:source?declaredLabel(source,source.tableTitle)??source.label:declaredLabel(f)??f.label};});
  draft.calculations.forEach((c,i)=>{
    const cited=c.operands.length>0&&c.operands.every(v=>acceptedIndices.has(v));
    const result=cited?reviewCalculation(c,canonicalFacts,contract):{ok:false,reason:'输入未经核验或操作数缺失，不自动替换引用'};
    checks.push({kind:'calculation',index:i,...result});if(result.ok)acceptedCalculations.push({...c,value:result.normalizedValue??c.value});
  });
  return {checks,acceptedFacts,acceptedCalculations,factSources,answerVerified:false as const,semanticReview:'pending' as const};
}
export function renderReport(run:{id:string;question:string;mode:string;companyName:string;sha256:string;createdAt:string;draft:Draft|null;review:ReturnType<typeof reviewDraft>|null;adoptedReport?:AdoptedReport|null;protocol?:ProtocolExport;error?:string;durationMs:number;sourcePages?:number[];sourcePageMap?:SourcePageMapEntry[]}){
  const {draft,review}=run,verified=run.mode==='current_evidence';
  const adopted=verified&&draft&&review?(run.adoptedReport??buildAdoptedReport(draft,review,run.question,run.id)):null;
  if(adopted&&adopted.runId!==run.id)throw new Error('采用内容与报告编号不一致，拒绝导出错配快照');
  const inert=(s:string)=>s.replace(/[\\`*_{}\[\]()#+.!|>~-]/g,'\\$&');
  const clean=(s:string)=>inert(s.replace(/[\r\n|]/g,' '));
  const citation=(id:string)=>{const prefix=`pdf:${run.sha256}:p`;if(run.sourcePageMap!==undefined)return sourceCitation(run.sourcePageMap,run.sha256,id)??`${clean(id)}（来源待核对）`;return (run.sourcePages??[]).some(page=>id===`${prefix}${page}`)?`本PDF原物理页 ${id.slice(prefix.length)}（归档来源编号；上传页映射未记录，原报告页待核对）`:`${clean(id)}（来源待核对）`;};
  let md=`# ${clean(run.companyName)}财务证据报告\n\n任务：${clean(run.question)}\n\n报告编号：${run.id}\n\n生成时间：${run.createdAt}\n\n模式：${verified?'自研核验':'简单单模型'}\n\nPDF SHA256：${run.sha256}\n\n## 来源与结果\n\n`;
  if(run.error)md+=`运行失败：${clean(run.error)}\n\n`;
  md+='来源为本次上传PDF。上传PDF物理页为本文件1至N页；原报告物理页和公司身份由上传者声明，尚未独立鉴定。未声明或未记录的页码不予补造；完整来源ID及页码映射保留在JSON记录中。\n\n';
  if(verified){md+='## 最终采用内容与任务缺口\n\n'+(!adopted?'任务未完成：没有可采用的模型与核验结果。':adopted.coverage.status==='incomplete'?'任务未完成：存在下列证据或计算缺口。':'已生成限定证据报告，整项任务仍待人工语义复核。')+'\n\n';for(const gap of adopted?.coverage.missing??[])md+=`- ${clean(gap)}\n`;md+='\n';}
  const facts=verified?adopted?.facts??[]:draft?.facts??[];
  if(verified&&adopted?.answerLines?.length){md+='## 任务回应（依据已核验数据与来源状态）\n\n';for(const line of adopted.answerLines)md+=`- ${clean(line)}\n`;md+='\n';}
  md+='|指标|期间/时点|范围|数值|单位|币种|来源|\n|---|---|---|---:|---|---|---|\n';
  for(const f of facts)md+=`|${clean(f.label)}|${clean(periodLabel(f))}|${f.scope==='consolidated'?'合并':'母公司/本银行'}|${clean(f.value)}|${clean(f.unit)}|${clean(verified&&'currency' in f?String(f.currency??'来源未明示'):'待核对')}|${citation(f.sourceId)}|\n`;
  md+='\n## 计算结果\n\n';for(const c of verified?adopted?.calculations??[]:draft?.calculations??[]){md+=`- ${clean(c.label)}：${clean(c.value)} ${clean(c.unit)}；${c.operation}\n`;for(const index of c.operands){const f=verified?adopted?.facts[index]:draft?.facts[index];if(f)md+=`  - 输入 #${index}：${clean(f.label)}，${clean(periodLabel(f))}，${f.scope==='consolidated'?'合并':'母公司/本银行'}，${clean(f.value)} ${clean(f.unit)}，${citation(f.sourceId)}\n`;}}
  if(run.protocol){
    md+='\n## 来源封装与导出合同\n\n两种模式共用机械来源定位；基线的原答和数值不因定位而修正。合同格式通过不能代替数值、语义和引用正确性审核。\n\n';
    md+=`JSON合同结构：${run.protocol.validation.schemaValid?'通过':'未通过'}；来源封装：${run.protocol.validation.valid?'通过（仍待语义审核）':'存在缺口'}；交付状态：${run.protocol.answer.status}\n\n`;
    for(const gap of run.protocol.evidenceGaps)md+=`- ${clean(gap)}\n`;
    md+='\n表头及数据行来自PDF坐标解析；竖线仅作列分隔。继承表头作为独立原页证据列示，不冒称本页文字。\n\n';
    for(const e of run.protocol.answer.evidence){
      md+=`### 上传PDF物理页 ${e.input_physical_page}；原报告物理页 ${e.source_physical_page}（上传者声明）\n\n表名：${clean(e.table_title)}\n\n表头文本：${clean(e.header_evidence)}\n\n`;
      for(const row of e.data_rows)md+=`- 原数据行：${clean(row)}\n`;
      if(!e.data_rows.length)md+='- 表头来源页引用，本项不提供其他页数据行。\n';
      md+='\n';
    }
  }else if(verified&&adopted?.facts.length){
    md+='\n## 逐项来源证据\n\n表头与数据行来自PDF坐标解析；竖线仅作列分隔。规范期间/时点与原页逐字列头分别保存，继承表头单独标注来源页。\n\n';
    for(const [i,f] of adopted.facts.entries()){
      md+=`### 事实 ${i}：${clean(f.label)}\n\n${citation(f.sourceId)}；表名：${clean(f.tableTitle??'未确认')}\n\n`;
      for(const h of f.headerEvidence)md+=`- ${h.relation==='inherited'?'继承表头（引用前页，非本页逐字）':'本页实际表头'}：${citation(h.sourceId)}\n\n    ${clean(h.text)}\n\n`;
      md+=`- 原数据行：${clean(f.quote??'未定位，不补造')}\n\n`;
    }
  }
  md+='\n## 核验与边界\n\n'+(verified?`通过的事实 ${facts.length} 条；拦截项 ${review?.checks.filter(c=>!c.ok).length??0} 条。这里只检查结构化证据和计算，任务覆盖、自由文字及拒答合理性待人工语义复核。`:'本模式未执行自研核验，下列原答及结构化结果须独立复核。')+'\n\n';
  for(const c of review?.checks??[])if(!c.ok)md+=`- ${c.kind} #${c.index}：${c.reason}\n`;
  if(verified){md+='\n## 来源与推断限制\n\n';for(const limitation of adopted?.coverage.limitations??[])md+=`- ${clean(limitation)}\n`;md+='\n原始模型回答、自述限制和计算标签仅保留在同一报告编号的JSON审计字段中，未进入最终采用正文。\n';}
  else{md+='\n## 模型原稿（未核验，保留审计）\n\n'+inert(draft?.answer??'无可用回答')+'\n\n';if(draft?.refused)md+='模型标记拒答；合理性尚待人工复核。\n\n';for(const l of draft?.limitations??[])md+=`- 模型自述限制（未核验）：${clean(l)}\n`;}
  md+=`\n## 运行记录\n\n完整模型与核验耗时 ${run.durationMs} ms。逐次请求、用量、失败及原始回复见 JSON 导出。\n`;
  return md;
}


