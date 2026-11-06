import {positiveRequirements,matchesRequiredMetric,metricCoordinates,requestedSumTerms,matchesFormulaTerm} from './intent.ts';
import {periodLabel,requestedPeriods,matchesPeriodCoordinate} from './period.ts';
import type {Draft,Fact} from './core.ts';
import {nonNumericEpsCells,type SourceBlock,type NonNumericEvidence} from './source-state.ts';
import {metricLabel} from './labels.ts';
import {compareFinancialAmounts,calculationResultCoordinate,cashRollForwardPeriod} from './calculations.ts';
export type SourceContext={sourceFacts?:Fact[];statementBlocks?:SourceBlock[]};
const scopeName=(s:Fact['scope'])=>s==='consolidated'?'合并':'母公司/本银行';
const label=(s:string)=>metricLabel(s.replace(/[（(](?:人民币)?元(?:\/股)?[）)]$/,''));
const matches=(f:Pick<Fact,'label'>,aliases:string[])=>matchesRequiredMetric(f.label,aliases);
const family=(s:string)=>/现金流|现金(?:及现金)?等价物(?:净增加|余额)/.test(s)?'现金流量表':/待摊费用|合同取得成本|合同履约成本|应付利息|(?:资产|负债|权益)(?:合计|总额|净额|余额)?$/.test(s)?'资产负债表':/利润|收入|每股收益|成本|费用|利息支出|收益|损失/.test(s)?'利润表':/资产|负债|权益|货币资金|现金|贷款|垫款|存货|股权投资|存款|借款|股本|资本公积|盈余公积/.test(s)?'资产负债表':null;
type DeliveredFact=Draft['facts'][number]&{periodAliases?:string[];currency?:string|null};
export function calculationGaps(question:string,facts:DeliveredFact[],calculations:Draft['calculations'],years:number[],scopes:Fact['scope'][],metrics:string[][]){
  if(!/计算|复算|指定公式|唯一公式|同比|增长率|增速|百分点|资产负债率|流动比率|速动比率|毛利率|研发费用率|简化资产收益率|净利率|换算|相减|差额/.test(question))return [];
  const calculationStarts=[...question.matchAll(/计算/g)].map(m=>m.index!);
  if(calculationStarts.length>1)return calculationStarts.flatMap((start,i)=>calculationGaps(question.slice(start,calculationStarts[i+1]),facts,calculations,years,scopes,metrics));
  // An explicit antecedent (“计算其...”) inherits preceding operands. An
  // independently named calculation keeps its own clause: facts listed
  // earlier must not silently acquire that calculation's task or years.
  const start=calculationStarts[0],tail=start===undefined?question:question.slice(start);
  let clause=/^计算(?:其|该|上述)/.test(tail)?question:tail;
  // A unique explicitly named antecedent can be converted by "并计算换算".
  // Multiple candidate metrics remain ambiguous rather than inheriting all.
  if(/换算/.test(clause)&&metrics.length===1&&!metrics[0].some(a=>clause.includes(a)))clause=question;
  if(/同比|增长率|增速/.test(clause)&&/差额|相减|增减金额|变动金额/.test(clause))return [
    ...calculationGaps(clause.replace(/差额|相减|增减金额|变动金额/g,''),facts,calculations,years,scopes,metrics),
    ...calculationGaps(clause.replace(/同比|增长率|增速/g,''),facts,calculations,years,scopes,metrics),
  ];
  const localMetrics=metrics.filter(g=>g.some(a=>clause.includes(a)));
  const scopeText=localMetrics.flat().sort((a,b)=>b.length-a.length).reduce((s,a)=>s.replaceAll(a,' '),clause);
  const localScopes:Fact['scope'][]=[];
  if(/合并|本集团/.test(scopeText))localScopes.push('consolidated');
  if(/母公司|本银行|本公司|本行/.test(scopeText))localScopes.push('parent');
  const clauseScopes=localScopes.length?localScopes:scopes;
  const explicit=[...clause.matchAll(/20\d{2}/g)].map(m=>Number(m[0]));
  const requestedYears=explicit.length?[...new Set(explicit)]:years.length?[Math.max(...years)]:[null];
  const requestedScopes=clauseScopes.length?clauseScopes:[null];
  const missing:string[]=[];
  const ratios:{name:string;num:string[];den:string[];unit:string;op?:'difference_ratio'|'absolute_ratio'|'average_denominator_ratio';subtract?:string[]}[]=[];
  if(/资产负债率/.test(clause))ratios.push({name:'资产负债率',num:['负债合计','负债总额'],den:['资产总计','资产总额'],unit:'%'});
  if(/流动比率/.test(clause))ratios.push({name:'流动比率',num:['流动资产合计'],den:['流动负债合计'],unit:/百分比|%/.test(clause)?'%':'倍'});
  if(/净利率/.test(clause))ratios.push({name:'净利率',num:['净利润'],den:['营业收入','营业收入合计'],unit:'%'});
  if(/研发费用率/.test(clause))ratios.push({name:'研发费用率',num:['研发费用'],den:['营业收入','营业收入合计'],unit:'%'});
  if(/毛利率/.test(clause))ratios.push({name:'毛利率',num:['营业收入','营业收入合计'],subtract:['营业成本'],den:['营业收入','营业收入合计'],unit:'%',op:'difference_ratio'});
  if(/速动比率/.test(clause)&&/流动资产合计.*存货.*流动负债合计/.test(clause))ratios.push({name:'速动比率',num:['流动资产合计'],subtract:['存货'],den:['流动负债合计'],unit:/百分比|%/.test(clause)?'%':'倍',op:'difference_ratio'});
  if(/利息支出绝对值.*利息收入/.test(clause))ratios.push({name:'利息支出绝对值占利息收入',num:['利息支出'],den:['利息收入'],unit:'%',op:'absolute_ratio'});
  if(/简化资产收益率/.test(clause)&&/净利润.*资产总计/.test(clause)&&/[÷/]\s*2/.test(clause))ratios.push({name:'简化资产收益率',num:['净利润'],den:['资产总计','资产总额'],unit:'%',op:'average_denominator_ratio'});
  if(/发放贷款和垫款\s*[÷/]\s*吸收存款/.test(clause))ratios.push({name:'发放贷款和垫款÷吸收存款',num:['发放贷款和垫款'],den:['吸收存款'],unit:'%'});
  if(/经营.*(?:现金流|现金流量净额).*(?:除以|÷|\/|比值).*净利润/.test(clause))ratios.push({name:'经营现金流与净利润比值',num:['经营现金流','经营现金流量净额','经营活动现金流量净额','经营活动产生的现金流量净额'],den:['净利润'],unit:/倍/.test(clause)?'倍':'%'});
  const formulaText=clause.match(/(?:指定|唯一)公式(?:为|[=＝:：])\s*([^，,。；;]+)/)?.[1]??'';
  const literalRatio=formulaText.match(/^([\u4e00-\u9fff]+)\s*[÷/]\s*([\u4e00-\u9fff]+)(?:\s*[×*]\s*100\s*%)?$/);
  if(literalRatio&&!ratios.length)ratios.push({name:'题定比率',num:[literalRatio[1]],den:[literalRatio[2]],unit:/%/.test(formulaText)||/输出\s*%/.test(clause)?'%':'倍'});
  const percentageChange=/百分点/.test(clause);
  const standaloneRatios=percentageChange?ratios.filter(r=>clause.split(/以及|并|及|和|、|[，。；;]/).some(part=>(part.includes(r.name)||r.name.includes('比值')&&/经营.*现金流.*比值/.test(part))&&!/百分点|变化|差|增减/.test(part))):ratios;
  for(const r of standaloneRatios)for(const {year,scope,period} of metricCoordinates(clause,[r.name],[...localMetrics,...ratios.map(r=>[r.name])],requestedYears.filter((y):y is number=>y!==null),clauseScopes)){
    const found=calculations.some(c=>{
      const [a,b,x]=c.operands.map(i=>facts[i]);if(c.operation!==(r.op??'ratio')||c.unit!==r.unit||!a||!b||!matches(a,r.num))return false;
      if(r.op==='average_denominator_ratio')return !!x&&matches(b,r.den)&&matches(x,r.den)&&(year===null||a.year===year&&b.year===year-1&&x.year===year)&&(scope===null||[a,b,x].every(f=>f.scope===scope));
      const inputs=r.op==='difference_ratio'?[a,b,x]:[a,b];
      if(r.op==='difference_ratio'? !x||!matches(b,r.subtract??[])||!matches(x,r.den):!matches(b,r.den))return false;
      return inputs.every(f=>!!f&&matchesPeriodCoordinate(f,year,period)&&(scope===null||f.scope===scope));
    });
    if(!found)missing.push(`${period??`${year??'所问年度'}年`}${scope?scopeName(scope):'所问范围'}${r.name}计算未交付`);
  }
  // The operation and operands must match the requested metric; a valid but
  // unrelated calculation cannot stand in for an absent requested result.
  const literalDifference=/^[\u4e00-\u9fff]+\s*[-−]\s*[\u4e00-\u9fff]+$/.test(formulaText);
  const operation=percentageChange?'percentage_point_change':/同比|增长率|增速/.test(clause)?'growth':/换算/.test(clause)?'unit_conversion':/相减|差额|减去|增减金额|变动金额|变动额/.test(clause)||literalDifference?'difference':/之和|求和|相加|加总|净合计/.test(clause)||requestedSumTerms(clause)?'sum':null;
  const targetUnit=operation==='unit_conversion'?clause.match(/换算(?:为|成|至|到)?\s*(?:人民币)?(百万元|千元|万元|亿元|元)(?!\/股)/)?.[1]:null;
  const formulaYears=[...new Set([...formulaText.matchAll(/20\d{2}/g)].map(m=>Number(m[0])))];
  const orderedYears=operation==='difference'&&formulaYears.length===2?formulaYears:explicit.length?[...new Set(explicit)]:[...years].sort((a,b)=>b-a);
  const newYear=orderedYears[0]??null;
  const oldYear=orderedYears[1]??(operation==='growth'&&newYear!==null?newYear-1:null);
  const requiredDates=requestedPeriods(clause,null).filter((p):p is string=>p!==null);
  const dateOperandsMatch=(c:Draft['calculations'][number])=>requiredDates.every(period=>c.operands.some(i=>facts[i]&&matchesPeriodCoordinate(facts[i],null,period)));
  const scopeMatches=(c:Draft['calculations'][number],scope:Fact['scope']|null)=>c.operands.every(i=>facts[i]&&(scope===null||facts[i].scope===scope));
  if(operation==='percentage_point_change'){
    if(!ratios.length)missing.push('百分点变化的分子/分母定义尚未自动确认，计算需人工核对');
    for(const r of ratios)for(const scope of requestedScopes){
      const found=calculations.some(c=>{const [a,b,x,y]=c.operands.map(i=>facts[i]);return c.operation===operation&&dateOperandsMatch(c)&&scopeMatches(c,scope)&&!!a&&!!b&&!!x&&!!y&&matches(a,r.num)&&matches(b,r.den)&&matches(x,r.num)&&matches(y,r.den)&&(newYear===null||a.year===newYear&&b.year===newYear)&&(oldYear===null||x.year===oldYear&&y.year===oldYear);});
      if(!found)missing.push(`${scope?scopeName(scope):'所问范围'}${r.name}所问年度与有序分子/分母的百分点计算未交付`);
    }
  }else if(operation==='sum'&&requestedSumTerms(clause)){
    const terms=requestedSumTerms(clause)!;
    const outputUnit=clause.match(/输出\s*(?:人民币)?(百万元|千元|万元|亿元|元)(?!\/股)/)?.[1];
    for(const scope of requestedScopes){
      const found=calculations.some(c=>{
        if(c.operation!=='sum'||c.operands.length!==terms.length||!scopeMatches(c,scope)||outputUnit&&c.unit!==outputUnit)return false;
        const closing=cashRollForwardPeriod(c,facts);
        if(requiredDates.length&&(closing?!requiredDates.every(p=>p===closing||c.operands.some(i=>facts[i]?.period===p)):!c.operands.every(i=>facts[i]&&requiredDates.some(p=>matchesPeriodCoordinate(facts[i],null,p)))))return false;
        return c.operands.every((i,j)=>{const f=facts[i];return !!f&&matchesFormulaTerm(f.label,terms[j],metrics)&&(newYear===null||f.year===newYear);});
      });
      if(!found)missing.push(`${scope?scopeName(scope):'所问范围'}sum的题定有序操作数计算未交付或定义尚未自动确认`);
    }
  }else if(operation==='sum'||operation==='difference'&&localMetrics.length>1){
    const orderedMetrics=[...localMetrics].sort((a,b)=>Math.min(...a.map(s=>clause.indexOf(s)).filter(i=>i>=0))-Math.min(...b.map(s=>clause.indexOf(s)).filter(i=>i>=0)));
    const requiredCount=operation==='difference'?2:orderedMetrics.length;
    const coordinates=orderedMetrics.map(g=>metricCoordinates(clause,g,localMetrics,requestedYears.filter((y):y is number=>y!==null),clauseScopes));
    for(const scope of requestedScopes){
      const found=orderedMetrics.length===requiredCount&&requiredCount>=2&&calculations.some(c=>c.operation===operation&&c.operands.length===requiredCount&&scopeMatches(c,scope)&&dateOperandsMatch(c)&&c.operands.every((i,j)=>{
        const f=facts[i];return !!f&&matches(f,orderedMetrics[j])&&coordinates[j].some(v=>matchesPeriodCoordinate(f,v.year,v.period)&&(v.scope===null||f.scope===v.scope));
      }));
      if(!found)missing.push(`${scope?scopeName(scope):'所问范围'}${operation}的题定有序操作数计算未交付或定义尚未自动确认`);
    }
  }else if(operation)for(const aliases of localMetrics){
    const coordinates=metricCoordinates(clause,aliases,localMetrics,requestedYears.filter((y):y is number=>y!==null),clauseScopes);
    const each=/各自|分别|逐年/.test(clause);
    const targets=operation==='unit_conversion'||each?coordinates:coordinates.filter(v=>v.year===Math.max(...coordinates.filter(c=>c.scope===v.scope).map(c=>c.year??0)));
    for(const {scope,year:requestedYear,period:requestedPeriod} of targets){
    const comparisonYears=[...new Set(coordinates.filter(c=>c.scope===scope&&c.year!==requestedYear).map(c=>c.year).filter((y):y is number=>y!==null))];
    const comparisonYear=operation==='growth'?(each||comparisonYears.length===0?requestedYear===null?null:requestedYear-1:comparisonYears.length===1?comparisonYears[0]:NaN):oldYear;
    const found=calculations.some(c=>{const [a,b]=c.operands.map(i=>facts[i]);
      if(c.operation!==operation||!scopeMatches(c,scope)||!a||!matches(a,aliases)||!matchesPeriodCoordinate(a,requestedYear,requestedPeriod))return false;
      if(operation==='unit_conversion')return !!targetUnit&&c.unit===targetUnit;
      if(!dateOperandsMatch(c))return false;
      if(!b)return false;
      if(operation==='growth')return matches(b,aliases)&&(comparisonYear===null||b.year===comparisonYear);
      return matches(b,aliases)&&(oldYear===null?b.year===a.year:b.year===oldYear);
    });
    if(!found)missing.push(`${requestedPeriod??`${requestedYear??'所问年度'}年`}${scope?scopeName(scope):'所问范围'}${aliases[0]}所问${operation}计算未交付`);
    }
  }
  if(!ratios.length&&!operation)missing.push('具体计算公式尚未自动确认，未形成所问计算的核验结果，需人工核对');
  if(operation&&!localMetrics.length&&!ratios.length&&!(operation==='sum'&&requestedSumTerms(clause)))missing.push('计算指标尚未自动确认，需人工核对');
  if(operation==='unit_conversion'&&!targetUnit)missing.push('换算目标单位尚未自动确认，需人工核对');
  return missing;
}
export function taskResponse(question:string,facts:DeliveredFact[],calculations:Draft['calculations'],metrics:string[][],years:number[],scopes:Fact['scope'][],context:SourceContext){
  const requiredQuestion=positiveRequirements(question);
  const answerLines:string[]=[],sourceAssessment:{metric:string;state:string;pages:number[]}[]=[];
  const boundaryEvidence:NonNumericEvidence[]=[],boundaryMissing:string[]=[],mustNotInfer:string[]=[];
  for(const aliases of metrics){
    for(const {year,scope,period} of metricCoordinates(requiredQuestion,aliases,metrics,years,scopes)){
      const wanted=(f:Pick<Fact,'label'|'year'|'scope'|'period'|'periodAliases'>)=>matches(f,aliases)&&matchesPeriodCoordinate(f,year,period)&&(scope===null||f.scope===scope);
      const delivered=facts.filter(wanted),key=`${period??`${year??'所问年度'}年`}${scope?scopeName(scope):'所问范围'}${aliases[0]}`;
      if(delivered.length){for(const f of delivered){
        const alias=period&&period!==f.period&&f.periodAliases?.includes(period)?`（题问${period}对应本表期初比较列，规范展示为${f.period}）`:'';
        answerLines.push(`${periodLabel(f)}${alias}${scopeName(f.scope)}${f.label}为${f.value} ${f.unit}；币种${f.currency??'来源未明示'}。`);
      }continue;}
      const derived=calculations.flatMap(c=>{const coordinate=calculationResultCoordinate(c,facts);return coordinate&&matches(coordinate,aliases)&&matchesPeriodCoordinate(coordinate,year,period)&&(scope===null||coordinate.scope===scope)?[{c,coordinate}]:[];});
      if(derived.length){for(const {c,coordinate} of derived)answerLines.push(`${coordinate.period}${scopeName(coordinate.scope)}${coordinate.label}按题定公式及已核验操作数复算为${c.value} ${c.unit}；此项为计算结果，不冒称原表直接抄录。`);continue;}
      const source=context.sourceFacts?.filter(wanted)??[],table=family(aliases[0]),blocks=context.statementBlocks?.filter(b=>table&&(b.name.endsWith(table)||table==='利润表'&&b.name.endsWith('损益表')))??[];
      const cells=nonNumericEpsCells(blocks).filter(wanted);
      if(source.length){answerLines.push(`原页已识别到${key}，但本次模型或核验未交付可采用的该项回答，不能说资料中没有。`);sourceAssessment.push({metric:key,state:'source_present_delivery_gap',pages:[...new Set(source.map(f=>f.page))]});}
      else if(cells.length===1){
        const cell=cells[0],constraint='横杠或空白不能当作0，不能用本集团或其他范围数值替代；请补充所问范围每股收益的明确数值披露及计算口径，原页含义仍须人工确认。';
        answerLines.push(`${key}在${cell.tableTitle}（物理页${cell.page}）对应列为${cell.state==='dash'?'横杠':'空白'}，未提供可读取的数值。${constraint}`);
        boundaryEvidence.push(cell);mustNotInfer.push(constraint);
        sourceAssessment.push({metric:key,state:'source_cell_non_numeric',pages:[cell.page]});
      }
      else if(scope!==null&&blocks.length&&blocks.every(b=>b.status==='parsed'&&!!b.columns?.length)&&blocks.every(b=>b.columns!.every(c=>c.scope!==scope))){
        answerLines.push(`本次已解析${table}（物理页${blocks.map(b=>b.page).join('、')}）未列示所问${scopeName(scope)}范围，不能读取可靠的${key}。请补充该范围的${table}及表头原页；不能用另一范围金额替代。`);
        sourceAssessment.push({metric:key,state:'requested_scope_not_in_resolved_columns',pages:blocks.map(b=>b.page)});
      }
      else if((period!==null||year!==null)&&blocks.length&&blocks.every(b=>b.status==='parsed'&&!!b.columns?.length)&&blocks.every(b=>b.columns!.every(c=>(scope!==null&&c.scope!==scope)||!matchesPeriodCoordinate(c,year,period)))){
        const available=[...new Set(blocks.flatMap(b=>b.columns!.filter(c=>scope===null||c.scope===scope).map(c=>c.period??String(c.year))))];
        answerLines.push(`本次已解析${table}列示时点/期间为${available.join('、')||'其他报表范围'}，没有${period??`${year}年度`}对应列，无法从这些列直接读取${key}。请补充该时点或期间、对应范围的${table}及完整表头；不能用同年其他时点替代。`);
        sourceAssessment.push({metric:key,state:'requested_period_not_in_resolved_columns',pages:blocks.map(b=>b.page)});
      }
      else if(blocks.length){answerLines.push(`原页已出现${table}（物理页${[...new Set(blocks.map(b=>b.page))].join('、')}），${key}仍有解析、行名或模型交付缺口，不能断言该表未提供。`);sourceAssessment.push({metric:key,state:'table_present_unresolved_amount',pages:blocks.map(b=>b.page)});}
      else if(context.statementBlocks?.length&&table){answerLines.push(`本次已识别${[...new Set(context.statementBlocks.map(b=>b.name))].join('、')}，未识别所问${table}，无法给出可靠的${key}；请补充目标表及表头原页，不能用其他报表金额推测。`);sourceAssessment.push({metric:key,state:'target_table_not_identified',pages:[]});}
      else{answerLines.push(`${key}尚无可采用证据；来源状态不足，无法区分资料缺失与解析、模型遗漏，请核对原页。`);sourceAssessment.push({metric:key,state:'source_state_unknown',pages:[]});}
    }
  }
  for(const c of calculations){
    const operands=c.operands.map(i=>facts[i]);
    if(['growth','difference'].includes(c.operation)&&operands.length===2&&label(operands[0].label)===label(operands[1].label)&&(operands[0].period??String(operands[0].year))>(operands[1].period??String(operands[1].year))){
      const direction=compareFinancialAmounts(operands[0].value,operands[1].value);
      answerLines.push(`${scopeName(operands[0].scope)}${operands[0].label}：${periodLabel(operands[0])}相对${periodLabel(operands[1])}${direction<0?'减少（下降）':direction>0?'增加（上升）':'金额持平'}；已核验计算结果为${c.value} ${c.unit}。增减方向取自原金额，不以舍入后的零值判断持平。`);
    }
  }
  if(/原因|为何|为什么|因果|是否由|造成|导致/.test(question))answerLines.push('财务报表原页可以支持对应金额、年度/时点、单位、报表范围的核对和同口径数值计算；本报告仅将通过核验的项目列为已交付结果。金额及变化不能单独确定经营原因，本次未核验管理层解释或因果依据，具体原因需补充对应原文及人工分析。');
  if(/净利润/.test(question)&&/归母|归属于母公司/.test(question)&&/必然|相同|不同|一致|比较/.test(question))answerLines.push('净利润与归母净利润应逐期核对报表及少数股东损益；不能仅凭指标名称断言金额必然相同或不同。');
  if(/保证|必然|一定|确保/.test(question)&&/未来|预测|增长/.test(question))answerLines.push('已披露财务主表只能证明对应历史期间的已核验事实，不能保证未来收入、利润或股价一定增长；未来结果需要另行取得预测依据，仍存在不确定性。');
  if(/资不抵债/.test(question)&&/现金流/.test(question))answerLines.push('某一类现金流量净额为负不能单独证明资不抵债。偿债与资产负债判断需核对同一时点、同一范围的资产、负债及相关附注，不能把期间现金收支净额直接当作资产负债余额。');
  if(/营业支出/.test(question)&&/营业成本|毛利率/.test(question))answerLines.push('银行营业支出与制造企业营业成本的组成和口径不同，不能直接替换并把自行套算结果称为披露毛利率；须取得适用的指标定义及可比成本证据。');
  if(/货币资金/.test(question)&&/现金及现金等价物/.test(question)&&/替代|等同|相等|相同|一致|口径|边界|精确金额/.test(question)){
    answerLines.push('货币资金与现金及现金等价物余额分属资产负债表和现金流量表口径，不能直接互相替代；不能仅凭货币资金确定现金及现金等价物的精确金额；须核对同一时点、同一范围现金流量表的期末现金及现金等价物余额，以及现金等价物及受限资金附注。具体差异原因不能仅凭主表推断。');
    for(const a of facts.filter(f=>matches(f,['货币资金'])))for(const b of facts.filter(f=>matches(f,['现金及现金等价物余额'])&&f.scope===a.scope&&f.period===a.period&&f.unit===a.unit))answerLines.push(`${periodLabel(a)}${scopeName(a.scope)}这两项已核验金额${compareFinancialAmounts(a.value,b.value)===0?'相等，但金额相等不证明口径相同':'不相等'}。`);
  }
  if(/金融投资|交易性金融资产/.test(question)&&/收益率|投资回报/.test(question))answerLines.push('金融资产余额是特定时点的账面金额，不能单凭余额确定已实现收益率；需对应期间的已实现收益、适用的平均投资余额或约定分母，并核对公允价值变动与收益确认口径。这里不将账面余额当作收益，也不补造未核验的收益数值。');
  if(/未分配利润|留存收益/.test(question)&&/净利润/.test(question)&&/差额|变动|增长|倒推|推算|代替|当作/.test(question))answerLines.push('未分配利润或留存收益的余额变动不能直接代替年度净利润；利润分配、分红、盈余公积提取及调整等可能影响余额。须核对同范围利润表、所有者权益变动表及相关附注，不能凭余额差额断言这些事项实际发生或倒推出净利润。');
  if(/现金及存放中央银行款项/.test(question)&&/现金等价物/.test(question))answerLines.push('现金及存放中央银行款项不能整体直接等同于现金及现金等价物，不能仅凭该余额确定现金及现金等价物的精确金额；还须核对同一时点、同一范围的现金流量表及现金等价物构成附注。须按现金等价物构成和受限资金等附注核对具体项目的可用性与定义；主表余额本身不能证明各组成项目均符合现金等价物口径。');
  if(/所有者权益|股东权益|净资产|账面权益/.test(question)&&/资本充足率|监管资本/.test(question))answerLines.push('账面所有者权益不能直接当作监管资本，也不能单凭账面权益确定资本充足率；需适用监管口径的资本净额、扣减与调整以及风险加权资产，并核对同一时点、适用范围的监管披露。');
  if(/应收账款/.test(question)&&/逾期|90天|九十天/.test(question))answerLines.push('应收账款账面金额不能证明款项逾期或全部逾期90天。账龄与逾期天数的起算口径不同；须核对合同约定到期日、逐笔收款及逾期披露，判断减值还需对应信用风险和损失准备证据，不能仅凭主表净额推断。');
  if(/存货/.test(question)&&/原值|跌价准备|减值准备/.test(question))answerLines.push('主表存货账面金额不能单独拆分出存货原值与跌价准备，不能把账面金额直接当作原值，也不能假定准备为零。须补充同一时点、同一范围的存货原值、跌价准备及账面价值附注细分，逐项核对后才能给出对应金额。');
  if(/商誉/.test(question)&&/原值|累计减值|减值准备|本期减值|当期减值/.test(question)&&facts.some(f=>matches(f,['商誉'])&&context.sourceFacts?.some(s=>s.sourceId===f.sourceId&&s.scope===f.scope&&s.period===f.period&&matches(s,['商誉'])&&/资产负债表$/.test(s.tableTitle??'')))){
    const constraint='主表商誉账面金额不能单独确定商誉原值、累计减值准备或本期减值损失，不能把净额当作原值，也不能假定准备或本期损失为零。须补充同一时点、同一范围的商誉附注及减值准备期初、增加、减少和期末变动表；累计准备是存量，不等于本期减值损失。';
    answerLines.push(constraint);mustNotInfer.push(constraint);boundaryMissing.push('商誉原值、累计减值准备及本期减值变动的附注细分尚未核验');
  }
  // Financial definition checks developed from exposed cases. These explain
  // why a verified main-statement amount cannot identify an undisclosed split;
  // no candidate narrative, hidden answer key or missing amount is adopted.
  const boundaries=[
    {metric:'无形资产',table:'资产负债表',when:/原值|累计摊销/.test(question)&&/判断|能否|确定|拆/.test(question),gap:'同一时点、同一范围的无形资产原值、累计摊销及减值准备附注细分尚未核验',constraint:'主表无形资产账面金额不能单独拆出原值与累计摊销，也不能假定摊销或减值准备为零；须补充同一时点、同一范围的无形资产原值、累计摊销、减值准备及账面价值附注细分，不能将净额直接作为原值。'},
    {metric:'利息费用',table:'利润表',when:/借款/.test(question)&&/平均利率/.test(question)&&/判断|能否|确定/.test(question),gap:'同年度借款利息口径、资本化利息、时间加权平均借款余额及利率定义尚未核验',constraint:'利润表利息费用不能单独精确确定借款平均利率；须补充同年度适用借款利息、资本化利息、时间加权平均借款余额及平均利率定义，并区分租赁、其他融资及不同计息期间，不能将期末借款余额或全部利息费用直接替代适用分子分母。'},
    {metric:'存货',table:'资产负债表',when:/原值|跌价准备|减值准备/.test(question)&&/判断|能否|确定|拆分/.test(question),gap:'同一时点、同一范围的存货原值及跌价准备附注细分尚未核验',constraint:'主表存货账面金额不能单独确定存货原值和跌价准备，不能把账面金额当作原值或假定准备为零；须补充同一时点、同一范围的存货原值、跌价准备及账面价值附注细分，逐项核对后才能确定对应金额。'},
    {metric:'使用权资产',table:'资产负债表',when:/租赁/.test(question)&&/未折现|到期分布/.test(question),gap:'租赁合同未折现付款额及逐年到期分布的附注尚未核验',constraint:'使用权资产是资产账面金额，不能直接当作全部租赁合同未来未折现付款额或逐年到期分布；须补充同一时点、同一范围的租赁合同承诺及未折现现金流到期分析附注，核对折现、已付款及合同范围。'},
    {metric:'研发费用',table:'利润表',when:/资本化/.test(question),gap:'研发支出费用化、资本化及总额的附注细分尚未核验',constraint:'利润表研发费用不能单独确定研发支出资本化金额或资本化率，也不能假定资本化为零；须补充同年度、同范围的研发支出费用化、资本化及总额披露与资本化率定义，不能把费用金额直接作为研发投入总额。'},
    {metric:'分配股利、利润或偿付利息支付的现金',table:'现金流量表',when:/仅支付股利|仅.*股利.*现金|分离.*股利/.test(question),gap:'股利、利润分配及利息支付的分项现金附注尚未核验',constraint:'分配股利、利润或偿付利息支付的现金包含不同性质的支付，不能将合计直接当作仅支付股利的现金，也不能用少数股东股利子项代表全部股利；须补充同年度、同范围的股利、利润分配和利息支付分项附注。'},
    {metric:'实收资本（或股本）',table:'资产负债表',when:/市值/.test(question),gap:'目标交易日股价、实际股数及股本面值的适用证据尚未核验',constraint:'实收资本或股本的货币金额不能直接当作实际股数或总市值；总市值还须目标交易日的股价、股份数量及适用股类口径，股本金额转为股数须有每股面值等依据，不能把人民币元直接写成股或补造股价。'},
    {metric:'营业收入',table:'利润表',when:/地区|分部/.test(question)&&/确定|判断|拆分|分离/.test(question),gap:'所问地区营业收入及地区划分口径的分部附注尚未核验',constraint:'主表营业收入合计不能单独确定某地区营业收入；须补充同年度、同范围的地区或经营分部收入附注，明确按客户所在地、经营所在地或其他口径划分并核对内部交易抵销，不能凭合计分摊或推测地区占比。'},
    {metric:'支付的各项税费',table:'现金流量表',when:/企业所得税/.test(question)&&/分离|仅|拆分|确定/.test(question),gap:'按税种列示的企业所得税实际现金支付附注尚未核验',constraint:'支付的各项税费包含多个税种，不能直接等同企业所得税现金支付额；须补充同年度、同范围按税种列示的实际现金支付及适用调节附注，利润表所得税费用也不等于当期所得税现金支付。'},
    {metric:'基本每股收益',table:'利润表',when:/精确|精确到股/.test(question)&&/加权平均|股数/.test(question),gap:'每股收益未舍入计算分子、加权平均股数及调整口径的附注尚未核验',constraint:'已披露基本每股收益通常经过舍入，净利润除以该每股收益只能得到近似比值，不能精确还原加权平均普通股股数；须补充基本每股收益计算附注、未舍入分子及优先股等调整、实际加权平均股数，不能将近似结果冒充精确到股的披露值。'},
  ];
  for(const rule of boundaries)if(rule.when&&facts.some(f=>matches(f,[rule.metric])&&context.sourceFacts?.some(s=>s.sourceId===f.sourceId&&s.scope===f.scope&&s.period===f.period&&matches(s,[rule.metric])&&(s.tableTitle??'').endsWith(rule.table)))){
    answerLines.push(rule.constraint);mustNotInfer.push(rule.constraint);boundaryMissing.push(rule.gap);
  }
  if(/贷款|垫款/.test(question)&&/逾期|90天|九十天/.test(question))answerLines.push('贷款和垫款主表金额不能单独确定逾期90天以上贷款的细分金额，也不能当作逾期贷款金额。须补充同一时点、同一范围的贷款逾期天数分类附注及相关减值口径，不能凭主表总额推断逾期分布。');
  if(/其他综合收益/.test(question)&&/余额/.test(question)&&/差额|变动/.test(question)&&/年度/.test(question)&&/当作|等同|代替|推算|倒推/.test(question)&&/税后净额|发生额/.test(question)&&
    facts.some(f=>matches(f,['其他综合收益'])&&context.sourceFacts?.some(s=>s.sourceId===f.sourceId&&s.scope===f.scope&&s.period===f.period&&matches(s,['其他综合收益'])&&/资产负债表$/.test(s.tableTitle??'')))){
    const constraint='其他综合收益余额差额不能直接当作年度其他综合收益税后净额。资产负债表提供时点存量；年度期间发生额须核对同范围利润表或综合收益表，并结合所有者权益变动表及相关附注衔接；不能仅凭余额差额断言具体调整或变动原因实际发生。';
    answerLines.push(constraint);mustNotInfer.push(constraint);
    boundaryMissing.push('年度其他综合收益期间发生额及与余额变动的衔接证据尚未核验；需同范围利润表或综合收益表、所有者权益变动表及相关附注');
  }
  return {answerLines:[...new Set(answerLines)],sourceAssessment,boundaryEvidence,boundaryMissing,mustNotInfer};
}
