export type FilingProvider='mimo'|'deepseek';
export type FilingModelIdentity={provider:FilingProvider;requestedModel:string;responseModel:string;endpoint:string};
type ResolvedFilingProvider=Readonly<{provider:FilingProvider;model:string;endpoint:string;apiKey:string}>;

/** Resolve once per run. Credentials never belong in persisted model identity. */
export function resolveFilingProvider(apiKeyOverride?:string):ResolvedFilingProvider{
  const provider=process.env.FILINGS_PROVIDER??'deepseek';
  if(provider!=='mimo'&&provider!=='deepseek')throw new Error('FILINGS_PROVIDER 仅支持 mimo 或 deepseek');
  const prefix=provider==='mimo'?'MIMO':'DEEPSEEK';
  const model=(process.env[`${prefix}_MODEL`]??(provider==='mimo'?'mimo-v2.5':'deepseek-flash')).trim();
  if(!model||model.length>150||/[\s\x00-\x1f]/.test(model))throw new Error(`${prefix}_MODEL 配置不合法`);
  const base=(process.env[`${prefix}_BASE_URL`]??(provider==='mimo'?'https://api.xiaomimimo.com/v1':'https://api.deepseek.com')).trim();
  let url:URL;
  try{url=new URL(base);}catch{throw new Error(`${prefix}_BASE_URL 配置不合法`);}
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash)throw new Error(`${prefix}_BASE_URL 必须是无凭证、查询参数或片段的 HTTP(S) 地址`);
  const pathname=url.pathname.replace(/\/+$/,'');
  url.pathname=pathname.endsWith('/chat/completions')?pathname:pathname+'/chat/completions';
  return Object.freeze({provider,model,endpoint:url.toString(),apiKey:apiKeyOverride??process.env[`${prefix}_API_KEY`]??''});
}

export function filingModelIdentity(config:ResolvedFilingProvider):FilingModelIdentity{
  return {provider:config.provider,requestedModel:config.model,responseModel:'unknown',endpoint:config.endpoint};
}

export function redactFilingCredential(text:string,apiKey:string):string{
  return apiKey?text.replaceAll(apiKey,'[REDACTED]'):text;
}
