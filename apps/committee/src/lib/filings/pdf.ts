import { PDFParse } from 'pdf-parse';
import { createHash } from 'node:crypto';
import path from 'node:path';
import { extractFacts, parsePageMap, type Page } from './core.ts';
import {extractStatementBlocks} from './statements.ts';
import {getDocument,GlobalWorkerOptions} from 'pdfjs-dist/legacy/build/pdf.mjs';
GlobalWorkerOptions.workerSrc='./pdf.worker.mjs';
export const MAX_PDF_BYTES=8*1024*1024;
export const FILING_PARSER_VERSION='pdf-parse2.4.5+pdfjs5.4.296-statements-v14-provenance-joint-wrapped-labels';
// Identity-H CID fonts may have no ToUnicode map. Use PDF.js's bundled Adobe
// maps for BOTH model text and verification coordinates, without OCR or HTTP.
// Next's server bundle rewrites createRequire(import.meta.url).resolve to a
// numeric module id. Resolve at runtime from the app root (standalone server
// changes cwd to its own directory) so the result stays a filesystem path.
const runtimeRequire=process.getBuiltinModule('module').createRequire(path.join(process.cwd(),'package.json'));
const cMapUrl=path.join(path.dirname(runtimeRequire.resolve('pdfjs-dist/package.json')),'cmaps').replaceAll('\\','/')+'/';
export async function parseFilingPdf(bytes:Uint8Array,pageMap:string){
  if(bytes.length>MAX_PDF_BYTES||bytes.length<20||Buffer.from(bytes.subarray(0,5)).toString()!=='%PDF-')throw new Error('仅接受有效 PDF，大小上限 8 MiB');
  const sha256=createHash('sha256').update(bytes).digest('hex');
  const parser=new PDFParse({data:new Uint8Array(bytes),cMapUrl,cMapPacked:true});
  try{const info=await parser.getInfo();if(info.total<1||info.total>40)throw new Error('请上传 1–40 页财务原页；整本年报请先截取财务页');
    const result=await parser.getText({cellSeparator:'|',lineEnforce:true});
    if(result.text.length>120000)throw new Error('PDF 文本超过120000字符，请减少页数');
    const physical=parsePageMap(pageMap,result.pages.length),pages=result.pages.map((p,i)=>({page:physical[i],uploadedPage:i+1,text:p.text,physicalPageDeclared:!!pageMap.trim()}));
    if(pages.some(p=>p.text.trim().length<30))throw new Error('部分页缺少可读取文本；扫描件暂不支持，请上传有文本层的财务原页');
    const missingLabels=pages.filter(p=>(p.text.match(/[\u4e00-\u9fff]/g)??[]).length<10);
    if(missingLabels.length)throw new Error(`原物理页${missingLabels.map(p=>p.page).join('、')}文本层缺少中文行名或表头，仅有数字也不能核验。当前不支持自动OCR；请提供含可复制中文的财务原页，或先OCR并人工核对。`);
    const layoutTask=getDocument({data:new Uint8Array(bytes),cMapUrl,cMapPacked:true,verbosity:0});
    try{const layoutPdf=await layoutTask.promise,positioned:Page[]=[];
      for(let i=0;i<pages.length;i++){const content=await (await layoutPdf.getPage(i+1)).getTextContent();const items=content.items.filter((item):item is typeof item&{str:string;transform:number[];width:number}=>'str' in item);positioned.push({...pages[i],layoutItems:items.map(item=>({str:item.str,transform:item.transform,width:item.width}))});}
      const statementBlocks=extractStatementBlocks(positioned,sha256);
      return {sha256,pages:positioned,facts:extractFacts(positioned,sha256),statementBlocks,mappingDeclared:!!pageMap.trim(),bytes:bytes.length,parserVersion:FILING_PARSER_VERSION};
    }finally{await layoutTask.destroy();}
  }finally{await parser.destroy();}
}
