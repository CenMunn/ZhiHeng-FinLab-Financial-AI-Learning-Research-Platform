import {NextRequest,NextResponse} from 'next/server'
import {requireUser,authErrorResponse} from '@/lib/auth/server'
import {getForecastSummary,runPriceForecast} from '@/lib/forecast/server'
export const dynamic='force-dynamic'
const options={headers:{'Cache-Control':'no-store'}}
export async function GET(req:NextRequest) {
  try{await requireUser(req);return NextResponse.json(await getForecastSummary(),options)}
  catch(e){return authErrorResponse(e)??NextResponse.json({error:'预测实验档案尚未就绪或核验失败'},{status:503,...options})}
}
export async function POST(req:NextRequest) {
  try{
    await requireUser(req,{write:true})
    const body=await req.json().catch(()=>null)
    if(!body||typeof body.stockCode!=='string'||!/^\d{6}$/.test(body.stockCode)||!['snapshot','live'].includes(body.mode))
      return NextResponse.json({error:'请选择实验股票及快照/当前日线模式'},{status:400,...options})
    const summary=await getForecastSummary()
    if(!summary.dataManifest.some(s=>s.code===body.stockCode))return NextResponse.json({error:'该股票尚未完成模型验证'},{status:400,...options})
    return NextResponse.json(await runPriceForecast(body.stockCode,body.mode),options)
  }catch(e){
    const auth=authErrorResponse(e);if(auth)return auth
    const safeErrors=new Set(['模型文件完整性核验失败','冻结数据文件完整性核验失败','模型特征顺序不一致','腾讯前复权日线不可用；未采用其他复权口径，请使用冻结快照或稍后重试'])
    const message=e instanceof Error&&safeErrors.has(e.message)?e.message:'模型或日线不可用，请核对实验档案与数据来源'
    return NextResponse.json({error:'预测未完成：'+message},{status:502,...options})
  }
}
