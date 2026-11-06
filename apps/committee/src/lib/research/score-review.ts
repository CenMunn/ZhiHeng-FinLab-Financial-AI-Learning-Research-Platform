import type { AgentDTO } from '@/lib/types'
import { safeSourceUrl } from '@/lib/research-evidence/engine'
export type ReviewAction='ai_rescore'|'accept_ai'|'manual_adjust'
export interface SupplementInput {text:string;source:string;locator:string;period:string;checked:boolean}
export interface ScoreReviewRequest {action:ReviewAction;agentId:string;expectedRevision:number;score?:number;confidence?:number;reason:string;proposalId?:string;supplement?:SupplementInput}
export interface ReviewActor {id:string;username:string;displayName:string}
export interface ConditionalProposal {score:number;confidence:number;reason:string;sourceIds:string[];informationSufficient:boolean}
export interface ScoreSnapshot {score:number|null;confidence:number|null;basis:string;reason:string;kind:string}
export interface ScoreSupplement extends SupplementInput {id:string;origin:'user_supplied';submittedBy:ReviewActor;at:string;checkedBy:string|null}
export interface ScoreReviewEntry {id:string;at:string;actor:ReviewActor;action:ReviewAction;before:ScoreSnapshot;after:ScoreSnapshot;reason:string;proposal?:ConditionalProposal;rawCandidate?:unknown;calls:unknown[];supplementId?:string}
export interface ScoreReviewState {original:ScoreSnapshot;proposal:(ConditionalProposal&{id:string;at:string})|null;supplements:ScoreSupplement[];history:ScoreReviewEntry[];confirmedBy?:ReviewActor}
export class ScoreReviewError extends Error {constructor(message:string,public status=400){super(message)}}
function text(v:unknown,max:number){return typeof v==='string'?v.trim().slice(0,max):''}
function integer(v:unknown){return typeof v==='number'&&Number.isInteger(v)&&v>=0&&v<=100}
export function parseScoreReviewRequest(raw:unknown):ScoreReviewRequest {
 if(!raw||typeof raw!=='object')throw new ScoreReviewError('复核内容无效')
 const p=raw as Record<string,unknown>,action=p.action as ReviewAction
 if(!['ai_rescore','accept_ai','manual_adjust'].includes(action)||typeof p.agentId!=='string'||!/^[a-zA-Z0-9_-]{1,100}$/.test(p.agentId))throw new ScoreReviewError('请选择有效角色及操作')
 if(typeof p.expectedRevision!=='number'||!Number.isInteger(p.expectedRevision)||p.expectedRevision<0)throw new ScoreReviewError('复核版本缺失，请刷新后再试')
 const reason=text(p.reason,1000)
 if(action!=='ai_rescore'&&!reason)throw new ScoreReviewError('请填写复核或调分理由')
 if(action==='manual_adjust'&&(!integer(p.score)||!integer(p.confidence)))throw new ScoreReviewError('分数和置信度必须是0至100的整数')
 if(action==='accept_ai'&&!text(p.proposalId,100))throw new ScoreReviewError('AI候选版本缺失，请刷新后再试')
 let supplement:SupplementInput|undefined
 if(p.supplement){
  if(typeof p.supplement!=='object')throw new ScoreReviewError('补充资料格式无效')
  const s=p.supplement as Record<string,unknown>
  supplement={text:text(s.text,4000),source:text(s.source,500),locator:text(s.locator,200),period:text(s.period,80),checked:s.checked===true}
  if(!supplement.text||!supplement.source||!supplement.locator)throw new ScoreReviewError('请完整填写资料摘录、来源和页码或定位')
  if(/^[a-z][a-z\d+.-]*:/i.test(supplement.source)&&!safeSourceUrl(supplement.source))throw new ScoreReviewError('资料链接仅支持不含凭据的HTTP或HTTPS网址')
 }
 if(action==='accept_ai'&&supplement)throw new ScoreReviewError('资料已有改动，请先重新生成AI候选，或使用人工调整')
 return {action,agentId:p.agentId,expectedRevision:p.expectedRevision,reason,score:p.score as number|undefined,confidence:p.confidence as number|undefined,proposalId:text(p.proposalId,100),supplement}
}
export function validateConditionalProposal(raw:unknown,allowedIds:string[]):ConditionalProposal {
 const p=raw&&typeof raw==='object'?raw as Record<string,unknown>:{}
 const reason=text(p.reason,500)
 if(!integer(p.score)||!integer(p.confidence)||!reason||typeof p.informationSufficient!=='boolean'||!Array.isArray(p.sourceIds)||p.sourceIds.some(id=>typeof id!=='string'||!allowedIds.includes(id)))throw new ScoreReviewError('AI评分结构或来源未通过检查，原评分保留',422)
 if(p.informationSufficient&&(!allowedIds.length||!p.sourceIds.length))throw new ScoreReviewError('AI评分缺少实际资料引用，原评分保留',422)
 return {score:p.informationSufficient?p.score as number:50,confidence:p.informationSufficient?Math.min(40,p.confidence as number):0,reason,sourceIds:[...new Set(p.sourceIds as string[])],informationSufficient:p.informationSufficient}
}
export function scoreSnapshot(a:AgentDTO):ScoreSnapshot{return {score:a.score,confidence:a.confidence,basis:typeof a.details?.scoreBasis==='string'?a.details.scoreBasis:'baseline',reason:typeof a.details?.scoreReason==='string'?a.details.scoreReason:'',kind:typeof a.details?.scoreKind==='string'?a.details.scoreKind:'investment_attractiveness'}}
export function applyScoreReview(input:{agent:AgentDTO;request:ScoreReviewRequest;actor:ReviewActor;at:string;id:string;proposal?:ConditionalProposal;rawCandidate?:unknown;calls?:unknown[]}){
 const {agent,request,actor,at,id}=input,before=scoreSnapshot(agent)
 const old=agent.details?.scoreReview as ScoreReviewState|undefined
 const state:ScoreReviewState={original:old?.original??before,proposal:old?.proposal??null,supplements:[...(old?.supplements??[])],history:[...(old?.history??[])],confirmedBy:old?.confirmedBy}
 if(state.history.length>=25)throw new ScoreReviewError('本角色已达到25次复核记录，请新建研究以保留完整历史',409)
 const details={...agent.details},updated={...agent,details}
 if(request.supplement){if(state.supplements.length>=20)throw new ScoreReviewError('补充资料已达20份，请新建研究',409);state.supplements.push({...request.supplement,id:'supplement:'+id,origin:'user_supplied',submittedBy:actor,at,checkedBy:request.supplement.checked?actor.id:null})}
 let proposal:ConditionalProposal|undefined,reason=request.reason
 if(request.action==='ai_rescore'){
  if(!input.proposal)throw new ScoreReviewError('AI复评分未完成，原评分保留',422)
  proposal={...input.proposal,confidence:input.proposal.informationSufficient?Math.min(40,input.proposal.confidence):0}
  state.proposal={...proposal,id,at};reason=proposal.reason
 }else if(request.action==='accept_ai'){
  if(!state.proposal||state.proposal.id!==request.proposalId)throw new ScoreReviewError('AI候选已更新，请刷新后确认',409)
  proposal=state.proposal;updated.score=proposal.score;updated.confidence=proposal.confidence
  details.scoreBasis=proposal.confidence===0?'baseline':'ai_estimate';details.scoreReason=proposal.reason;details.scoreKind='investment_attractiveness';details.scoreSourceIds=proposal.sourceIds
  state.confirmedBy=actor;state.proposal=null
 }else{
  updated.score=request.score!;updated.confidence=request.confidence!;details.scoreBasis='human_adjusted';details.scoreReason=request.reason;details.scoreKind='investment_attractiveness';state.confirmedBy=actor;state.proposal=null
 }
 const entry:ScoreReviewEntry={id,at,actor,action:request.action,before,after:scoreSnapshot(updated),reason,proposal,rawCandidate:input.rawCandidate,calls:input.calls??[],supplementId:request.supplement?'supplement:'+id:undefined}
 state.history.push(entry);details.scoreReview=state
 return {agent:updated,entry,state}
}
