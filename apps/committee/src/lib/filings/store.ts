import { db } from '@/lib/db';
import { ownerFilter, type AuthUser } from '@/lib/auth/core';
import { mkdir, writeFile, readFile, unlink } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
import type { parseFilingPdf } from './pdf';
import type { callFilingModel, FilingMode } from './model';
import type { reviewDraft } from './core';
import type {AdoptedReport} from './adoption';
import type {SourcePageMapEntry} from './source-pages';
import type {ProtocolExport} from './protocol';
export type FilingDocument=Awaited<ReturnType<typeof parseFilingPdf>>&{id:string;companyCode:string;companyName:string;reportYear:number;filename:string;createdAt:string;importDurationMs:number;identityStatus:'declared'};
export type FilingRun=Awaited<ReturnType<typeof callFilingModel>>&{id:string;documentId:string;companyName:string;question:string;mode:FilingMode;sha256:string;sourcePages:number[];sourcePageMap?:SourcePageMapEntry[];createdAt:string;durationMs:number;review:ReturnType<typeof reviewDraft>|null;adoptedReport?:AdoptedReport|null;protocol?:ProtocolExport;reportMd:string;status:string;stageDurations:Record<string,number>};
const dir=process.env.FILINGS_DATA_DIR?resolve(process.env.FILINGS_DATA_DIR):resolve(process.cwd(),'db','filing-documents');
function pdfPath(id:string){if(!/^pdf_[a-f0-9-]{36}$/.test(id))throw new Error('文档编号不合法');return resolve(dir,id+'.pdf');}
export async function saveDocument(user:AuthUser,doc:Omit<FilingDocument,'id'|'createdAt'>,bytes:Uint8Array){
  const id='pdf_'+randomUUID(),document={...doc,id,createdAt:new Date().toISOString()};await mkdir(dir,{recursive:true});await writeFile(pdfPath(id),bytes,{flag:'wx'});
  try{await db.researchSession.create({data:{id,ownerId:user.id,query:'PDF导入',stockCode:doc.companyCode,stockName:doc.companyName,status:'completed',progress:100,meta:JSON.stringify({kind:'filing_document',document})}});}catch(e){await unlink(pdfPath(id));throw e;}return document;
}
export async function getFiling<T>(user:AuthUser,id:string,kind:'filing_document'|'filing_run'):Promise<T|null>{
  if(!/^(?:pdf|fr)_[a-f0-9-]{36}$/.test(id))return null;
  const row=await db.researchSession.findFirst({where:{id,...ownerFilter(user)}});if(!row?.meta)return null;
  const meta=JSON.parse(row.meta);return meta.kind===kind?(kind==='filing_document'?meta.document:meta.run):null;
}
export async function getPdfBytes(id:string){return readFile(pdfPath(id));}
export async function saveRun(user:AuthUser,run:FilingRun){const data={ownerId:user.id,query:run.question,stockName:run.companyName,status:run.status,currentStepLabel:run.mode,progress:run.status==='running'?50:100,meta:JSON.stringify({kind:'filing_run',run})};await db.researchSession.upsert({where:{id:run.id},create:{id:run.id,...data},update:data});}
export async function listFilings(user:AuthUser){const rows=await db.researchSession.findMany({where:{...ownerFilter(user),OR:[{id:{startsWith:'pdf_'}},{id:{startsWith:'fr_'}}]},orderBy:{createdAt:'desc'},take:100,select:{id:true,query:true,stockName:true,status:true,createdAt:true,currentStepLabel:true}});return rows;}
