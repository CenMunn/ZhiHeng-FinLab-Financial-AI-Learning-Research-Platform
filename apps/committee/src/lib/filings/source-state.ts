import type {StatementBlock} from './statements.ts';
import {stripNote,metricLabel} from './labels.ts';
export type SourceBlock=Pick<StatementBlock,'name'|'page'|'status'|'gap'>&Partial<StatementBlock>;
// Nonnumeric observations are separate from monetary facts. A blank is only
// observable when the parser supplied an explicit, complete cell binding.
export function nonNumericEpsCells(blocks:SourceBlock[]=[]){
  const observations=blocks.flatMap(block=>{
    if(block.status!=='parsed'||!block.id||!block.columns?.length||!block.headerEvidence?.some(h=>h.page===block.page&&h.relation==='own'))return [];
    if(!/(?:利润表|损益表)$/.test(block.name))return [];
    const columns=block.columns,n=columns.length;
    return (block.rows??[]).flatMap(row=>{
      let name=row.label,cells=row.cells;
      if(!name||cells?.length!==n){
        const numeric='(?:\\(?-?\\d[\\d,，]*(?:\\.\\d+)?\\)?|[-–—])';
        const m=row.text.match(new RegExp('((?:'+numeric+'[ \\t|]+){'+(n-1)+'}'+numeric+')[ \\t|]*$'));
        if(!m||m.index===undefined)return [];
        name=row.text.slice(0,m.index).trim().replace(/[|\s]+$/,'');cells=m[1].split(/[\s|]+/).filter(Boolean);
        // A numeric prefix may be an excess amount rather than a note. Text
        // fallback has no independent note binding, so do not strip it to
        // force the remaining suffix into the declared number of columns.
        if(/\d/.test(name))return [];
      }
      const label=metricLabel(stripNote(name)).replace(/(?:人民币)?元(?:\/股)?$/,'');
      if(!['基本每股收益','稀释每股收益'].includes(label)||cells.length!==n)return [];
      return cells.map((cell,i)=>({
        statementId:block.id!,sourceId:`${block.id!.replace(/:s\d+$/,'')}`,page:block.page,tableTitle:block.name,
        label,columnIndex:i,year:columns[i].year,period:columns[i].period??String(columns[i].year),scope:columns[i].scope,
        state:cell===null?'blank' as const:/^[-–—]+$/.test(cell.trim())?'dash' as const:'numeric' as const,quote:row.text,unitEvidence:row.unitEvidence,headerEvidence:block.headerEvidence!,
      }));
    });
  });
  // A second row at the same reporting coordinate is ambiguous, including
  // a numeric row that disagrees with a dash/blank observation.
  return observations.filter(o=>o.state!=='numeric'&&observations.filter(x=>x.label===o.label&&x.scope===o.scope&&x.period===o.period).length===1);
}
export type NonNumericEvidence=ReturnType<typeof nonNumericEpsCells>[number];
