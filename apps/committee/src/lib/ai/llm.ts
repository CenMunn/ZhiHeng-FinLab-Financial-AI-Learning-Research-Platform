import { AsyncLocalStorage } from 'node:async_hooks'
import { appendFileSync } from 'node:fs'

// Legacy role arguments remain source-compatible; generation is unified on DeepSeek.
export type LLMProvider = 'deepseek' | 'zai' | 'mimo'
export const MODEL_LABEL: Record<LLMProvider,string> = {deepseek:'deepseek-flash',zai:'deepseek-flash',mimo:'deepseek-flash'}
export interface LLMCall {
  requestedModel:string; responseModel:string; responseId?:string; durationMs:number
  usage?:{prompt_tokens?:number;completion_tokens?:number;total_tokens?:number}
  status:'ok'|'failed'; error?:string; finishReason?:string
}
const trace = new AsyncLocalStorage<LLMCall[]>()
export async function withLLMTrace<T>(run:()=>Promise<T>):Promise<{value:T;calls:LLMCall[]}> {
  const calls:LLMCall[]=[]
  return trace.run(calls,async()=>{
    try{return {value:await run(),calls}}
    catch(error){throw Object.assign(error instanceof Error?error:new Error('LLM_FAILED'),{llmCalls:calls})}
  })
}
function record(call:LLMCall) {
  trace.getStore()?.push(call)
  // Never log keys, prompts, provider error bodies or private report content.
  if(process.env.LLM_AUDIT_LOG) {
    try{appendFileSync(process.env.LLM_AUDIT_LOG,JSON.stringify({at:new Date().toISOString(),...call})+'\n')}
    catch{console.error('[llm] audit log unavailable')}
  }
}
export function extractJSON<T>(raw:string):T {
  let text=raw.trim()
  const fence=text.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if(fence)text=fence[1].trim()
  try{return JSON.parse(text) as T}catch{}
  const start=text.indexOf('{'),end=text.lastIndexOf('}')
  if(start>=0&&end>start){try{return JSON.parse(text.slice(start,end+1)) as T}catch{}}
  throw new Error('JSON_PARSE_FAILED')
}
let active=0
const waiting:(()=>void)[]=[]
async function acquire(){if(active<3){active++;return}await new Promise<void>(resolve=>waiting.push(resolve))}
function release(){const next=waiting.shift();if(next)next();else active--}
const wait=(ms:number)=>new Promise<void>(resolve=>setTimeout(resolve,ms))
const JSON_RULE='只输出一个完整、合法的 JSON 对象，遵循任务指定字段，不添加 Markdown 或对象外说明。字符串中的英文双引号必须转义；每个字段必须有双引号键名和冒号；null 后不得添加引号。不得补造数据。'
function configuration(){
  const key=process.env.DEEPSEEK_API_KEY?.trim()
  if(!key)throw new Error('DEEPSEEK_API_KEY_NOT_CONFIGURED')
  const model=process.env.DEEPSEEK_MODEL?.trim()||'deepseek-flash'
  const url=new URL(process.env.DEEPSEEK_BASE_URL||'https://api.deepseek.com')
  if(url.username||url.password||url.search||url.hash||
    !(url.protocol==='https:'||(url.protocol==='http:'&&['127.0.0.1','localhost'].includes(url.hostname))))throw new Error('DEEPSEEK_ENDPOINT_INVALID')
  const p=url.pathname.replace(/\/+$/,'');url.pathname=p.endsWith('/chat/completions')?p:p+'/chat/completions'
  return {key,model,url:url.toString()}
}
async function generate(system:string,user:string,timeoutMs:number,json:boolean):Promise<string> {
  const config=configuration(),deadline=Date.now()+timeoutMs
  let lastError:Error=new Error('LLM_FAILED'),correct=false
  for(let attempt=0;attempt<3;attempt++) {
    await acquire()
    let timer:ReturnType<typeof setTimeout>|undefined
    const started=Date.now(),call:LLMCall={requestedModel:config.model,responseModel:'unknown',durationMs:0,status:'failed'}
    try {
      if(Date.now()>=deadline)throw new Error('LLM_TIMEOUT')
      const controller=new AbortController()
      timer=setTimeout(()=>controller.abort(),deadline-Date.now())
      const res=await fetch(config.url,{
        method:'POST',headers:{'Content-Type':'application/json',Authorization:`Bearer ${config.key}`},signal:controller.signal,
        body:JSON.stringify({model:config.model,messages:[
          {role:'system',content:json?`${system}\n\n${JSON_RULE}`:system},
          {role:'user',content:correct?`${user}\n\n（上一次返回的 JSON 格式校验失败。请重新生成完整对象。${JSON_RULE}）`:user}
        ],max_tokens:6000,temperature:0.6,stream:false,thinking:{type:'disabled'},
        ...(json?{response_format:{type:'json_object'}}:{})})
      })
      if(!res.ok)throw new Error(`DEEPSEEK_HTTP_${res.status}`)
      const data=await res.json()
      call.responseModel=typeof data.model==='string'?data.model:'unknown'
      call.responseId=typeof data.id==='string'?data.id:undefined
      if(data.usage)call.usage=Object.fromEntries(['prompt_tokens','completion_tokens','total_tokens'].filter(k=>typeof data.usage[k]==='number').map(k=>[k,data.usage[k]]))
      const choice=data.choices?.[0];call.finishReason=choice?.finish_reason
      if(choice?.finish_reason==='length')throw new Error('DEEPSEEK_TRUNCATED_RESPONSE')
      if(choice?.finish_reason&&choice.finish_reason!=='stop')throw new Error('DEEPSEEK_NONFINAL_RESPONSE')
      const content=choice?.message?.content
      if(typeof content!=='string'||!content.trim())throw new Error('EMPTY_LLM_RESPONSE')
      if(json){const value=extractJSON<unknown>(content);if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('JSON_OBJECT_REQUIRED')}
      call.status='ok'
      return content
    } catch(e) {
      const message=e instanceof Error?e.message:''
      lastError=new Error(e instanceof Error&&e.name==='AbortError'?'LLM_TIMEOUT':
        /^(DEEPSEEK_HTTP_\d+|DEEPSEEK_TRUNCATED_RESPONSE|DEEPSEEK_NONFINAL_RESPONSE|EMPTY_LLM_RESPONSE|JSON_PARSE_FAILED|JSON_OBJECT_REQUIRED|LLM_TIMEOUT)$/.test(message)?message:'DEEPSEEK_TRANSPORT_ERROR')
      call.error=lastError.message
      correct=['JSON_PARSE_FAILED','JSON_OBJECT_REQUIRED'].includes(lastError.message)
      if(/DEEPSEEK_HTTP_(400|401|402|403|404|422)$/.test(lastError.message)||lastError.message==='LLM_TIMEOUT')throw lastError
    } finally {
      if(timer)clearTimeout(timer)
      call.durationMs=Date.now()-started;record(call);release()
    }
    if(attempt<2){const delay=lastError.message==='DEEPSEEK_HTTP_429'?1500:250;if(Date.now()+delay>=deadline)break;await wait(delay)}
  }
  throw lastError
}
export async function chatText(system:string,user:string,timeoutMs=120_000,_provider:LLMProvider='deepseek'):Promise<string>{return generate(system,user,timeoutMs,false)}
export async function chatJSON<T>(system:string,user:string,timeoutMs=120_000,_provider:LLMProvider='deepseek'):Promise<T>{return extractJSON<T>(await generate(system,user,timeoutMs,true))}
export async function tryChatJSON<T>(system:string,user:string,timeoutMs=120_000,provider:LLMProvider='deepseek'):Promise<T|null>{
  try{return await chatJSON<T>(system,user,timeoutMs,provider)}catch{return null}
}
