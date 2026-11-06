// Remove explicit prohibitions only for positive requirement extraction.
// Keep the original question in model input, reports and inference checks.
export function positiveRequirements(question:string){
  return question.replace(/差額/g,'差额').replace(/[？?！!]/g,'。')
    .replace(/[（(](?:净)?(?:亏损|损失|减少|收益)(?:总额)?以[“"‘']?[－\-−][”"’']?号填列[）)]/g,'')
    .replace(/保留负号\s*(?:[“"‘']?[－\-−][”"’']?|[（(][－\-−][）)])/g,'')
    .replace(/计算(?:使用|采用)未提前舍入的(?:Decimal|十进制)?操作数[，,]仅最终结果(?:ROUND_HALF_UP|四舍五入)保留(?:\d+|[两二四])位[；;](?:须|应)?列指定公式及各操作数[。.]?/g,'')
    // A report's comparative-column provenance is not another requested year.
    .replace(/[（(]20\d{2}(?:年)?(?:报告(?:表内)?|表内)比较列[）)]/g,'')
    .replace(/每个计算操作数/g,'每个操作数')
    .replace(/计算(?=仅用题定公式)/g,'')
    // Documentation of a calculation, if any, is not itself a request to
    // create a new calculation and must not replace an earlier real task.
    .replace(/(?:如有|若有|如涉及)?计算(?:时)?[，,]?\s*(?:请|须|应)?(?:列出|列明|列|注明|给出|说明|展示)(?:唯一指定)?公式(?:及|与|和|、)操作数(?:与最终舍入)?/g,'')
    .replace(/(?:^|[，,；;。\n])\s*(?:请)?(?:不要|不得|不将|不用|不取|不加|不改用|不使用|不根据|不以|不把|不替换为|不借用|不是|勿用|勿替换|不能用)[^，,；;。\n]*/g,'。')
    .replace(/(?:^|[，,；;。\n])\s*(?:请)?(?:无需|不需|不必)计算[^，,；;。\n]*/g,'。')
    .replace(/(?:^|[，,；;。\n])\s*(?:请)?不计算[^，,；;。\n]*/g,'。')
    .replace(/(?:^|[，,；;。\n])\s*(?:本题)?不(?:排除|剔除)[^，,；;。\n]*/g,'。')
    .replace(/((?:分母|总额|合计|口径)(?:中)?)(?:包含|包括|含)少数股东(?:损益|权益)/g,'$1')
    .replace(/(?:^|[，,；;。\n])\s*(?:包含|包括|含)少数股东(?:损益|权益)(?=$|[，,；;。\n])/g,'。')
    .replace(/20\d{2}年(?:年度报告|报)/g,'年报')
    // Explicit "under / including" qualifiers ask for the leaf row; a
    // conjunction (父项和子项) still requires both amounts.
    .replace(/其他应收款(?:项下|下)(?:的)?(?:其中[：:]?)?\s*(?=应收股利|应收利息)/g,'')
    .replace(/(20\d{2})年末/g,'$1年12月31日')
    .replace(/基本(?:及|和|与|、)稀释每股收益/g,'基本每股收益和稀释每股收益');
}

// An arithmetic check alone is not a request to publish that calculation.
// This bounded operation gate never reads a model's free-form label/prose.
export function requestsCalculation(question:string,operation:string){
 const q=positiveRequirements(question);
 switch(operation){
  case 'growth':return /同比|增长率|增速/.test(q);
  case 'difference':return /差额|相减|减去|增减金额|变动金额/.test(q);
  case 'unit_conversion':return /换算|转换为/.test(q);
  case 'percentage_point_change':return /百分点/.test(q);
  case 'absolute_ratio':return /绝对值/.test(q)&&/比值|占|[÷/]|除以/.test(q);
  case 'average_denominator_ratio':return /简化资产收益率|平均.*分母|平均资产/.test(q);
  case 'difference_ratio':return /毛利率|速动比率/.test(q);
  case 'ratio':return /资产负债率|流动比率|净利率|研发费用率|比值|占比|占.*比例|[÷/]|除以/.test(q)&&!/仅.*百分点/.test(q);
  case 'sum':return /之和|求和|相加|加总|[+＋]|计算[^。；;]{0,40}(?:金额合计|合计金额)/.test(q);
  default:return false;
 }
}

import {metricLabel} from './labels.ts';
import {requestedPeriods} from './period.ts';
import type {Fact} from './core.ts';
import {cashRole} from './calculations.ts';
const clean=(s:string)=>metricLabel(s.replace(/[（(](?:人民币)?元(?:\/股)?[）)]$/,''));
// A verified joint row can cover either EPS request. This is deliberately
// one-way: a basic-only row is never evidence for diluted earnings.
export function matchesRequiredMetric(name:string,aliases:string[]){
 const value=clean(name);
 return aliases.some(a=>value===clean(a)||/^(?:期末|年末)现金及现金等价物余额$/.test(value)&&clean(a)==='现金及现金等价物余额'||/^基本(?:每股收益)?(?:及|和|与|、)稀释每股收益$/.test(value)&&['基本每股收益','稀释每股收益'].includes(clean(a)));
}
// Only a literal flat addition formula is resolved here. Other expressions
// retain the dedicated operation rules or an explicit unsupported gap.
export function requestedSumTerms(question:string){
 const rhs=question.match(/(?:指定|唯一)公式(?:为|[=＝:：])\s*([^，,。；;]+)/)?.[1]?.trim();
 if(!rhs||/[÷/×*()（）−-]/.test(rhs))return null;
 const terms=rhs.split(/[+＋]/).map(t=>t.trim());
 return terms.length>=2&&terms.length<=8&&terms.every(t=>/^[\u4e00-\u9fff]+$/.test(t))?terms:null;
}
export function matchesFormulaTerm(label:string,term:string,groups:string[][]){
 const role=cashRole(term);if(role)return cashRole(label)===role;
 const group=groups.find(g=>g.some(s=>clean(s)===clean(term)));
 return matchesRequiredMetric(label,group??[term]);
}

type Coordinate={year:number|null;scope:Fact['scope']|null;period:string|null};
// Bind explicit qualifiers to the following metrics, retaining a shared
// prefix until another explicit year/date/scope replaces it. Metric names
// themselves are never scanned as scope qualifiers (e.g. 归属于母公司...).
export function metricCoordinates(question:string,aliases:string[],metrics:string[][],years:number[],scopes:Fact['scope'][]):Coordinate[]{
 // Implicit operands follow each formula mention's qualifiers. Without this,
 // two locally scoped ratios produce a false Cartesian product of requests.
 if(aliases.some(a=>['流动资产合计','流动负债合计'].includes(a))&&!aliases.some(a=>question.includes(a))&&question.includes('流动比率')){
  const formula=['流动比率'];
  return metricCoordinates(question,formula,[...metrics,formula],years,scopes);
 }
 const vocabulary=metrics.flatMap(group=>group.map(alias=>({alias,group}))).sort((a,b)=>b.alias.length-a.alias.length);
 const mentions:{start:number;end:number;group:string[]}[]=[];
 for(let i=0;i<question.length;i++){
  const found=vocabulary.find(v=>question.startsWith(v.alias,i));if(!found)continue;
  mentions.push({start:i,end:i+found.alias.length,group:found.group});i+=found.alias.length-1;
 }
 let activeYears=years,activeScopes=scopes,periodText=question,previousEnd=0;
 const result:Coordinate[]=[];
 for(const mention of mentions){
  const prefix=question.slice(previousEnd,mention.start),localYears=[...new Set([...prefix.matchAll(/20\d{2}/g)].map(m=>Number(m[0])))];
  const localScopes:Fact['scope'][]=[];
  if(/合并|本集团/.test(prefix))localScopes.push('consolidated');
  if(/母公司|本银行|本公司|本行/.test(prefix))localScopes.push('parent');
  if(localYears.length){activeYears=localYears;periodText=prefix;}
  if(localScopes.length)activeScopes=localScopes;
  if(mention.group===aliases||mention.group.some(a=>aliases.includes(a))){
   for(const year of activeYears.length?activeYears:[null])for(const scope of activeScopes.length?activeScopes:[null])for(const period of requestedPeriods(periodText,year))result.push({year,scope,period});
  }
  previousEnd=mention.end;
 }
 if(!result.length)for(const year of years.length?years:[null])for(const scope of scopes.length?scopes:[null])for(const period of requestedPeriods(question,year))result.push({year,scope,period});
 return result.filter((v,i,a)=>a.findIndex(x=>x.year===v.year&&x.scope===v.scope&&x.period===v.period)===i);
}

// Presentation only: select by the user's explicit metric/column coordinates.
// Values are never filled from source facts or recomputed here. All original
// facts remain in the export and the raw candidate remains in the run.
export function questionFacts<T extends Pick<Fact,'label'|'year'|'scope'|'period'|'periodAliases'>>(question:string,facts:T[]):T[]{
 const q=positiveRequirements(question),groups=facts.filter((f,i,a)=>a.findIndex(s=>clean(s.label)===clean(f.label))===i).map(f=>[...new Set([f.label,clean(f.label)])]);
 const vocabulary=groups.flat().sort((a,b)=>b.length-a.length),metrics:string[][]=[];
 let scopeText=q;
 for(let i=0;i<q.length;i++){
  const name=vocabulary.find(s=>q.startsWith(s,i));if(!name)continue;
  const group=groups.find(g=>g.includes(name))!;if(!metrics.includes(group))metrics.push(group);
  scopeText=scopeText.replaceAll(name,' ');i+=name.length-1;
 }
 if(!metrics.length)return facts;
 const years=[...new Set([...q.matchAll(/20\d{2}/g)].map(m=>Number(m[0])))],scopes:Fact['scope'][]=[];
 if(/合并|本集团/.test(scopeText))scopes.push('consolidated');
 if(/母公司|本银行|本公司|本行/.test(scopeText))scopes.push('parent');
 return facts.filter(f=>metrics.some(g=>matchesRequiredMetric(f.label,g)&&metricCoordinates(q,g,metrics,years,scopes).some(c=>
  (c.year===null||f.year===c.year)&&(c.scope===null||f.scope===c.scope)&&(c.period===null||f.period===c.period||f.periodAliases?.includes(c.period)))));
}
