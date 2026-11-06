import { Archive, ChartNoAxesCombined, FileText, SlidersHorizontal } from 'lucide-react';
import type { State } from './risk-state';

export type ResearchStage='source'|'assumptions'|'projection'|'archive';
const stages=[
  {id:'source' as const,label:'资料',Icon:FileText,start:270},
  {id:'assumptions' as const,label:'假设',Icon:SlidersHorizontal,start:0},
  {id:'projection' as const,label:'推演',Icon:ChartNoAxesCombined,start:90},
  {id:'archive' as const,label:'归档',Icon:Archive,start:180},
];
function polar(radius:number,degrees:number){const a=(degrees-90)*Math.PI/180;return [140+radius*Math.cos(a),140+radius*Math.sin(a)];}
function segment(start:number){
  const [a,b,c,d]=[polar(126,start+2),polar(126,start+88),polar(66,start+88),polar(66,start+2)];
  return `M${a} A126,126 0 0,1 ${b} L${c} A66,66 0 0,0 ${d} Z`;
}
export function ResearchWheel({state,valid,fresh,registered,active,onPick}:{state:State;valid:boolean;fresh:boolean;registered:boolean;active:ResearchStage;onPick:(stage:ResearchStage)=>void}){
  const statuses={source:registered?'已登记':'历史快照',assumptions:valid?'已设置':'待设置',projection:state.calculating?'计算中':fresh?'已计算':state.result?'待更新':'待推演',archive:state.saving?'保存中':state.saved?'已保存':'待归档'};
  return <div className="research-wheel">
    <svg viewBox="8 8 264 264" role="group" aria-label="研究路径：资料、假设、推演、归档">
      <defs><radialGradient id="wheel-core"><stop stopColor="#182934"/><stop offset="1" stopColor="#0b141d"/></radialGradient></defs>
      {stages.map(({id,label,Icon,start})=>{
        const [x,y]=polar(96,start+45),angle=(start-45)*Math.PI/180;
        return <g key={id} role="button" tabIndex={0} aria-label={`打开${label}环节：${statuses[id]}`} aria-pressed={active===id}
          className={`wheel-segment stage-${id} ${active===id?'is-active':''}`}
          style={{'--segment-x':`${Math.cos(angle)*3}px`,'--segment-y':`${Math.sin(angle)*3}px`} as React.CSSProperties}
          onClick={()=>onPick(id)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();onPick(id);}}}>
          <path d={segment(start)}/><Icon x={x-10} y={y-31} width={20} height={20} strokeWidth={1.5}/>
          <text x={x} y={y+7} textAnchor="middle" className="wheel-label">{label}</text>
          <text x={x} y={y+26} textAnchor="middle" className="wheel-status">{statuses[id]}</text>
        </g>;
      })}
      <circle cx="140" cy="140" r="60" fill="url(#wheel-core)" className="wheel-center"/>
      <text x="140" y="136" textAnchor="middle" className="wheel-center-title">研究路径</text>
      <text x="140" y="155" textAnchor="middle" className="wheel-center-caption">点击环节继续</text>
    </svg>
  </div>;
}
