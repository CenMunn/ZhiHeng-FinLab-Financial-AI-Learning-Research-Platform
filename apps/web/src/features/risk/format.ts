export function money(value:string):string {
  const match=/^(-?)(\d+)(?:\.(\d+))?$/.exec(value);
  if(!match)return '—';
  const fraction=(match[3]||'').padEnd(3,'0');
  let cents=BigInt(match[2])*100n+BigInt(fraction.slice(0,2));
  if(Number(fraction[2])>=5)cents+=1n;
  const digits=cents.toString().padStart(3,'0');
  return `${match[1] && cents!==0n?'-':''}${digits.slice(0,-2).replace(/\B(?=(\d{3})+(?!\d))/g,',')}.${digits.slice(-2)}`;
}
export function savedTime(value:string):string {
  return new Intl.DateTimeFormat('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false,timeZone:'Asia/Shanghai'}).format(new Date(value));
}
