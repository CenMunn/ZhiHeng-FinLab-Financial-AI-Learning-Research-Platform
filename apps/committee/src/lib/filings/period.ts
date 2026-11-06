// Preserve source dates; January 1 is not silently relabelled as the prior year.
export function sourcePeriods(text:string):string[]{
  return [...text.replace(/(20\d{2})-(\d{2})-(\d{2})/g,'$1年$2月$3日').replace(/[|\s]/g,'').matchAll(/(20\d{2})年(?:(\d{1,2})月(\d{1,2})日)?/g)].map(m=>{
    if(!m[2])return m[1];
    const y=Number(m[1]),month=Number(m[2]),day=Number(m[3]);
    const date=new Date(Date.UTC(y,month-1,day));
    return date.getUTCFullYear()===y&&date.getUTCMonth()===month-1&&date.getUTCDate()===day?`${y}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`:'invalid';
  });
}
export const periodLabel=(f:{year:number;period?:string})=>f.period&&f.period.length>4?f.period:`${f.year}年`;
export const samePeriod=(a:{year:number;period?:string},b:{year:number;period?:string})=>a.year===b.year&&(a.period??String(a.year))===(b.period??String(b.year));
// Aliases are internal source provenance, never accepted from model JSON.
// A year-only request cannot borrow a different year's opening-date alias.
export function matchesPeriodCoordinate(f:{year:number;period?:string;periodAliases?:string[]},year:number|null,period:string|null){
  if(period&&f.periodAliases?.includes(period)&&(year===null||year===Number(period.slice(0,4))))return true;
  return (year===null||f.year===year)&&(period===null||f.period===period);
}

export function requestedPeriods(question:string,year:number|null):(string|null)[]{
  const dates=[...new Set(sourcePeriods(question).filter(p=>p.length===10&&(year===null||Number(p.slice(0,4))===year)))];
  return dates.length?dates:[null];
}

// An explicit annual qualifier immediately governing an income/cash-flow
// metric is not overridden by another metric's balance-sheet date.
export function metricPeriodQuestion(question:string,aliases:string[]){
  const positions=aliases.map(a=>question.indexOf(a)).filter(i=>i>=0);
  if(!positions.length)return ''; // Do not lend another metric's question date to an unasked operand.
  const before=question.slice(0,Math.min(...positions));
  const last=[...before.matchAll(/20\d{2}(?:年(?:\d{1,2}月\d{1,2}日|度)?|-\d{2}-\d{2})/g)].at(-1)?.[0];
  return last?.endsWith('年度')?last:question;
}
