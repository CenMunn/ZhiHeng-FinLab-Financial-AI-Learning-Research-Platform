import fs from 'node:fs';
import path from 'node:path';
import net from 'node:net';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {createGateway,localOrigin} from './committee-runtime.mjs';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const configPath=process.argv.includes('--config')?path.resolve(process.argv[process.argv.indexOf('--config')+1]):path.join(root,'.local/committee/config.json');
const checksum=file=>createHash('sha256').update(fs.readFileSync(file)).digest('hex');
function free(port){return new Promise((resolve,reject)=>{const probe=net.createServer();probe.once('error',()=>reject(Error(`端口 ${port} 已占用，不会结束已有进程。`)));probe.listen(port,'127.0.0.1',()=>probe.close(resolve));});}

async function main(){
  const config=JSON.parse(fs.readFileSync(configPath,'utf8'));
  const manifest=JSON.parse(fs.readFileSync(path.join(root,'integrations/committee-manifest.json'),'utf8'));
  for(const port of [config.port,config.upstreamPort])if(!Number.isInteger(port)||port<1024||port>65535)throw Error('Invalid local port');
  if(config.port===config.upstreamPort)throw Error('Gateway and application ports must differ');
  const origin=localOrigin(`http://127.0.0.1:${config.port}`),platformOrigin=localOrigin(config.platformOrigin);
  await free(config.port);await free(config.upstreamPort);
  const runtime=path.resolve(config.runtimeDir),index=path.join(root,'.local/committee/runtime-files.json');
  if(checksum(index)!==manifest.runtime_index_sha256)throw Error('运行清单发生变化，请重新核对智投委版本。');
  const files=JSON.parse(fs.readFileSync(index,'utf8'));
  for(const [relative,expected] of Object.entries(files)){
    const target=path.resolve(runtime,relative);
    if(!target.startsWith(runtime+path.sep)||checksum(target)!==expected)throw Error('运行包完整性核验失败：'+relative);
  }
  if(fs.readFileSync(path.join(runtime,manifest.build_directory,'BUILD_ID'),'utf8').trim()!==manifest.build_id)throw Error('Next构建版本不一致');
  if(!fs.statSync(config.databasePath).isFile()||!fs.statSync(config.filingsDir).isDirectory())throw Error('原账号数据库或财报目录不存在，不会新建替代数据。');
  if(config.envFile)process.loadEnvFile(config.envFile);
  const env={...process.env,NODE_ENV:'production',NEXT_TELEMETRY_DISABLED:'1',HOSTNAME:'127.0.0.1',PORT:String(config.upstreamPort),APP_ORIGIN:origin,
    DATABASE_URL:'file:'+path.resolve(config.databasePath).replaceAll('\\','/'),FILINGS_DATA_DIR:path.resolve(config.filingsDir),
    FILINGS_PROVIDER:'deepseek',DEEPSEEK_MODEL:'deepseek-flash',DEEPSEEK_BASE_URL:'https://api.deepseek.com',FILINGS_RETRY_POLICY:'no_content_only',
    LLM_AUDIT_LOG:path.join(root,'.local/committee/llm-audit.jsonl'),MIMO_API_KEY:'',ZAI_API_KEY:'',OPENAI_API_KEY:''};
  for(const key of Object.keys(env))if(/^PRISMA_/i.test(key)||['NODE_OPTIONS','NODE_PATH'].includes(key.toUpperCase()))delete env[key];
  const logs=path.join(root,'.local/committee');fs.mkdirSync(logs,{recursive:true});
  const child=spawn(process.execPath,[path.join(runtime,'server.js')],{cwd:runtime,env,windowsHide:true,
    stdio:['ignore',fs.openSync(path.join(logs,'server.log'),'a'),fs.openSync(path.join(logs,'server-error.log'),'a')]});
  const gateway=createGateway({upstreamOrigin:`http://127.0.0.1:${config.upstreamPort}`,platformOrigin,identity:{buildId:manifest.build_id,release:manifest.release}});
  let stopping=false;
  function stop(){if(stopping)return;stopping=true;gateway.close();child.kill();}
  gateway.on('error',error=>{console.error(error.message);stop();process.exitCode=1;});
  child.on('error',error=>{console.error('智投委启动失败：'+error.message);stop();process.exitCode=1;});
  child.on('exit',code=>{gateway.close();process.exitCode=code??1;});
  process.on('SIGINT',stop);process.on('SIGTERM',stop);
  gateway.listen(config.port,'127.0.0.1',()=>console.log(`智投委 ${manifest.release} 已挂载 ${origin}；沿用现有账号和资料。`));
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
