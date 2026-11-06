export function sourcePageIndex(pages:{page:number}[],sha256:string,sourceId:string){return pages.findIndex(p=>sourceId===`pdf:${sha256}:p${p.page}`);}
export async function readLimitedBody(stream:ReadableStream<Uint8Array>|null,limit:number):Promise<Uint8Array>{
  if(!stream)return new Uint8Array();const reader=stream.getReader(),chunks:Uint8Array[]=[];let total=0;
  try{while(true){const {done,value}=await reader.read();if(done)break;total+=value.length;if(total>limit){await reader.cancel();throw new Error('请求体超过允许大小');}chunks.push(value);}}finally{reader.releaseLock();}
  const bytes=new Uint8Array(total);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}return bytes;
}
