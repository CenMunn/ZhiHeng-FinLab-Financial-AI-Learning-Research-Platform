// Read-only integration checks. Does not create accounts or request a language model.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {createRequire}=require('node:module');
const {pathToFileURL}=require('node:url');
const {createHash}=require('node:crypto');

function samplePdf(){
 const stream='BT /F1 12 Tf 30 150 Td (Revenue 1000) Tj ET';
 const objects=['<< /Type /Catalog /Pages 2 0 R >>','<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',`<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`];
 let text='%PDF-1.4\n',offsets=[0];
 objects.forEach((object,i)=>{offsets.push(Buffer.byteLength(text));text+=`${i+1} 0 obj\n${object}\nendobj\n`;});
 const start=Buffer.byteLength(text);text+=`xref\n0 6\n0000000000 65535 f \n`;
 for(const offset of offsets.slice(1))text+=String(offset).padStart(10,'0')+' 00000 n \n';
 text+=`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${start}\n%%EOF\n`;return Buffer.from(text);
}

(async()=>{
 const root=path.resolve(__dirname,'..'),config=JSON.parse(fs.readFileSync(path.join(root,'.local/committee/config.json'),'utf8'));
 const req=createRequire(path.join(config.runtimeDir,'package.json'));
 const {PrismaClient}=req('@prisma/client');
 const db=new PrismaClient({datasources:{db:{url:'file:'+config.databasePath.replaceAll('\\','/')}}});
 let counts;
 try{await db.$queryRawUnsafe('SELECT 1');counts={users:await db.user.count(),sessions:await db.researchSession.count()};}finally{await db.$disconnect();}
 const {PDFParse}=req('pdf-parse');const parser=new PDFParse({data:new Uint8Array(samplePdf())});
 try{const value=await parser.getText();assert.match(value.text,/Revenue 1000/);}finally{await parser.destroy();}
 const modelDir=path.join(config.runtimeDir,'public/forecast');
 const summary=JSON.parse(fs.readFileSync(path.join(modelDir,'summary.json'),'utf8'));
 const bytes=fs.readFileSync(path.join(modelDir,'model-v1.json'));
 assert.equal(createHash('sha256').update(bytes).digest('hex'),summary.modelSha256);
 const model=JSON.parse(bytes.toString('utf8'));
 const {buildPriceFeatures,predictTreeModel,PRICE_FEATURES}=await import(pathToFileURL(path.join(root,'apps/committee/src/lib/forecast/model.ts')).href);
 assert.deepEqual(model.feature_names,PRICE_FEATURES);
 for(const input of summary.dataManifest){
   const raw=fs.readFileSync(path.join(modelDir,input.code+'-bars.json'));
   assert.equal(createHash('sha256').update(raw).digest('hex'),input.barsSha256);
   const prediction=predictTreeModel(model,buildPriceFeatures(JSON.parse(raw.toString('utf8'))));
   assert.ok(Number.isFinite(prediction)&&prediction>-1);
 }
 const report={status:'passed',databaseCounts:counts,syntheticPdfParser:true,frozenModelHash:true,frozenStocksInferred:summary.dataManifest.length,
  languageModelCalls:0,databaseWrites:0,scope:'Dependency and inference smoke checks, not model performance evaluation'};
 fs.writeFileSync(path.join(root,'.local/committee/runtime-qa.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
})().catch(e=>{console.error(e);process.exitCode=1});
