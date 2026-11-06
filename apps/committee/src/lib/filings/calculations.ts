import {samePeriod} from './period.ts';
import {metricLabel} from './labels.ts';
import type {Draft} from './core.ts';
type Rational={n:bigint;d:bigint};
export type CalculationContract={roundingDigits?:number;invalidReason?:string};
const denominations:Record<string,bigint>={'元':BigInt(1),'千元':BigInt(1000),'万元':BigInt(10000),'百万元':BigInt(1000000),'亿元':BigInt(100000000)};
export function conversionExpression(value:string,fromUnit:string,toUnit:string){
  const from=denominations[fromUnit],to=denominations[toUnit];
  if(!from||!to)throw new Error('不支持的换算单位');
  return from<=to?`${value} ${fromUnit} ÷ ${to/from}`:`${value} ${fromUnit} × ${from/to}`;
}
export function calculationContract(question:string):CalculationContract{
  const digits:Record<string,number>={'零':0,'一':1,'二':2,'两':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8};
  const mentions=[...question.matchAll(/(?:保留(?:小数点后)?|小数点后)\s*([0-9]+|[零一二两三四五六七八九十]+)\s*位(?:小数)?/g)].map(m=>/^\d+$/.test(m[1])?Number(m[1]):digits[m[1]]);
  if(mentions.some(v=>!Number.isInteger(v)||v<0||v>8)||new Set(mentions).size>1)return {invalidReason:'题目精度不明确或不支持；需明确统一的0–8位小数'};
  return mentions.length?{roundingDigits:mentions[0]}:{};
}
function decimal(s:string):Rational{
  let value=s.trim().replace(/[,，\s]/g,'');if(/^\([\d.]+\)$/.test(value))value='-'+value.slice(1,-1);
  if(!/^-?\d+(?:\.\d+)?$/.test(value)||value.length>80)throw new Error('数值格式不合法');
  const [a,b='']=value.split('.');return {n:BigInt(a.replace('-','')+b)*(a.startsWith('-')?-BigInt(1):BigInt(1)),d:BigInt(10)**BigInt(b.length)};
}
const add=(a:Rational,b:Rational):Rational=>({n:a.n*b.d+b.n*a.d,d:a.d*b.d});
const subtract=(a:Rational,b:Rational):Rational=>add(a,{n:-b.n,d:b.d});
function divide(a:Rational,b:Rational):Rational{
  if(b.n===BigInt(0))throw new Error('分母为零');const sign=b.n<BigInt(0)?-BigInt(1):BigInt(1);return {n:a.n*b.d*sign,d:a.d*b.n*sign};
}
function equal(a:Rational,b:Rational){return a.n*b.d===b.n*a.d;}
export function compareFinancialAmounts(a:string,b:string){
  const x=decimal(a),y=decimal(b),diff=x.n*y.d-y.n*x.d;
  return diff<BigInt(0)?-1:diff>BigInt(0)?1:0;
}
function rounded(a:Rational,digits:number):Rational{
  const scale=BigInt(10)**BigInt(digits),sign=a.n<BigInt(0)?-BigInt(1):BigInt(1),n=(a.n<BigInt(0)?-a.n:a.n)*scale;
  let q=n/a.d;if((n%a.d)*BigInt(2)>=a.d)q++;
  return {n:q*sign,d:scale};
}
const norm=(s:string)=>s.replace(/[\s|：:、，,（）()]/g,'');
export function cashRole(label:string){
  const s=metricLabel(label).replace(/(?:产生[╱/]使用|使用[╱/]产生)/g,'产生');
  if(/^(?:加)?(?:期初|年初)现金及现金等价物余额$/.test(s))return 'opening';
  if(/^现金及现金等价物净(?:增加额|减少\/增加额)$/.test(s))return 'movement';
  if(/^经营活动(?:产生|使用)的现金流量净额$/.test(s)||s==='经营净现金流')return 'operating';
  if(/^投资活动(?:产生|使用)的现金流量净额$/.test(s)||s==='投资净现金流')return 'investing';
  if(/^筹资活动(?:产生|使用)的现金流量净额$/.test(s)||s==='筹资净现金流')return 'financing';
  if(/^汇率变动对现金及现金等价物的影响$/.test(s)||s==='汇率变动影响')return 'fx';
  return null;
}
export function cashRollForwardPeriod(c:Draft['calculations'][number],facts:Draft['facts']){
  if(c.operation!=='sum'||![2,5].includes(c.operands.length)||new Set(c.operands).size!==c.operands.length)return null;
  const fs=c.operands.map(i=>facts[i]);if(fs.some(f=>!f))return null;
  const roles=fs.map(f=>cashRole(f.label)),opening=fs.find((_,i)=>roles[i]==='opening');
  const expected=fs.length===2?['opening','movement']:['opening','operating','investing','financing','fx'];
  if(!opening||new Set(roles).size!==expected.length||expected.some(r=>!roles.includes(r as NonNullable<typeof roles[number]>)))return null;
  if(opening.period!==`${opening.year}-01-01`||fs.some(f=>f.year!==opening.year||f.scope!==opening.scope||f.unit!==opening.unit||f.sourceId.replace(/:p\d+$/,'')!==opening.sourceId.replace(/:p\d+$/,'')))return null;
  if(fs.some(f=>f!==opening&&f.period!==String(opening.year)))return null;
  return `${opening.year}-12-31`;
}
export function calculationResultCoordinate(c:Draft['calculations'][number],facts:Draft['facts']){
  const fs=c.operands.map(i=>facts[i]);if(!fs.length||fs.some(f=>!f))return null;
  const closing=cashRollForwardPeriod(c,facts);
  if(closing)return {label:'期末现金及现金等价物余额',year:fs[0].year,period:closing,scope:fs[0].scope};
  if(c.operation==='sum'&&fs.length===2&&new Set(c.operands).size===2&&fs.every(f=>samePeriod(f,fs[0])&&f.scope===fs[0].scope)&&
    fs.some(f=>/^归属于母公司(?:股东|所有者)的净利润$/.test(metricLabel(f.label)))&&fs.some(f=>metricLabel(f.label)==='少数股东损益'))return {label:'净利润',year:fs[0].year,period:fs[0].period??String(fs[0].year),scope:fs[0].scope};
  return null;
}
export function reviewCalculation(c:Draft['calculations'][number],facts:Draft['facts'],contract:CalculationContract={}):{ok:boolean;reason:string;normalizedValue?:string}{
  const fail=(reason:string)=>({ok:false,reason});
  if(contract.invalidReason)return fail(contract.invalidReason);
  if(contract.roundingDigits!==undefined&&(!Number.isInteger(contract.roundingDigits)||contract.roundingDigits<0||contract.roundingDigits>8))return fail('服务端精度契约无效');
  const arity=c.operation==='unit_conversion'?1:c.operation==='percentage_point_change'?4:['difference_ratio','average_denominator_ratio'].includes(c.operation)?3:c.operation==='sum'?null:2;
  if((arity!==null&&c.operands.length!==arity)||(arity===null&&(c.operands.length<2||c.operands.length>8)))return fail('操作数数量不符');
  if(c.operands.some(i=>!Number.isInteger(i)||i<0||i>=facts.length||!facts[i]))return fail('操作数下标越界，不自动替换引用');
  const fs=c.operands.map(i=>facts[i]),a=fs[0],b=fs[1];
  if(fs.some(f=>f.scope!==a.scope||f.sourceId.replace(/:p\d+$/,'')!==a.sourceId.replace(/:p\d+$/,'')))return fail('跨报表范围或跨资料计算不支持');
  if(fs.some(f=>f.unit!==a.unit))return fail('输入单位不一致，请单独提供明确转换');
  const cashRollForward=cashRollForwardPeriod(c,facts)!==null;
  if(['ratio','sum','difference_ratio','absolute_ratio'].includes(c.operation)&&!fs.every(f=>samePeriod(f,a))&&!cashRollForward)return fail('比值或加总须同一期间/时点，不能混合年初与年末');
  if(c.operation==='growth'&&a.period?.length===10&&b.period?.length===10&&a.period.slice(4)!==b.period.slice(4))return fail('同比须同一月日的可比期间');
  if(c.operation==='difference'&&a.year===b.year&&!samePeriod(a,b)&&!(a.period&&b.period&&a.period>b.period&&norm(a.label)===norm(b.label)))return fail('同年不同时点差额须同指标较晚时点减较早时点');
  if(c.operation==='percentage_point_change'&&(!samePeriod(fs[0],fs[1])||!samePeriod(fs[2],fs[3])))return fail('各期比率必须使用相同期间/时点');
  const sameYear=fs.every(f=>f.year===a.year),sameMetric=(x:typeof a,y:typeof a)=>norm(x.label)===norm(y.label);
  if(c.operation==='growth'&&!(a.year===b.year+1&&sameMetric(a,b)))return fail('同比须为同指标本年相对上年，年度方向不符');
  if(c.operation==='difference'&&!sameYear&&!(a.year>b.year&&sameMetric(a,b)))return fail('跨年差额须同指标较新年度减较旧年度');
  if(['ratio','sum','difference_ratio','absolute_ratio'].includes(c.operation)&&!sameYear)return fail('比值或加总须同年度');
  if(c.operation==='average_denominator_ratio'&&!(a.period===String(a.year)&&b.period===`${a.year-1}-12-31`&&fs[2].period===`${a.year}-12-31`&&b.year===a.year-1&&fs[2].year===a.year&&sameMetric(b,fs[2])))return fail('年度平均分母须本年年度流量、上年末和本年末同指标余额，顺序不能互换');
  if(c.operation==='percentage_point_change'&&!(fs[0].year===fs[1].year&&fs[2].year===fs[3].year&&fs[0].year>fs[2].year&&sameMetric(fs[0],fs[2])&&sameMetric(fs[1],fs[3])))return fail('百分点变化须两期同口径比率，较新年度在前');
  try{
    const vs=fs.map(f=>decimal(f.value));let expected:Rational;
    switch(c.operation){
      case 'unit_conversion':{
        const from=denominations[a.unit],to=denominations[c.unit];
        if(!from||!to)return fail('转换仅支持人民币金额单位，元/股不是金额');
        expected={n:vs[0].n*from,d:vs[0].d*to};break;
      }
      case 'sum':case 'difference':
        if(c.unit!==a.unit)return fail('加减结果单位须与输入一致');
        expected=c.operation==='sum'?vs.reduce(add,{n:BigInt(0),d:BigInt(1)}):subtract(vs[0],vs[1]);break;
      case 'ratio':case 'growth':
        if(!['%','倍'].includes(c.unit))return fail('比率/同比单位须为%或倍，不能写百分点');
        expected=divide(vs[0],vs[1]);if(c.operation==='growth')expected=subtract(expected,{n:BigInt(1),d:BigInt(1)});
        if(c.unit==='%')expected={n:expected.n*BigInt(100),d:expected.d};break;
      case 'difference_ratio':case 'absolute_ratio':case 'average_denominator_ratio':
        if(!['%','倍'].includes(c.unit))return fail('复合比率单位须为%或倍');
        expected=c.operation==='difference_ratio'?divide(subtract(vs[0],vs[1]),vs[2]):c.operation==='absolute_ratio'?divide({...vs[0],n:vs[0].n<BigInt(0)?-vs[0].n:vs[0].n},vs[1]):divide(vs[0],divide(add(vs[1],vs[2]),{n:BigInt(2),d:BigInt(1)}));
        if(c.unit==='%')expected={n:expected.n*BigInt(100),d:expected.d};break;
      case 'percentage_point_change':
        if(c.unit!=='百分点')return fail('两期比率差须明确为百分点');
        expected=subtract(divide(vs[0],vs[1]),divide(vs[2],vs[3]));expected={n:expected.n*BigInt(100),d:expected.d};break;
      default:return fail('不支持的计算操作');
    }
    const digits=contract.roundingDigits??(['ratio','growth','unit_conversion','percentage_point_change','difference_ratio','absolute_ratio','average_denominator_ratio'].includes(c.operation)?4:undefined);
    const target=digits===undefined?expected:rounded(expected,digits);
    const observed=decimal(c.value),ok=equal(target,observed);
    // Explicit precision governs display. Preserve the original candidate in
    // audit, but do not reject extra decimals that round to the exact target.
    if(!ok&&contract.roundingDigits!==undefined&&equal(target,rounded(observed,contract.roundingDigits))){
      const places=contract.roundingDigits,negative=target.n<BigInt(0),n=negative?-target.n:target.n;
      const s=n.toString().padStart(places+1,'0');
      const value=(negative?'-':'')+(places?s.slice(0,-places)+'.'+s.slice(-places):s);
      return {ok:true,reason:`来源和操作数通过；按题目${places}位小数精确复算并标准化，原候选保留审计`,normalizedValue:value};
    }
    return {ok,reason:ok?`输入口径、年度方向、单位及精确复算一致${digits===undefined?'（不舍入）':`（服务端四舍五入${digits}位）`}`:'精确复算或舍入结果不一致'};
  }catch(e){return fail(e instanceof Error?e.message:'无法复算');}
}
