import {z} from 'zod';
import {metricLabel} from './labels.ts';
import {cashRollForwardPeriod} from './calculations.ts';
import {questionFacts} from './intent.ts';
import type {Draft,Fact,Page} from './core.ts';
import type {AdoptedReport} from './adoption.ts';
import {nonNumericEpsCells,type SourceBlock} from './source-state.ts';

// Same strict public answer contract for both paths. No question/gold lookup,
// provider retry, candidate correction or financial recomputation here.
export const protocolAnswerSchema=z.object({
  question_id:z.string(),status:z.enum(['answered','insufficient_evidence']),
  scope:z.string(),period:z.string(),unit:z.string(),currency:z.string().nullable(),
  answer:z.string(),value:z.string().nullable(),formula:z.string().nullable(),
  operands:z.array(z.object({name:z.string(),value:z.string(),scope:z.string(),period:z.string(),unit:z.string()})),
  evidence:z.array(z.object({input_physical_page:z.number().int().min(1),source_physical_page:z.number().int().min(1),table_title:z.string(),data_rows:z.array(z.string()),header_evidence:z.string().min(1)})),
  answerable_facts:z.array(z.unknown()),missing_evidence:z.array(z.string()),must_not_infer:z.array(z.string()),
}).strict();
type ProtocolRun={id:string;sha256:string;mode:string;question?:string;draft:Draft|null;adoptedReport?:AdoptedReport|null;error?:string;status?:string};
type ProtocolDocument={sha256:string;pages:Page[];facts:Fact[];statementBlocks?:SourceBlock[]};
const unique=(xs:string[])=>[...new Set(xs)];
const joined=(xs:string[])=>unique(xs).join('；')||'未核实';
const period=(f:Pick<Fact,'period'|'year'>)=>f.period??String(f.year);
const key=(f:Pick<Fact,'sourceId'|'label'|'year'|'period'|'scope'|'unit'>)=>JSON.stringify([f.sourceId,metricLabel(f.label),f.year,period(f),f.scope,f.unit]);

export function buildProtocolExport(run:ProtocolRun,doc:ProtocolDocument,questionId=run.id){
  const current=run.mode==='current_evidence';
  const body=run.error?null:current?run.adoptedReport:run.draft;
  const facts=body?.facts??[],calculations=body?.calculations??[];
  const gaps:string[]=[],evidence:z.infer<typeof protocolAnswerSchema>['evidence']=[],currencies:string[]=[];
  for(const [index,f] of facts.entries()){
    // A baseline candidate locates a row by source and column coordinates.
    // Its value and prose are NEVER replaced by the source value/prose.
    const sources=doc.sha256===run.sha256?doc.facts.filter(s=>key(s)===key(f)):[];
    if(sources.length!==1){gaps.push(`事实${index}：来源编号、指标和完整列口径未唯一定位；不猜测原行与表头`);continue;}
    const source=sources[0],headers=source.headerEvidence??[];
    const rowPage=doc.pages.findIndex(p=>f.sourceId===`pdf:${doc.sha256}:p${p.page}`);
    if(rowPage<0||doc.pages[rowPage].physicalPageDeclared!==true){gaps.push(`事实${index}：原报告物理页未声明或来源编号不匹配`);continue;}
    if(!source.tableTitle||!source.quote||!headers.length||!headers.some(h=>h.sourceId===source.sourceId&&h.relation==='own')){
      gaps.push(`事实${index}：缺少与原行绑定的实际表名、数据行或本页表头；不使用整页前缀补造`);continue;
    }
    if(source.currency)currencies.push(source.currency);
    for(const h of headers){
      const i=doc.pages.findIndex(p=>h.sourceId===`pdf:${doc.sha256}:p${p.page}`&&p.page===h.page),p=doc.pages[i];
      if(i<0||p.physicalPageDeclared!==true||!h.text.trim()){
        gaps.push(`事实${index}：${h.relation==='inherited'?'继承':'本页'}表头来源页或实际文本缺失`);continue;
      }
      const local=h.sourceId===source.sourceId;
      evidence.push({input_physical_page:i+1,source_physical_page:p.page,table_title:source.tableTitle,
        data_rows:local?[...(source.unitEvidence?[source.unitEvidence]:[]),source.quote]:[],header_evidence:h.text});
    }
  }
  for(const observation of current?run.adoptedReport?.boundaryEvidence??[]:[]){
    const source=doc.sha256===run.sha256?nonNumericEpsCells(doc.statementBlocks).find(s=>JSON.stringify(s)===JSON.stringify(observation)):undefined;
    if(!source){gaps.push('非金额来源状态未在已解析报表唯一复核；不导出未经定位的横杠或空白');continue;}
    for(const h of source.headerEvidence){
      const i=doc.pages.findIndex(p=>h.sourceId===`pdf:${doc.sha256}:p${p.page}`&&p.page===h.page),p=doc.pages[i];
      if(i<0||p.physicalPageDeclared!==true||!h.text.trim()){gaps.push('非金额来源状态的表头物理页或文本未确认');continue;}
      evidence.push({input_physical_page:i+1,source_physical_page:p.page,table_title:source.tableTitle,data_rows:h.sourceId===source.sourceId?[...(source.unitEvidence?[source.unitEvidence]:[]),source.quote]:[],header_evidence:h.text});
    }
  }
  const operands=calculations.flatMap(c=>c.operands.map(i=>{
    const f=facts[i];if(!f){gaps.push(`计算${c.operation}：操作数下标${i}未交付`);return {name:'未交付',value:'未核实',scope:'未核实',period:'未核实',unit:'未核实'};}
    return {name:f.label,value:f.value,scope:f.scope,period:period(f),unit:f.unit};
  }));
  const missing=unique([...(current?run.adoptedReport?.coverage.missing??[]:run.draft?.limitations??[]),...gaps,
    ...(!body?['运行失败或尚无可用结果'+(run.error?`：${run.error}`:'')]:[]),
    ...(facts.length===0?['本次未交付可核对的结构化事实；范围、期间及单位未核实']:[])]);
  const selected=run.question?questionFacts(run.question,facts):facts;
  const resultPeriods=calculations.length===1?[cashRollForwardPeriod(calculations[0],facts)??(facts[calculations[0].operands[0]]?period(facts[calculations[0].operands[0]]):'未核实')]:selected.map(period);
  const answer={question_id:questionId,status:(!body||!facts.length||gaps.length||run.draft?.refused||current&&!!run.adoptedReport?.coverage.missing.length?'insufficient_evidence':'answered') as 'answered'|'insufficient_evidence',
    scope:joined((calculations.length?facts:selected).map(f=>f.scope)),period:joined(resultPeriods),unit:joined((calculations.length?calculations:selected).map(f=>f.unit)),currency:unique(currencies).length===1?currencies[0]:null,
    answer:!body?'任务未完成；详见运行失败和证据缺口。':current?(run.adoptedReport?.answerLines??[]).join('\n'):run.draft!.answer,
    value:current&&run.adoptedReport?.boundaryMissing?.length?null:calculations.length===1?calculations[0].value:selected.length===1?selected[0].value:null,
    formula:calculations.length?JSON.stringify(calculations.map(({label,operation,operands,unit})=>({label,operation,operands,unit}))):null,
    operands,evidence,answerable_facts:facts,missing_evidence:missing,
    must_not_infer:unique(current?[...(run.adoptedReport?.coverage.limitations??[]),...(run.adoptedReport?.mustNotInfer??[]),...missing]:run.draft?.limitations??missing)};
  const check=protocolAnswerSchema.safeParse(answer);
  const issues=[...(check.success?[]:check.error.issues.map(i=>`${i.path.join('.')}: ${i.message}`)),...gaps,...(!body?['无可交付模型结果']:[])];
  return {version:'financial-evidence-protocol-v14',answer,validation:{schemaValid:check.success,valid:check.success&&issues.length===0,issues},evidenceGaps:gaps};
}
export type ProtocolExport=ReturnType<typeof buildProtocolExport>;
