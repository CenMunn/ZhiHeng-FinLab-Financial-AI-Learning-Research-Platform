import {periodLabel,matchesPeriodCoordinate} from './period.ts';
import {positiveRequirements,matchesRequiredMetric,metricCoordinates,requestsCalculation,requestedSumTerms} from './intent.ts';
import {conversionExpression,calculationResultCoordinate} from './calculations.ts';
import type {Draft,Fact,reviewDraft} from './core.ts';
import {calculationGaps,taskResponse,type SourceContext} from './task-response.ts';
import {metricLabel} from './labels.ts';
type Review=ReturnType<typeof reviewDraft>;
const scopeName=(s:string)=>s==='consolidated'?'合并':'母公司/本银行';
// Development vocabulary, not a test-answer register. Unknown tasks stay pending.
const metricGroups=[
  ['资产总计','资产总额'],['负债合计','负债总额'],['所有者权益合计','所有者权益总额','股东权益合计'],
  ['流动资产合计'],['非流动资产合计'],['流动负债合计'],['非流动负债合计'],
  ['营业收入','营业收入合计'],['营业总收入'],['营业利润'],['利润总额'],['净利润'],
  ['归属于母公司股东的净利润','归属于母公司所有者的净利润','归母净利润'],
  ['经营活动产生的现金流量净额','经营活动现金流量净额','经营现金流量净额','经营现金流','经营性现金流'],
  ['投资活动产生的现金流量净额'],['筹资活动产生的现金流量净额'],['现金及现金等价物净增加额'],
  ['基本每股收益'],['稀释每股收益'],['货币资金'],['现金及现金等价物余额'],['少数股东损益'],
  ['其他应收款'],['应收股利'],['应收利息'],
];
function expression(c:Draft['calculations'][number],facts:Draft['facts']){
  const operands=c.operands.map(i=>facts[i]),names=operands.map(f=>`${periodLabel(f)}${scopeName(f.scope)}${f.label}`);
  switch(c.operation){
    case 'difference':return `${names[0]} − ${names[1]}`;
    case 'sum':return names.join(' + ');
    case 'ratio':return `${names[0]} / ${names[1]}${c.unit==='%'?' × 100%':''}`;
    case 'difference_ratio':return `(${names[0]} − ${names[1]}) / ${names[2]}${c.unit==='%'?' × 100%':''}`;
    case 'absolute_ratio':return `|${names[0]}| / ${names[1]}${c.unit==='%'?' × 100%':''}`;
    case 'average_denominator_ratio':return `${names[0]} / ((${names[1]} + ${names[2]}) / 2)${c.unit==='%'?' × 100%':''}`;
    case 'growth':return `(${names[0]} / ${names[1]} − 1)${c.unit==='%'?' × 100%':''}`;
    case 'unit_conversion':return `${names[0]}：${conversionExpression(operands[0].value,operands[0].unit,c.unit)} = ${c.value} ${c.unit}`;
    case 'percentage_point_change':return `(${names[0]} / ${names[1]} − ${names[2]} / ${names[3]}) × 100`;
  }
}
export function buildAdoptedReport(draft:Draft,review:Review,question:string,runId:string|null=null,context:SourceContext={}){
  const factChecks=new Set(review.checks.filter(c=>c.kind==='fact'&&c.ok).map(c=>c.index));
  const calculationChecks=new Set(review.checks.filter(c=>c.kind==='calculation'&&c.ok).map(c=>c.index));
  const indexMap=new Map<number,number>();
  const facts=draft.facts.flatMap((f,i)=>{
    if(!factChecks.has(i))return [];
    const source=review.factSources?.find(s=>s.originalIndex===i)?.source;
    indexMap.set(i,indexMap.size);
    return [{...f,year:source?.year??f.year,period:source?.period??f.period??String(f.year),periodAliases:source?.periodAliases??[],label:source?.label??f.label,currency:source?.currency??null,originalIndex:i,headerSourceIds:source?.headerSourceIds??[],statementId:source?.statementId??null,headerEvidence:source?.headerEvidence??[],tableTitle:source?.tableTitle??null,quote:source?.quote??null,...(source?.unitEvidence?{unitEvidence:source.unitEvidence}:{})}];
  });
  const excludedCalculations:{originalIndex:number;reason:string}[]=[];
  const verifiedCalculations=draft.calculations.flatMap((c,i)=>{
    if(!calculationChecks.has(i)||!c.operands.every(n=>indexMap.has(n)))return [];
    const check=review.checks.find(check=>check.kind==='calculation'&&check.index===i&&check.ok);
    const mapped={...c,value:check&&'normalizedValue' in check?String(check.normalizedValue??c.value):c.value,operands:c.operands.map(n=>indexMap.get(n)!)};
    return [{...mapped,label:expression(mapped,facts),originalIndex:i}];
  });
  const requiredQuestion=positiveRequirements(question);
  const years=[...new Set([...requiredQuestion.matchAll(/\b(20\d{2})\b/g)].map(m=>Number(m[1])))];
  // Extend the development vocabulary from actually parsed source row names,
  // not from unverified model labels. Unknown quoted requests stay required.
  const sourceGroups=(context.sourceFacts??[]).filter((f,i,a)=>a.findIndex(s=>metricLabel(s.label)===metricLabel(f.label))===i&&!metricGroups.some(g=>g.some(alias=>matchesRequiredMetric(f.label,[alias])))).map(f=>[...new Set([f.label,metricLabel(f.label)])]).filter(g=>/[\u4e00-\u9fff]/.test(g[0])&&g[0].length>=2);
  const formulaGroups=(requestedSumTerms(requiredQuestion)??[]).map(term=>[term]);
  const metrics:string[][]=[],vocabulary=[...metricGroups,...sourceGroups,...formulaGroups].flatMap(group=>group.map(alias=>({alias,group}))).sort((a,b)=>b.alias.length-a.alias.length);
  const masked=requiredQuestion.split('');
  for(let i=0;i<requiredQuestion.length;i++){
    const match=vocabulary.find(({alias})=>requiredQuestion.startsWith(alias,i));if(!match)continue;
    // Formula terms bind to verified calculation operands, not incidental
    // shorter row names embedded in shorthand such as 经营净现金流.
    if(!formulaGroups.includes(match.group)&&!metrics.includes(match.group))metrics.push(match.group);
    for(let j=i;j<i+match.alias.length;j++)masked[j]=' ';
    i+=match.alias.length-1;
  }
  const scopes:Fact['scope'][]=[],scopeText=masked.join('');
  if(/合并|本集团/.test(scopeText))scopes.push('consolidated');
  if(/母公司|本银行|本公司|本行/.test(scopeText))scopes.push('parent');
  for(const m of requiredQuestion.matchAll(/[“「]([^”」]{1,80})[”」]/g)){
    const prefix=requiredQuestion.slice(Math.max(0,(m.index??0)-20),m.index),formula=/[÷/+*=×]|除以|乘以/.test(m[1])||/[−－-]|减去/.test(m[1])&&/公式|计算|按照/.test(prefix);
    if(!/^(?:本行|本银行|本公司|本集团|母公司|合并)$/.test(m[1])&&!formula&&!metrics.some(a=>a.includes(m[1])))metrics.push([m[1]]);
  }
  if(/流动比率/.test(requiredQuestion))for(const name of ['流动资产合计','流动负债合计']){
    const group=metricGroups.find(g=>g.includes(name))!;if(!metrics.includes(group))metrics.push(group);
  }
  const unfulfilled=new Set(calculationGaps(requiredQuestion,facts,[],years,scopes,metrics));
  const calculations=verifiedCalculations.filter(c=>{
    const remaining=new Set(calculationGaps(requiredQuestion,facts,[c],years,scopes,metrics));
    if([...unfulfilled].some(gap=>!remaining.has(gap)))return true;
    excludedCalculations.push({originalIndex:c.originalIndex,reason:requestsCalculation(question,c.operation)?'request_operands_or_formula_unconfirmed':'not_requested'});
    return false;
  });
  const missing:string[]=[],present:string[]=[];
  for(const aliases of metrics){
    const selected=facts.filter(f=>matchesRequiredMetric(f.label,aliases));
    for(const {year,scope,period} of metricCoordinates(requiredQuestion,aliases,metrics,years,scopes)){
      const key=`${period??`${year??'所问年度'}年`}${scope?scopeName(scope):'所问范围'}${aliases[0]}`;
      const computed=calculations.some(c=>{const f=calculationResultCoordinate(c,facts);return f&&matchesRequiredMetric(f.label,aliases)&&matchesPeriodCoordinate(f,year,period)&&(scope===null||f.scope===scope);});
      (computed||selected.some(f=>matchesPeriodCoordinate(f,year,period)&&(scope===null||f.scope===scope))?present:missing).push(key);
    }
  }
  missing.push(...calculationGaps(requiredQuestion,facts,calculations,years,scopes,metrics));
  if(/币种/.test(question)&&facts.some(f=>!f.currency))missing.push('所问币种未从对应表头证实');
  if(facts.length===0&&calculations.length===0)missing.push('本次未形成可采用的结构化证据；请核对资料、解析缺口及模型输出');
  const limitations=[
    '只采用来源匹配的结构化事实和复算通过的计算，不采用模型自由文字或模型自述限制作为研究结论。',
    '覆盖检查仅识别有限指标词、明确年度和范围及计算要求；多条件题、定义、分类、推断、否定和证据边界仍须人工逐项审核。',
    '数值核验不能证明指标、公式选择和整项任务语义正确；当前未提供投资结论。',
  ];
  const response=taskResponse(question,facts,calculations,metrics,years,scopes,context);
  missing.push(...response.boundaryMissing);
  return {
    version:'facts-calculations-v2' as const,runId,facts,calculations,
    ...response,
    conclusions:facts.map(f=>`${periodLabel(f)}${scopeName(f.scope)}${f.label}：${f.value} ${f.unit}。`),
    coverage:{status:missing.length?'incomplete' as const:'needs_semantic_review' as const,present,missing,limitations},
    answerVerified:false as const,semanticReview:'pending' as const,
    audit:{originalDraftInJson:true,rawProseAdopted:false,refusalFlag:draft.refused,rejected:review.checks.filter(c=>!c.ok).map(c=>({...c})),excludedCalculations,excludedProseFields:['answer','limitations','calculations.label']},
  };
}
export type AdoptedReport=ReturnType<typeof buildAdoptedReport>;
