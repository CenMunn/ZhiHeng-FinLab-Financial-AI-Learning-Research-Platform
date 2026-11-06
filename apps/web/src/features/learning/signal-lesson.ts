/** Synthetic teaching inputs, never market observations or a backtest. */
export const LESSON_SERIES={
  ashare:[100,102,101,104,103,105,107,106,108,111,109,108,106,105,107,110,113,112,115,117,116,114,111,109,108,110,112,115,118,117,119,122,120,118,116,117,120,123,122,125,127,124,121,119,120,123,125,128],
  btc:[100,104,102,108,112,106,110,117,115,123,120,113,107,110,116,125,130,123,127,135,131,120,112,105,108,114,121,130,137,132,140,148,141,131,124,129,139,150,145,155,160,148,136,130,138,149,158,165],
} as const;

export function movingAverage(values:readonly number[],window:number):(number|null)[]{
  if(!Number.isInteger(window)||window<1)throw Error('Window must be a positive integer');
  if(values.some(value=>!Number.isFinite(value)))throw Error('Samples must be finite');
  let sum=0;
  return values.map((value,index)=>{sum+=value;if(index>=window)sum-=values[index-window];return index<window-1?null:sum/window;});
}
export function lessonSignal(value:number,average:number|null){
  return average===null?'warmup':value===average?'equal':value>average?'above':'below';
}
