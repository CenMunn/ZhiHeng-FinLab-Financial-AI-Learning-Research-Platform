/** Read API failures without exposing parser exceptions or upstream HTML. */
export async function readFilingResponse<T=Record<string,unknown>>(response:Response):Promise<T>{
  const text=await response.text();
  let value:unknown;
  try{value=JSON.parse(text);}catch{/* Empty and truncated upstream responses are handled below. */}
  const object=!!value&&typeof value==='object'&&!Array.isArray(value);
  if(!response.ok){
    if(object&&typeof (value as {error?:unknown}).error==='string')throw new Error((value as {error:string}).error);
    if(response.status===413)throw new Error('上传文件过大，请选择8 MiB以内的PDF。');
    if(response.status===401)throw new Error('登录已失效，请重新登录后再试。');
    throw new Error(`财报服务暂时不可用（HTTP ${response.status}），请稍后重试或联系管理员。`);
  }
  if(!object)throw new Error('财报服务返回数据不完整，请重新读取；若持续出现，请联系管理员。');
  return value as T;
}
