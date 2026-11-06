import fs from 'node:fs/promises'
import path from 'node:path'
import {createHash} from 'node:crypto'
import {fetchForecastQfqBars} from './source'
import {buildPriceFeatures,predictTreeModel,PRICE_FEATURES,type PriceBar,type PriceTreeModel} from './model'
import type {ForecastSummary,PriceForecastResult} from './types'
const base=()=>path.join(process.cwd(),'public','forecast')
const hash=(bytes:Buffer)=>createHash('sha256').update(bytes).digest('hex')
export async function getForecastSummary():Promise<ForecastSummary> {
  const value=JSON.parse(await fs.readFile(path.join(base(),'summary.json'),'utf8')) as ForecastSummary
  if(value.version!=='lightgbm-stock-v1'||JSON.stringify(value.featureNames)!==JSON.stringify(PRICE_FEATURES)||!Array.isArray(value.dataManifest))
    throw Error('预测模型档案尚未通过格式核验')
  return value
}
export async function runPriceForecast(stockCode:string,mode:'snapshot'|'live'):Promise<PriceForecastResult> {
  const started=performance.now(),summary=await getForecastSummary()
  const source=summary.dataManifest.find(s=>s.code===stockCode)
  if(!source || !/^\d{6}$/.test(stockCode))throw Error('实验只支持已验证的六只股票')
  const bytes=await fs.readFile(path.join(base(),'model-v1.json'))
  if(hash(bytes)!==summary.modelSha256)throw Error('模型文件完整性核验失败')
  const model=JSON.parse(bytes.toString('utf8')) as PriceTreeModel
  if(JSON.stringify(model.feature_names)!==JSON.stringify(PRICE_FEATURES))throw Error('模型特征顺序不一致')
  let bars:PriceBar[]
  if(mode==='live')bars=await fetchForecastQfqBars(stockCode,500)
  else{
    const raw=await fs.readFile(path.join(base(),`${stockCode}-bars.json`))
    if(hash(raw)!==source.barsSha256)throw Error('冻结数据文件完整性核验失败')
    bars=JSON.parse(raw.toString('utf8')) as PriceBar[]
  }
  const features=buildPriceFeatures(bars),latest=bars.at(-1)!
  if(latest.date<summary.segments.train.lastFeatureDate)throw Error('输入日线早于训练截止日，不能作为未来预测')
  const prediction=predictTreeModel(model,features),radius=summary.errorBand.radiusFraction
  if(prediction<=-1||!Number.isFinite(radius)||radius<0)throw Error('预测或误差范围无效')
  return {stockCode,stockName:source.name,modelVersion:summary.version,mode,inputDate:latest.date,
    inputSource:mode==='live'?'腾讯日线接口本次采集（前复权）':'冻结的真实日线快照（前复权）',observedClose:latest.close,
    predictedChangePct:prediction*100,predictedClose:latest.close*(1+prediction),errorBandPct:[(prediction-radius)*100,(prediction+radius)*100],
    predictionPeriod:'下一实际交易日；未指定日历日期',inferenceMs:performance.now()-started,history:bars.slice(-30).map(b=>({date:b.date,close:b.close})),
    scope:'experimental_price_change',investmentDecisionEligible:false}
}
