import {NextResponse} from 'next/server';
import {randomUUID} from 'node:crypto';
import {requireUser,authErrorResponse} from '@/lib/auth/server';
import {parseFilingPdf,MAX_PDF_BYTES,FILING_PARSER_VERSION} from '@/lib/filings/pdf';
import {callFilingModel,buildFilingRequest} from '@/lib/filings/model';
import {reviewDraft,renderReport,buildAdoptedReport} from '@/lib/filings/core';
import {readLimitedBody} from '@/lib/filings/boundaries';
import {buildSourcePageMap} from '@/lib/filings/source-pages';
import {buildProtocolExport} from '@/lib/filings/protocol';
import {saveDocument,getFiling,getPdfBytes,saveRun,listFilings,type FilingDocument,type FilingRun} from '@/lib/filings/store';
export const runtime='nodejs';export const dynamic='force-dynamic';export const maxDuration=300;
const headers={'Cache-Control':'no-store'};
const fail=(message:string,status=400)=>NextResponse.json({error:message},{status,headers});
export async function GET(req:Request){try{
  const user=await requireUser(req),url=new URL(req.url),action=url.searchParams.get('action')??'list',id=url.searchParams.get('id')??'';
  if(action==='list')return NextResponse.json({items:await listFilings(user)},{headers});
  if(action==='document'||action==='source'){
    const document=await getFiling<FilingDocument>(user,id,'filing_document');if(!document)return fail('文档不存在或无权查看',404);
    if(action==='document')return NextResponse.json({document},{headers});
    return new Response(new Uint8Array(await getPdfBytes(document.id)),{headers:{...headers,'Content-Type':'application/pdf','Content-Disposition':'inline; filename="source.pdf"','X-Content-Type-Options':'nosniff'}});
  }
  const run=await getFiling<FilingRun>(user,id,'filing_run');if(!run)return fail('报告不存在或无权查看',404);
  if(action==='report')return NextResponse.json({run},{headers});
  if(action==='export'){const format=url.searchParams.get('format');if(!['md','json'].includes(format??''))return fail('仅支持 md 或 json');return new Response(format==='md'?run.reportMd:JSON.stringify(run,null,2),{headers:{...headers,'Content-Type':format==='md'?'text/markdown; charset=utf-8':'application/json; charset=utf-8','Content-Disposition':`attachment; filename="${run.id}.${format}"`,'X-Content-Type-Options':'nosniff'}});}
  return fail('未知操作');
}catch(e){return authErrorResponse(e)??fail('读取失败，请重试',500);}}
export async function POST(req:Request){try{
  const user=await requireUser(req,{write:true}),start=Date.now();
  const multipart=req.headers.get('content-type')?.includes('multipart/form-data'),limit=multipart?MAX_PDF_BYTES+100000:10000;
  let bodyBytes;try{bodyBytes=await readLimitedBody(req.body,limit);}catch{return fail('请求体超过允许大小',413);}
  if(req.headers.get('content-type')?.includes('multipart/form-data')){
    const length=Number(req.headers.get('content-length')??0);if(length>MAX_PDF_BYTES+100000)return fail('上传文件过大',413);
    const bounded=new Request(req.url,{method:'POST',headers:req.headers,body:new Uint8Array(bodyBytes)});
    const form=await bounded.formData(),file=form.get('file'),companyCode=String(form.get('companyCode')??'').trim(),companyName=String(form.get('companyName')??'').trim(),reportYear=Number(form.get('reportYear')),pageMap=String(form.get('pageMap')??'');
    if(!(file instanceof File)||file.size>MAX_PDF_BYTES||!/^\d{6}$/.test(companyCode)||!companyName||companyName.length>80||!Number.isInteger(reportYear)||reportYear<1990||reportYear>2100)return fail('请填写六位股票代码、公司、年度，并选择 8 MiB 以内 PDF');
    const bytes=new Uint8Array(await file.arrayBuffer());let parsed;try{parsed=await parseFilingPdf(bytes,pageMap);}catch(e){return fail(e instanceof Error?e.message:'PDF无法解析');}
    // Identity is a user declaration, not independent issuer authentication.
    const document=await saveDocument(user,{...parsed,companyCode,companyName,reportYear,filename:file.name.slice(0,150),identityStatus:'declared',importDurationMs:Date.now()-start},bytes);
    return NextResponse.json({document},{status:201,headers});
  }
  let body;try{body=JSON.parse(new TextDecoder().decode(bodyBytes));}catch{return fail('JSON格式不合法');}if(!body||body.action!=='run'||!['single_model','current_evidence'].includes(body.mode)||typeof body.question!=='string'||!body.question.trim()||body.question.length>2000)return fail('运行参数不合法');
  const document=await getFiling<FilingDocument>(user,String(body.documentId??''),'filing_document');if(!document)return fail('文档不存在或无权使用',404);
  if(document.parserVersion!==FILING_PARSER_VERSION)return fail('该PDF使用旧版文本解析，请重新导入以核验实际列位置',409);
  const pending:FilingRun={id:'fr_'+randomUUID(),documentId:document.id,companyName:document.companyName,sha256:document.sha256,sourcePages:document.pages.map(p=>p.page),sourcePageMap:buildSourcePageMap(document.pages,document.sha256),question:body.question,mode:body.mode,createdAt:new Date().toISOString(),durationMs:0,review:null,reportMd:'',status:'running',error:undefined,draft:null,attempts:[],request:buildFilingRequest(body.question,document.pages,document.sha256,body.mode),stageDurations:{importMs:document.importDurationMs}};
  pending.reportMd='任务已启动，尚未生成最终回答。若服务中断，这条记录不算完成或成功；已经返回的技术尝试会逐次保留在JSON中。';await saveRun(user,pending);
  const modelStart=Date.now(),result=await callFilingModel(body.question,document.pages,document.sha256,body.mode,{onAttempts:async attempts=>{pending.attempts=attempts;pending.durationMs=Date.now()-start;await saveRun(user,pending);}}),modelMs=Date.now()-modelStart,reviewStart=Date.now();
  const review=body.mode==='current_evidence'&&result.draft?reviewDraft(result.draft,document.facts,{question:body.question}):null;
  const adoptedReport=result.draft&&review?buildAdoptedReport(result.draft,review,body.question,pending.id,{sourceFacts:document.facts,statementBlocks:document.statementBlocks}):null;
  const run:FilingRun={...pending,...result,durationMs:Date.now()-start,review,adoptedReport,reportMd:'',status:result.error?'failed':'completed',stageDurations:{importMs:document.importDurationMs,modelMs,reviewMs:Date.now()-reviewStart}};
  run.protocol=buildProtocolExport(run,document);run.reportMd=renderReport(run);const saveStart=Date.now();await saveRun(user,run);
  return NextResponse.json({run,persistMs:Date.now()-saveStart},{headers});
}catch(e){return authErrorResponse(e)??fail('处理失败，请检查文件或运行参数',500);}}
