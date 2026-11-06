import type {Page} from './core.ts';
export type SourcePageMapEntry={sourceId:string;uploadedPage:number;originalPage:number|null};
export function buildSourcePageMap(pages:Page[],sha256:string):SourcePageMapEntry[]{
  return pages.map((p,i)=>({sourceId:`pdf:${sha256}:p${p.page}`,uploadedPage:i+1,originalPage:p.physicalPageDeclared===true?p.page:null}));
}
export function sourceCitation(map:SourcePageMapEntry[],sha256:string,sourceId:string):string|null{
  const seen=new Set<string>();
  for(let i=0;i<map.length;i++){
    const p=map[i];
    if(p.uploadedPage!==i+1||seen.has(p.sourceId)||p.originalPage!==null&&(!Number.isInteger(p.originalPage)||p.originalPage<1)||p.sourceId!==`pdf:${sha256}:p${p.originalPage??p.uploadedPage}`)return null;
    seen.add(p.sourceId);
  }
  const p=map.find(p=>p.sourceId===sourceId);
  return p?`上传PDF物理页 ${p.uploadedPage}；${p.originalPage===null?'原报告物理页未声明':`原报告物理页 ${p.originalPage}（上传者声明）`}`:null;
}
