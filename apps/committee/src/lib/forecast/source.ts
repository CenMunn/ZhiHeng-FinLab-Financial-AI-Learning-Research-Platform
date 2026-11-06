import type {PriceBar} from './model'

/** Forecast features require qfq prices. Never reuse the mixed-source quote cache. */
export async function fetchForecastQfqBars(code:string,days=500,request:typeof fetch=fetch):Promise<PriceBar[]> {
  if(!/^(?:0|3|6)\d{5}$/.test(code))throw Error('预测行情只支持A股六位代码')
  const symbol=(code.startsWith('6')?'sh':'sz')+code
  for(const host of ['https://web.ifzq.gtimg.cn','https://proxy.finance.qq.com']) {
    try {
      const res=await request(`${host}/ifzqgtimg/appstock/app/fqkline/get?param=${symbol},day,,,${Math.min(Math.max(days,31),800)},qfq`,
        {cache:'no-store',signal:AbortSignal.timeout(12_000)})
      if(!res.ok)continue
      const json=await res.json() as {code?:number;data?:Record<string,{qfqday?:unknown}>}
      const rows=json.data?.[symbol]?.qfqday
      if(json.code!==0||!Array.isArray(rows)||!rows.length)continue
      const bars=rows.map(row=>{
        if(!Array.isArray(row)||row.length<6)throw Error('日线格式无效')
        const bar={date:String(row[0]),open:Number(row[1]),close:Number(row[2]),high:Number(row[3]),low:Number(row[4]),volume:Number(row[5])}
        if(!/^\d{4}-\d{2}-\d{2}$/.test(bar.date)||![bar.open,bar.close,bar.high,bar.low,bar.volume].every(Number.isFinite)
          ||Math.min(bar.open,bar.close,bar.high,bar.low)<=0||bar.volume<0)throw Error('日线值无效')
        return bar
      })
      return bars
    }catch{/* Only retry the same qfq contract on the Tencent mirror. */}
  }
  throw Error('腾讯前复权日线不可用；未采用其他复权口径，请使用冻结快照或稍后重试')
}
