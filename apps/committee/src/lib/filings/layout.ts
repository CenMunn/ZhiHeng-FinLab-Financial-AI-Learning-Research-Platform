import {sourcePeriods} from './period.ts';
export type TextItem={str:string;transform:number[];width:number};
export type LayoutLine={y:number;text:string;items:TextItem[]};
export type ColumnGeometry={years:TextItem[];anchors:number[];periods?:string[];annualRelativeBalances?:boolean};
const numeric=/^(?:\(?-?\d[\d,，]*(?:\.\d+)?\)?|[-–—])$/;
export const yearItem=(i:TextItem)=>/^20\d{2}(?:\s*年.*)?$/.test(i.str.trim());
export function positionedLines(items:TextItem[]):LayoutLine[]{
  const rows:{y:number;items:TextItem[]}[]=[];
  for(const item of items){if(!item.str.trim())continue;let row=rows.find(r=>Math.abs(r.y-item.transform[5])<2);if(!row){row={y:item.transform[5],items:[]};rows.push(row);}row.items.push(item);}
  rows.sort((a,b)=>b.y-a.y);
  return rows.map(r=>{
    const merged:TextItem[]=[];
    for(const i of [...r.items].sort((a,b)=>a.transform[4]-b.transform[4])){
      const prev=merged.at(-1);
      const gap=prev?i.transform[4]-(prev.transform[4]+prev.width):Infinity;
      // Some PDFs space every date glyph. Coalesce only a valid date prefix,
      // within a bounded font-scale gap; never join neighbouring amount cells.
      const joined=prev?(prev.str+i.str).replace(/\s/g,''):'';
      const dateFragment=prev&&/^20\d{2}(?:年[\d月日]*)?$/.test(prev.str.replace(/\s/g,''))&&!/日/.test(prev.str)&&/^20\d{2}年(?:\d{1,2}(?:月(?:\d{1,2}日?)?)?)?$/.test(joined);
      const dateGap=Math.min(3.2,Math.max(Math.abs(i.transform[0]),Math.abs(i.transform[3]))*.35);
      if(prev&&(gap<=1.3||dateFragment&&gap<=dateGap)){prev.str+=i.str;prev.width=i.transform[4]+i.width-prev.transform[4];}
      else merged.push({...i,transform:[...i.transform]});
    }
    return {y:r.y,items:merged,text:merged.map(i=>i.str).join(' |')};
  });
}
// A continuation must independently reproduce each monetary column's anchor.
// Note numbers and blank cells never supply missing amounts.
function columnPeriods(rows:LayoutLine[],years:TextItem[]):string[]{
  const centers=years.map(i=>i.transform[4]+i.width/2);
  return years.map((year,c)=>{
    const left=c? (centers[c-1]+centers[c])/2:-Infinity,right=c+1<years.length?(centers[c]+centers[c+1])/2:Infinity;
    const local=rows.filter(r=>r.y<=year.transform[5]+2&&r.y>=year.transform[5]-36).flatMap(r=>r.items).filter(i=>{
      const x=i.transform[4]+i.width/2;
      return x>left&&x<right&&/^(?:[\d年月日度\s()（）]|已重述|重述后|经重述|调整后)+$/.test(i.str);
    }).map(i=>i.str).join('').replace(/\s/g,'');
    // A second caption in one column is conflicting metadata, not body data
    // to discard after accepting the first regex match.
    if([...local.matchAll(/20\d{2}年?/g)].length!==1||[...local.matchAll(/\d{1,2}月\d{1,2}日/g)].length>1)return 'invalid';
    const full=local.match(/^(20\d{2})年?(?:(\d{1,2})月(\d{1,2})日)?/);
    if(!full?.[2])return year.str.trim().slice(0,4);
    const y=Number(full[1]),m=Number(full[2]),d=Number(full[3]),date=new Date(Date.UTC(y,m-1,d));
    return date.getUTCFullYear()===y&&date.getUTCMonth()===m-1&&date.getUTCDate()===d?`${y}-${String(m).padStart(2,'0')}-${String(d).padStart(2,'0')}`:'invalid';
  });
}
function bindAtHeader(rows:LayoutLine[],count:number,header:LayoutLine|undefined,years:TextItem[],inherited?:ColumnGeometry,resolvedPeriods?:string[]){
  if(years.length!==count)return null;
  const spacing=Math.min(...years.slice(1).map((i,j)=>i.transform[4]-years[j].transform[4]));
  if(spacing<20)return null;
  const labelOnly=(r:LayoutLine)=>r.items.length>0&&r.items.every(i=>i.transform[4]+i.width<years[0].transform[4]-20)&&/[\u4e00-\u9fff]/.test(r.text);
  const candidates=rows.flatMap((r,index)=>{
    if(header&&r.y>=header.y-3)return [];
    const isNote=(i:TextItem)=>/^[一二三四五六七八九十]+[、](?:\d+)(?:[（(][\da-zA-Z]+[）)])?$/.test(i.str.replace(/\s/g,''));
    const noteOnly=r.items.some(isNote)&&r.items.every(i=>numeric.test(i.str.trim())||isNote(i));
    if(!noteOnly&&r.items.some(i=>/[\u4e00-\u9fff]/.test(i.str))){
      const labelItems=r.items.filter(i=>i.transform[4]+i.width<years[0].transform[4]-20&&!/^\d+[（(][\da-zA-Z]+[）)]$/.test(i.str.trim()));
      if(labelItems.length&&r.items.filter(i=>numeric.test(i.str.trim())).length>=count){
        const prefixes:LayoutLine[]=[];let next=r,labelX=Math.min(...labelItems.map(i=>i.transform[4]));
        for(let j=index-1;j>=Math.max(0,index-2);j--){
          const above=rows[j],text=above.items.map(i=>i.str).join(''),x=Math.min(...above.items.map(i=>i.transform[4]));
          const right=Math.max(...above.items.map(i=>i.transform[4]+i.width));
          const suffix=labelItems.map(i=>i.str).join('').replace(/\s/g,'');
          const cashWrap=prefixes.length===0&&/(?:现金|现金流量|现金及现金等价物的)$/.test(text)&&/^(?:流量净额|净额|影响)$/.test(suffix);
          if(!labelOnly(above)||above.y-next.y>18||labelX-x< -2||labelX-x>40||(!cashWrap&&right<years[0].transform[4]-80)||(text.match(/[\u4e00-\u9fff]/g)??[]).length<8||(!cashWrap&&!/(?:计入|其他综合(?:收)?|且其变(?:动)?|的)$/.test(text)))break;
          prefixes.unshift(above);next=above;labelX=x;
        }
        if(prefixes.length){
          const first=prefixes[0].items[0],text=prefixes.map(l=>l.items.map(i=>i.str).join('')).join('')+labelItems.map(i=>i.str).join('');
          const merged={str:text,transform:[...first.transform],width:Math.max(...labelItems.map(i=>i.transform[4]+i.width))-first.transform[4]};merged.transform[5]=r.y;
          return [{...r,items:[merged,...r.items.filter(i=>!labelItems.includes(i))],text:text+' |'+r.items.filter(i=>!labelItems.includes(i)).map(i=>i.str).join(' |')}];
        }
      }
      return [r];
    }
    // A wrapped label can straddle a vertically centred amount row. Require
    // both neighbouring label-only lines and a complete numeric row; never
    // borrow a label from the next ordinary amount row or bridge a wide gap.
    const above=rows[index-1],below=rows[index+1];
    if(!above||!below||above.y-r.y>8.5||r.y-below.y>8.5||!labelOnly(above)||!labelOnly(below)||r.items.filter(i=>numeric.test(i.str.trim())).length<count||r.items.some(i=>!numeric.test(i.str.trim())&&!isNote(i)))return [];
    const first=above.items[0],text=[above,below].map(l=>l.items.map(i=>i.str).join('')).join('');
    const merged={str:text,transform:[...first.transform],width:Math.max(...[above,below].flatMap(l=>l.items.map(i=>i.transform[4]+i.width)))-first.transform[4]};merged.transform[5]=r.y;
    return [{...r,items:[merged,...r.items],text:text+' |'+r.text}];
  });
  const tolerance=Math.min(spacing*.12,8),anchors:number[]=[];
  for(let c=0;c<count;c++){
    // PDF financial amounts often align with the year heading's right edge.
    // Allow bounded glyph-width jitter, keeping note columns to its left out.
    const left=years[c].transform[4]+years[c].width-tolerance,right=years[c+1]?.transform[4]??years[c].transform[4]+spacing;
    const clusters:{x:number;hits:number}[]=[];
    for(const row of candidates)for(const item of row.items){
      const x=item.transform[4]+item.width;
      if(!numeric.test(item.str.trim())||x<=left||x>=right)continue;
      const cluster=clusters.find(k=>Math.abs(k.x-x)<=tolerance);
      if(cluster){cluster.x=(cluster.x*cluster.hits+x)/(cluster.hits+1);cluster.hits++;}
      else clusters.push({x,hits:1});
    }
    // An explicit header can start at a page foot with one complete body row.
    // Headerless continuations still require repeated independent anchors.
    const repeated=clusters.filter(k=>k.hits>=2);
    const found=repeated.length?repeated:header&&!inherited?clusters:[];
    if(found.length!==1)return null;
    anchors.push(found[0].x);
  }
  if(anchors.some((x,i)=>i>0&&x-anchors[i-1]<spacing*.5))return null;
  if(inherited&&anchors.some((x,i)=>Math.abs(x-inherited.anchors[i])>tolerance))return null;
  const amounts:{text:string;cells?:(string|null)[];label?:string;unitEvidence?:string}[]=[];
  for(const row of candidates){
    const cells:(TextItem|null)[]=Array(count).fill(null);let ambiguous=false;
    for(const item of row.items){if(!numeric.test(item.str.trim()))continue;const x=item.transform[4]+item.width,index=anchors.findIndex(a=>Math.abs(a-x)<=tolerance);if(index<0)continue;if(cells[index]){ambiguous=true;break;}cells[index]=item;}
    if(ambiguous)continue;
    const label=row.items.filter(i=>i.transform[4]+i.width<anchors[0]-spacing*.55).map(i=>i.str).join(' ').trim();
    if(!/[\u4e00-\u9fff]/.test(label))continue;
    // An EPS section's explicit currency unit applies only to its basic/diluted
    // child rows in this same table, before the next numbered section.
    const preceding=rows.filter(r=>r.y>row.y).reverse();
    const section=preceding.find(r=>/^(?:[一二三四五六七八九十]+[、.．]|\d+[、.．])/.test(r.text.replace(/\s/g,'')));
    const labelX=Math.min(...row.items.filter(i=>/[\u4e00-\u9fff]/.test(i.str)&&i.transform[4]<anchors[0]-spacing*.55).map(i=>i.transform[4]));
    const sectionX=section?Math.min(...section.items.map(i=>i.transform[4])):Infinity;
    const unitEvidence=/^(?:[（(][一二][）)])?(?:基本|稀释)每股收益$/.test(label.replace(/\s/g,''))&&section&&labelOnly(section)&&labelX-sectionX>=-2&&labelX-sectionX<=40&&/^[一二三四五六七八九十]+[、.．]每股收益[（(]人民币元[）)]$/.test(section.text.replace(/[\s|]/g,''))?section.text:undefined;
    if(cells.some(c=>c===null)){
      // A joint group/bank statement may disclose EPS only for one scope.
      // Retain two aligned year cells only with an explicit EPS unit and an
      // entirely blank other scope; never shift or synthesise missing values.
      const oneScope=count===4&&((cells[0]&&cells[1]&&!cells[2]&&!cells[3])||(!cells[0]&&!cells[1]&&cells[2]&&cells[3]));
      if(!oneScope||!/每\s*股\s*收\s*益/.test(label)||!/[（(]\s*(?:人\s*民\s*币\s*)?元(?:\s*\/\s*股)?\s*[）)]/.test(label)&&!unitEvidence)continue;
      const values=cells.map(c=>c?.str.trim()??null);
      amounts.push({label,cells:values,unitEvidence,text:label+' |'+values.map(v=>v??'〔原单元格空白〕').join(' |')});continue;
    }
    amounts.push({unitEvidence,text:label+' |'+cells.map(c=>c!.str.trim()).join(' |')});
  }
  return {rows:amounts,geometry:{years,anchors,periods:resolvedPeriods??(header?columnPeriods(rows,years):inherited?.periods),annualRelativeBalances:resolvedPeriods?true:!header&&inherited?.annualRelativeBalances||undefined},header};
}
// Relative balance captions are meaningful only with one explicit annual
// closing date. Keep the original text/items intact; derived column dates
// retain provenance and still require independently observed money anchors.
function relativeBalanceHeader(rows:LayoutLine[]){
  const headers=rows.filter(r=>r.items.some(i=>/^(?:期[末初]余额|[本上]年年末余额)$/.test(i.str.replace(/\s/g,''))));
  if(!headers.length)return {state:'absent' as const};
  if(headers.length!==1)return {state:'invalid' as const};
  const header=headers[0],captions=header.items.filter(i=>/^(?:期[末初]余额|[本上]年年末余额)$/.test(i.str.replace(/\s/g,''))).sort((a,b)=>a.transform[4]-b.transform[4]);
  if(captions.length!==2||!['期末余额,期初余额','本年年末余额,上年年末余额'].includes(captions.map(i=>i.str.replace(/\s/g,'')).join(',')))return {state:'invalid' as const};
  const body=rows.find(r=>r.y<header.y&&r.items.some(i=>/[\u4e00-\u9fff]/.test(i.str))&&r.items.filter(i=>numeric.test(i.str.trim())).length>=2);
  const headerRows=rows.filter(r=>r.y>(body?.y??-Infinity));
  return {state:'valid' as const,header,captions,headerRows};
}
function relativePeriodsAgree(meta:ReturnType<typeof relativeBalanceHeader>,periods:string[]){
  if(meta.state!=='valid'||periods.length!==2||!periods.every(p=>/^20\d{2}-12-31$/.test(p))||Number(periods[0].slice(0,4))-1!==Number(periods[1].slice(0,4)))return false;
  const above=meta.headerRows.filter(r=>r.y>meta.header.y+2).map(r=>r.text).join('\n');
  if(/半年度|季度|六个月/.test(above)||sourcePeriods(above).some(p=>p!==periods[0]&&p!==periods[0].slice(0,4)))return false;
  // Include layered date captions BELOW the relative heading, but never body
  // notes. Derived dates may fill missing metadata, not replace explicit dates.
  const centers=meta.captions.map(i=>i.transform[4]+i.width/2),mid=(centers[0]+centers[1])/2;
  const layered=meta.headerRows.filter(r=>r.y<=meta.header.y+2);
  if(!layered.every(r=>r.items.every(i=>{
    const stated=sourcePeriods(i.str);if(!stated.length)return true;
    const c=i.transform[4]+i.width/2<mid?0:1;
    return stated.every(p=>p===periods[c]||p===periods[c].slice(0,4));
  })))return false;
  return periods.every((period,c)=>{
    const fragments=layered.flatMap(r=>r.items).filter(i=>(i.transform[4]+i.width/2<mid?0:1)===c&&/^[\d年月日度\s-]+$/.test(i.str)).map(i=>i.str).join('').replace(/\s/g,'');
    if(sourcePeriods(fragments).some(p=>p!==period&&p!==period.slice(0,4)))return false;
    return [...fragments.matchAll(/(\d{1,2})月(\d{1,2})日/g)].every(m=>Number(m[1])===12&&Number(m[2])===31);
  });
}
export function bindAnnualBalanceRows(rows:LayoutLine[]):ReturnType<typeof bindAtHeader>{
  const meta=relativeBalanceHeader(rows);if(meta.state!=='valid')return null;
  const {header,captions}=meta;
  const above=rows.filter(r=>r.y>header.y+2).map(r=>r.text).join('\n'),stated=sourcePeriods(above);
  const dates=[...new Set(stated.filter(p=>p.length===10))];
  if(stated.includes('invalid')||dates.length!==1||!dates[0].endsWith('-12-31')||/半年度|季度|六个月/.test(above))return null;
  const year=Number(dates[0].slice(0,4)),periods=[dates[0],`${year-1}-12-31`];
  if(!relativePeriodsAgree(meta,periods))return null;
  const derived=captions.map((caption,i)=>({...caption,str:`${year-i}年`,transform:[...caption.transform]}));
  const bound=bindAtHeader(rows,2,header,derived,undefined,periods);
  if(bound)bound.geometry.annualRelativeBalances=captions[0].str.replace(/\s/g,'')==='期末余额'||undefined;
  return bound;
}
// Relative annual flows require an independently dated full-year heading.
// A report year, quarter or a balance-sheet date alone cannot supply it.
export function bindAnnualFlowRows(rows:LayoutLine[]):ReturnType<typeof bindAtHeader>{
  const headers=rows.filter(r=>r.items.some(i=>/^[本上]年发生额$/.test(i.str.replace(/\s/g,''))));
  if(headers.length!==1)return null;
  const header=headers[0],captions=header.items.filter(i=>/^[本上]年发生额$/.test(i.str.replace(/\s/g,''))).sort((a,b)=>a.transform[4]-b.transform[4]);
  if(captions.length!==2||captions.map(i=>i.str.replace(/\s/g,'')).join(',')!=='本年发生额,上年发生额')return null;
  const above=rows.filter(r=>r.y>header.y+2).map(r=>r.text).join('\n').replace(/[\s|]/g,'');
  if(/半年度|季度|六个月/.test(above))return null;
  const annual=[...above.matchAll(/(20\d{2})年12月31日止年度/g)];
  const stated=sourcePeriods(above),dates=[...new Set(stated.filter(p=>p.length===10))];
  if(annual.length!==1||dates.length!==1||dates[0]!==`${annual[0][1]}-12-31`||stated.includes('invalid')||stated.some(p=>p!==dates[0]&&p!==annual[0][1]))return null;
  // Reject extra layered dates instead of overriding their column semantics.
  const body=rows.find(r=>r.y<header.y&&r.items.some(i=>/[\u4e00-\u9fff]/.test(i.str))&&r.items.filter(i=>numeric.test(i.str.trim())).length>=2);
  if(rows.some(r=>r.y<=header.y+2&&r.y>(body?.y??-Infinity)&&sourcePeriods(r.text).length))return null;
  const year=Number(annual[0][1]),derived=captions.map((caption,i)=>({...caption,str:`${year-i}年`,transform:[...caption.transform]}));
  const bound=bindAtHeader(rows,2,header,derived,undefined,[String(year),String(year-1)]);
  if(bound)bound.geometry.annualRelativeBalances=undefined;
  return bound;
}
export function bindFinancialRows(rows:LayoutLine[],count:number,inherited?:ColumnGeometry):ReturnType<typeof bindAtHeader>{
  if(rows.some(r=>r.items.some(i=>/^[本上]年发生额$/.test(i.str.replace(/\s/g,'')))))return null;
  const relative=relativeBalanceHeader(rows);
  if(relative.state!=='absent'){
    if(relative.state!=='valid'||count!==2||!inherited||!relativePeriodsAgree(relative,inherited.periods??[]))return null;
    // A continuation may not change year-end captions into opening balances
    // (or the reverse) by borrowing the predecessor's date/alias metadata.
    if((relative.captions[0].str.replace(/\s/g,'')==='期末余额')!==!!inherited.annualRelativeBalances)return null;
    const bound=bindAtHeader(rows,count,relative.header,inherited.years,inherited,inherited.periods);
    if(bound)bound.geometry.annualRelativeBalances=relative.captions[0].str.replace(/\s/g,'')==='期末余额'||undefined;
    return bound;
  }
  const aligned=rows.find(r=>r.items.filter(yearItem).length===count);
  if(aligned)return bindAtHeader(rows,count,aligned,aligned.items.filter(yearItem),inherited);
  // Wrapped/restated column captions need not have the same y coordinate.
  // Every proposed year column must still reproduce an independent money anchor.
  const upper=rows.slice(0,24),yearRows=upper.filter(r=>r.items.some(yearItem));
  const candidates:NonNullable<ReturnType<typeof bindAtHeader>>[]=[];
  for(let a=0;a<yearRows.length;a++)for(let b=a;b<yearRows.length;b++){
    if(yearRows[a].y-yearRows[b].y>30)break;
    const nearby=yearRows.filter(r=>r.y<=yearRows[a].y+30&&r.y>=yearRows[b].y-30);
    const years=nearby.flatMap(r=>r.items.filter(yearItem)).sort((x,y)=>x.transform[4]-y.transform[4]);
    if(years.length!==count)continue;
    const header=nearby.at(-1)!;
    const bound=bindAtHeader(rows,count,header,years,inherited);
    if(bound&&!candidates.some(v=>JSON.stringify(v.geometry.years)===JSON.stringify(bound.geometry.years)))candidates.push(bound);
  }
  if(candidates.length===1)return candidates[0];
  if(candidates.length>1)return null;
  return inherited?bindAtHeader(rows,count,undefined,inherited.years,inherited):null;
}
export function financialLayoutRows(items:TextItem[],count:number):{text:string}[]{
  return bindFinancialRows(positionedLines(items),count)?.rows??[];
}
