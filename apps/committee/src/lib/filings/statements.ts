import {sourcePeriods} from './period.ts';
import type {Page,Fact} from './core.ts';
import {positionedLines,bindFinancialRows,bindAnnualBalanceRows,bindAnnualFlowRows,type ColumnGeometry,type LayoutLine} from './layout.ts';
import {financialSection} from './labels.ts';
export type StatementBlock={
  id:string;page:number;name:string;entity:string|null;unit:string|null;currency?:'人民币'|null;
  columns:{year:number;scope:Fact['scope'];period?:string;periodAliases?:string[]}[];rows:{text:string;cells?:(string|null)[];label?:string;unitEvidence?:string}[];
  headerSourceIds:string[];status:'parsed'|'unresolved';gap?:string;geometry?:ColumnGeometry;
  headerRelation?:'own'|'named_continuation'|'structural_continuation';
  annualPeriodConfirmed?:boolean;
  headerEvidence?:HeaderEvidence[];
};
export type HeaderEvidence={sourceId:string;page:number;text:string;relation:'own'|'inherited';lines?:{text:string;y:number;cells:{text:string;x:number;y:number;width:number}[]}[]};
const compact=(s:string)=>s.replace(/[\s|]/g,'');
const title=/合并(资产负债表|利润表|损益表|现金流量表)(?:和|及)\1|(合并及(?:母公司|本公司|本行|银行|公司)|合并|母公司|银行|公司)(资产负债表|利润表|损益表|现金流量表)/;
const joint=(name:string)=>name.startsWith('合并及')||/(?:和|及)(?:资产负债表|利润表|损益表|现金流量表)$/.test(name);
function scopeConflict(text:string,name:string){
  if(joint(name))return false; // Four-column ordering is checked separately.
  const header=text.split('\n').filter(l=>!title.test(compact(l))).join('\n');
  return name.startsWith('合并')?/母公司|本银行|本公司|本行/.test(header):/本集团|合并/.test(header);
}
function declaredUnit(text:string):{unit:string|null;invalid:boolean}{
  const t=text.replace(/\|/g,' ');
  if([...t.matchAll(/币种\s*[:：]\s*([^\n（）()]+)/g)].some(m=>m[1].trim()!=='人民币'))return {unit:null,invalid:true};
  const explicit=[...t.matchAll(/(?<!编制)单位\s*(?:均?为|[:：])\s*([^\s，,（）()]+)/g)].map(m=>m[1]);
  if(explicit.some(u=>!/^(?:人民币)?(?:百万元|千元|万元|亿元|元)(?:人民币)?$/.test(u)))return {unit:null,invalid:true};
  const declarations=[...t.matchAll(/(?:金额单位\s*(?:均?为|[:：])?|单位\s*(?:均?为|[:：])|人民币)\s*(?:人民币\s*)?(百万元|千元|万元|亿元|元)(?:人民币)?(?![\u4e00-\u9fff/])/g)].map(m=>m[1]);
  declarations.push(...[...t.matchAll(/以人民币\s*(百万元|千元|万元|亿元|元)列示(?=[\s，,（）()]|$)/g)].map(m=>m[1]));
  const units=[...new Set(declarations)];
  return {unit:units.length===1?units[0]:null,invalid:units.length>1||(!units.length&&/(?:金额单位|单位[:：]|人民币)/.test(t))};
}
function columns(text:string,name:string,geometry?:ColumnGeometry,headerLines?:LayoutLine[]):StatementBlock['columns']{
  const n=joint(name)?4:2;
  let years:number[]=[];
  if(geometry)years=geometry.years.map(i=>Number(i.str.trim().slice(0,4)));
  else for(const line of text.split('\n')){const ys=[...line.matchAll(/(20\d{2})[\s|]*年/g)].map(m=>Number(m[1]));if(ys.length===n){years=ys;break;}}
  const dateRow=text.split('\n').map(sourcePeriods).find(ps=>ps.length===n);
  let periods=geometry?.periods??dateRow??years.map(String);
  // Annual balance sheets may print the complete closing date above columns
  // captioned only with years. Bind that actual local heading, never the
  // report year; interim dates and explicit column dates remain untouched.
  const headingDates=[...new Set(text.split('\n').flatMap(line=>{
    const ps=sourcePeriods(line);return ps.length===1&&/^20\d{2}-\d{2}-\d{2}$/.test(ps[0])?ps:[];
  }))];
  if(n===2&&name.endsWith('资产负债表')&&periods.every(p=>/^20\d{2}$/.test(p))&&
    headingDates.length===1&&headingDates[0]===`${years[0]}-12-31`&&years[1]===years[0]-1){
    periods=years.map(year=>`${year}-12-31`);
  }
  if(years.length!==n||periods.includes('invalid')||periods.some((p,i)=>Number(p.slice(0,4))!==years[i]))return [];
  if(n===2&&new Set(periods).size!==2)return [];
  if(n===4&&(periods[0]===periods[1]||periods[0]!==periods[2]||periods[1]!==periods[3]))return [];
  const scope:Fact['scope']=name.startsWith('合并')?'consolidated':'parent';
  if(n===2)return years.map((year,i)=>({year,scope,period:periods[i],...(geometry?.annualRelativeBalances&&i===1?{periodAliases:[`${year+1}-01-01`]}:{})}));
  const header=text.split('\n').filter(l=>!title.test(compact(l))).join('\n');
  // Scope captions are standalone header cells, never issuer names or words
  // inside a body label such as "归属于母公司股东".
  const scopeToken=/^(?:本集团|本银行|本行|本公司|母公司|合并|公司|银行)$/;
  const markerCells=headerLines?.filter(l=>!title.test(compact(l.text))).flatMap(l=>l.items.filter(i=>scopeToken.test(compact(i.str)))).sort((a,b)=>a.transform[4]-b.transform[4]);
  let markers=(markerCells?.map(i=>compact(i.str))??header.split('\n').flatMap(l=>l.split(/\s*\|\s*|\s+/).filter(s=>scopeToken.test(s)))).map(s=>s==='本集团'||s==='合并'?'consolidated':'parent');
  if(geometry&&markerCells?.length){
    const centers=geometry.years.map(i=>i.transform[4]+i.width/2),spacing=Math.min(...centers.slice(1).map((x,i)=>x-centers[i]));
    if(markerCells.some(i=>{const x=i.transform[4]+i.width/2;return x<centers[0]-spacing/2||x>centers.at(-1)!+spacing/2;}))return [];
  }
  if(geometry&&markerCells?.length===4){
    const centers=geometry.years.map(i=>i.transform[4]+i.width/2);
    const assigned=markerCells.map(i=>{const x=i.transform[4]+i.width/2;return centers.reduce((best,c,j)=>Math.abs(c-x)<Math.abs(centers[best]-x)?j:best,0);});
    // Each explicit caption must bind to a distinct monetary/year column.
    if(assigned.some((c,i)=>c!==i))return [];
  }
  if(geometry&&markerCells?.length===2){
    const centers=geometry.years.map(i=>i.transform[4]+i.width/2),mid=(centers[1]+centers[2])/2;
    if(markerCells[0].transform[4]+markerCells[0].width/2>=mid||markerCells[1].transform[4]+markerCells[1].width/2<=mid)return [];
  }
  if(!markers.length){
    // Named captions must explicitly pair the SAME issuer with its group.
    // A generic first-two-columns assumption would silently swap scopes.
    const pairs=header.split('\n').map(l=>l.split(/\s*\|\s*|\s{2,}/).map(compact)).filter(parts=>parts.length===2&&parts[0].endsWith('集团')&&parts[0].slice(0,-2).length>=2&&parts[0].slice(0,-2)===parts[1]);
    if(pairs.length===1){
      if(geometry){
        const positioned=headerLines?.map(l=>l.items.filter(i=>pairs[0].includes(compact(i.str)))).find(items=>items.length===2&&compact(items[0].str)===pairs[0][0]&&compact(items[1].str)===pairs[0][1]);
        if(!positioned)return [];
        const centers=geometry.years.map(i=>i.transform[4]+i.width/2),spacing=Math.min(...centers.slice(1).map((x,i)=>x-centers[i])),mid=(centers[1]+centers[2])/2;
        const [a,b]=positioned.map(i=>i.transform[4]+i.width/2);
        if(a<centers[0]-spacing/2||a>=mid||b<=mid||b>centers.at(-1)!+spacing/2)return [];
      }
      markers=['consolidated','parent'];
    }
  }
  if(!['consolidated,parent','consolidated,consolidated,parent,parent'].includes(markers.join(','))||years[0]!==years[2]||years[1]!==years[3])return [];
  return years.map((year,i)=>({year,scope:i<2?'consolidated':'parent',period:periods[i]}));
}
export function extractStatementBlocks(pages:Page[],sha256:string):StatementBlock[]{
  const blocks:StatementBlock[]=[];
  for(let pageIndex=0;pageIndex<pages.length;pageIndex++){
    const p=pages[pageIndex],sid=`pdf:${sha256}:p${p.page}`;
    const lines:LayoutLine[]=p.layoutItems?positionedLines(p.layoutItems):p.text.split('\n').map((text,i)=>({text,y:-i,items:[]}));
    const starts=lines.flatMap((l,i)=>title.test(compact(l.text))?[i]:[]);
    const prior=blocks.at(-1);
    // A missing table title is not enough. Recognise a narrow, ordered section
    // bridge in addition to entity, physical adjacency and independent anchors.
    const previousTail=compact(prior?.rows.at(-1)?.text.split('|')[0]??'');
    const bodyHead=lines.find(l=>!/^.*(?:公司|年度报告)/.test(compact(l.text))&&/[\u4e00-\u9fff]/.test(l.text));
    const nextHead=compact(bodyHead?.text??'');
    const bridge=!!prior&&((prior.name.endsWith('资产负债表')&&previousTail==='资产总计'&&/^(?:流动负债|负债)[:：]?/.test(nextHead))||
      (/(?:利润表|损益表)$/.test(prior.name)&&/营业利润/.test(previousTail)&&/^加[:：]营业外收入/.test(nextHead))||
      (prior.name.endsWith('现金流量表')&&/经营活动产生的现金流量净额/.test(previousTail)&&/^二[、.]投资活动产生的现金流量/.test(nextHead)));
    const entityLines=lines.slice(0,starts[0]??3);
    const issuerCells=[...new Set([...entityLines.flatMap(l=>l.items).map(i=>i.str),...entityLines.map(l=>l.text)].map(s=>compact(s).replace(/20\d{2}年(?:年度|半年度|季度)?报告(?:[（(][^（）()]*[）)])?$/,'')).filter(t=>/^[\u4e00-\u9fffA-Za-z（）()]+(?:公司|银行)$/.test(t)&&!['公司','母公司','本公司','银行','本银行','本行'].includes(t)))];
    const entity=p.layoutItems?(issuerCells.length===1?issuerCells[0]:null):entityLines.map(l=>compact(l.text)).find(t=>/公司|银行/.test(t))?.replace(/20\d{2}年.*$/,'')??null;
    const adjacentPage=pageIndex>0&&pages[pageIndex-1].page+1===p.page&&p.physicalPageDeclared===true&&pages[pageIndex-1].physicalPageDeclared===true;
    const prefix=lines.slice(0,starts[0]??lines.length);
    const boundPrefix=p.layoutItems&&prior?.geometry?bindFinancialRows(prefix,prior.columns.length,prior.geometry):null;
    const previousRank=prior?.rows.map(r=>financialSection(prior.name,r.text.split('|')[0])).filter(r=>r!==null).at(-1);
    const nextRank=boundPrefix?.rows.map(r=>financialSection(prior!.name,r.text.split('|')[0])).find(r=>r!==null);
    const repeatedRow=boundPrefix?.rows[0],repeat=prior?.rows.slice(-6).find(r=>compact(r.text)===compact(repeatedRow?.text??''));
    const repeatRank=repeat&&prior?financialSection(prior.name,repeat.text.split('|')[0]):null;
    const followingRanks=boundPrefix?.rows.slice(1).map(r=>financialSection(prior!.name,r.text.split('|')[0])).filter((r):r is number=>r!==null)??[];
    // Some financial reports repeat the exact net-profit subtotal on the
    // next page after EPS. Exact row/amount overlap proves this narrow reset;
    // a changed value or a subsequent earlier section cannot establish it.
    const comprehensiveReset=!!prior&&/(?:利润表|损益表)$/.test(prior.name)&&previousRank===8&&repeatRank===5&&compact(repeat?.text.split('|')[0]??'')==='净利润'&&followingRanks[0]===7&&prefix.some(l=>/其他综合收益/.test(l.text));
    // Credit-loss components can occur inside OCI; the lexical section helper
    // alone cannot classify these subrows as a return to operating gains.
    const overlap=comprehensiveReset&&boundPrefix!.rows.slice(1).every(row=>{
      const r=financialSection(prior!.name,row.text.split('|')[0]);
      return r===null||r>=5||r===1&&/^(?:[－\-—])?(?:分类为以公允价值计量且其变动计入其他综合收益的)?金融资产信用损失准备$/.test(compact(row.label??row.text.split('|')[0]));
    });
    const ordered=previousRank!==undefined&&previousRank!==null&&nextRank!==undefined&&nextRank!==null&&(nextRank>=previousRank||overlap);
    const firstMoney=prefix.findIndex(l=>l.items.filter(i=>/^(?:\(?-?\d[\d,.，]*\)?|[-–—])$/.test(i.str.trim())&&prior?.geometry?.anchors.some(a=>Math.abs(a-i.transform[4]-i.width)<=8)).length>=2);
    const heading=prefix.slice(0,firstMoney<0?prefix.length:firstMoney);
    const unsafeHeading=heading.some(l=>/不明|未知|注释|说明|表格/.test(l.text)||/附注/.test(l.text)&&!l.items.every(i=>/^(?:项目|附注|20\d{2}年|\d{1,2}月\d{1,2}日)$/.test(compact(i.str))));
    const continuing=!!prior&&prior.status==='parsed'&&!!boundPrefix&&boundPrefix.rows.length>=2&&ordered&&!unsafeHeading;
    const titleCarry=!!prior&&prior.name!=='未识别表块'&&prior.rows.length===0&&prior.gap==='缺少可独立确认的单位/年度/范围；续表关系未证实'&&prefix.some(l=>l.items.filter(i=>/^20\d{2}(?:\s*年.*)?$/.test(i.str.trim())).length===(joint(prior.name)?4:2));
    const implicit=!!p.layoutItems&&adjacentPage&&entity!==null&&prior?.entity===entity&&(bridge||continuing||titleCarry);
    if(implicit)starts.unshift(0);
    if(starts.length===0){blocks.push({id:`${sid}:s0`,page:p.page,name:'未识别表块',entity,unit:null,columns:[],rows:[],headerSourceIds:[],status:'unresolved',gap:'缺少报表标题，不能证实续表关系'});continue;}
    for(let k=0;k<starts.length;k++){
      const prefixBlock=implicit&&k===0;
      const part=lines.slice(starts[k],starts[k+1]??lines.length),name=prefixBlock?prior!.name:compact(part[0].text).match(title)![0];
      const block:StatementBlock={id:`${sid}:s${k+1}`,page:p.page,name,entity,unit:null,columns:[],rows:[],headerSourceIds:[],status:'unresolved'};
      const n=joint(name)?4:2;
      // Only an immediately adjacent pure dated heading may precede a title.
      // Never borrow a report year or an earlier table's metadata.
      const preceding:LayoutLine[]=[];
      if(!prefixBlock){let next=part[0];for(let j=starts[k]-1;j>=Math.max(0,starts[k]-2);j--){const row=lines[j],text=compact(row.text);if(next.y-row.y>0||row.y-next.y>50||!/^20\d{2}年\d{1,2}月\d{1,2}日(?:止年度)?$/.test(text))break;preceding.unshift(row);next=row;}}
      const contextual=[...preceding,...part];
      const ownLayout=p.layoutItems?(bindFinancialRows(contextual,n)??(!joint(name)?name.endsWith('资产负债表')?bindAnnualBalanceRows(contextual):/(?:利润表|损益表|现金流量表)$/.test(name)?bindAnnualFlowRows(contextual):null:null)):null;
      const headerEnd=ownLayout?.header?part.findIndex(l=>l===ownLayout.header)+1:Math.min(28,part.length);
      const bodyIndex=part.findIndex(l=>/[\u4e00-\u9fff]/.test(l.text)&&/(?:\(?-?\d[\d,.，]*\)?|[-–—])[\s|]+(?:\(?-?\d[\d,.，]*\)?|[-–—])[\s|]*$/.test(l.text)&&!/20\d{2}[\s|]*年/.test(l.text));
      const headerLines=[...preceding,...part.slice(0,bodyIndex>=0?bodyIndex:headerEnd)];
      const headerText=headerLines.map(l=>l.text).join('\n');
      const periodContext=compact(headerText),pageHeading=compact(lines.slice(0,starts[0]??3).map(l=>l.text).join(''));
      const interim=/半年度|半年度报告|季度|六个月|1[—–－\-至]6月/.test(periodContext+pageHeading);
      const ownAnnual=!interim&&/20\d{2}年度(?!报告)|20\d{2}年1[—–－\-至]12月|20\d{2}年12月31日止年度/.test(periodContext);
      const unit=declaredUnit(headerText),ownCols=columns(headerText,name,ownLayout?.geometry,p.layoutItems?headerLines:undefined);
      const prev=blocks.at(-1),continuation=prefixBlock||/续/.test(compact(part[0].text));
      const adjacent=pageIndex>0&&pages[pageIndex-1].page+1===p.page&&p.physicalPageDeclared===true&&pages[pageIndex-1].physicalPageDeclared===true;
      const canInherit=continuation&&adjacent&&k===0&&entity!==null&&prev?.entity===entity&&prev?.page===p.page-1&&prev?.name===name&&prev?.status==='parsed'&&!!prev.geometry;
      block.annualPeriodConfirmed=ownAnnual||!interim&&canInherit&&prev?.annualPeriodConfirmed===true;
      if(unit.invalid){block.gap='单位声明冲突或不支持';blocks.push(block);continue;}
      if(ownLayout?.geometry.periods?.includes('invalid')){block.gap='同列日期或年度冲突，不能由前表覆盖修复';blocks.push(block);continue;}
      if(scopeConflict(headerText,name)){block.gap='表头范围与报表标题/前表范围冲突';blocks.push(block);continue;}
      const explicitYearRow=p.layoutItems?part.some(l=>l.items.filter(i=>/^20\d{2}(?:\s*年.*)?$/.test(i.str.trim())).length===n):headerText.split('\n').some(l=>[...l.matchAll(/20\d{2}[\s|]*年/g)].length===n);
      const statedYears=[...headerText.matchAll(/(20\d{2})[\s|]*年/g)].map(m=>Number(m[1]));
      // Invalid explicit metadata is different from absence; neither a bad
      // year header nor reversed scope captions may be repaired by inheritance.
      if(explicitYearRow&&!ownCols.length){block.gap='已提供的年度/范围列冲突或不能确认';blocks.push(block);continue;}
      if(canInherit&&!ownCols.length&&sourcePeriods(headerText).some(p=>p.length>4)){block.gap='续表仅有部分日期表头，不能证实与前表列顺序一致';blocks.push(block);continue;}
      if(canInherit&&!ownCols.length&&statedYears.some(y=>!prev.columns.some(c=>c.year===y))){block.gap='续表明示年度与前表冲突';blocks.push(block);continue;}
      if(continuation&&adjacent&&k===0&&prev?.status==='parsed'&&prev.name===name&&prev.entity===entity&&((unit.unit&&unit.unit!==prev.unit)||(ownCols.length&&JSON.stringify(ownCols)!==JSON.stringify(prev.columns)))){block.gap='续表明示单位/年度/范围与前表冲突';blocks.push(block);continue;}
      let inherited:ReturnType<typeof bindFinancialRows>=null;
      if(canInherit&&p.layoutItems){
        const agree=(!unit.unit||unit.unit===prev.unit)&&(!ownCols.length||JSON.stringify(ownCols)===JSON.stringify(prev.columns));
        if(agree)inherited=bindFinancialRows(part,n,prev.geometry);
      }
      const complete=!!unit.unit&&ownCols.length===n;
      if(complete){block.unit=unit.unit;block.columns=ownCols;block.headerSourceIds=prefixBlock?[...new Set([...(prev?.headerSourceIds.length?prev.headerSourceIds:[`pdf:${sha256}:p${prev!.page}`]),sid])]:[sid];block.headerRelation=prefixBlock?'structural_continuation':'own';}
      else if(inherited&&prev){block.unit=unit.unit??prev.unit;block.columns=ownCols.length?ownCols:prev.columns;block.headerSourceIds=[...new Set([...prev.headerSourceIds,...(unit.unit||ownCols.length?[sid]:[])])];block.headerRelation=prefixBlock?'structural_continuation':'named_continuation';}
      else {block.gap='缺少可独立确认的单位/年度/范围；续表关系未证实';blocks.push(block);continue;}
      block.currency=/人民币/.test(headerText)?'人民币':inherited?prev?.currency??null:null;
      if(p.layoutItems){
        const bound=complete?ownLayout:inherited;
        if(!bound){block.gap='金额列坐标不完整或存在歧义';blocks.push(block);continue;}
        block.rows=bound.rows;block.geometry=bound.geometry;
      }else if(p.layoutRows!==undefined){
        if(starts.length!==1){block.gap='旧行坐标不能定位同页多个表块';blocks.push(block);continue;}
        block.rows=p.layoutRows;
      }else{
        if(/附注/.test(headerText)){block.gap='存在附注列，缺少金额列坐标';blocks.push(block);continue;}
        block.rows=part.map(l=>({text:l.text}));
      }
      block.status='parsed';blocks.push(block);
      // Capture the same coordinate channel that resolved the columns. Do not
      // reverse-search formatted money rows in the unrelated plain-text channel.
      const ownHeaderLines=[...(k===0&&!prefixBlock?entityLines:[]),...headerLines];
      const text=ownHeaderLines.map(l=>l.text).join('\n').trim();
      const own:HeaderEvidence[]=text?[{sourceId:sid,page:p.page,text,relation:'own',lines:ownHeaderLines.map(l=>({text:l.text,y:l.y,cells:l.items.map(i=>({text:i.str,x:i.transform[4],y:i.transform[5],width:i.width}))}))}]:[];
      const inheritedHeaders=block.headerSourceIds.filter(id=>id!==sid).flatMap(id=>(prev?.headerEvidence??[]).filter(h=>h.sourceId===id).map(h=>({...h,relation:'inherited' as const})));
      block.headerEvidence=[...inheritedHeaders,...own];
    }
  }
  return blocks;
}
