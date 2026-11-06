import { useEffect, useReducer, useRef, useState } from 'react';
import { api, type CalculationRequest, type CaseSnapshot, type ComparisonResult, type SavedScenario } from './api';
import { currentResult, initialState, percentToRatio, reducer, validDelay } from './risk-state';

export interface WorkspaceProps {snapshot:CaseSnapshot;canCalculate:boolean;history:SavedScenario[];refreshHistory:()=>Promise<void>;openScenario:SavedScenario|null;onOpened:()=>void}

export function useRiskScenario({snapshot,canCalculate,refreshHistory,openScenario,onOpened}:WorkspaceProps) {
  const [state,dispatch]=useReducer(reducer,snapshot,initialState);
  const [reference,setReference]=useState('');
  const [comparison,setComparison]=useState<ComparisonResult>();
  const [comparisonError,setComparisonError]=useState('');
  const [pendingOpen,setPendingOpen]=useState<SavedScenario>();
  const [openVersion,setOpenVersion]=useState(0);
  const sequence=useRef(0),saveRequest=useRef<{fingerprint:string;key:string}>();
  const share=percentToRatio(state.draft.creditPercent);
  const valid=share!==null && validDelay(state.draft.delayDays);
  const fresh=currentResult(state);
  const registered=canCalculate && state.snapshot.snapshot_id===snapshot.snapshot_id && state.snapshot.snapshot_sha256===snapshot.snapshot_sha256;
  const result=state.result;
  function open(saved:SavedScenario){dispatch({type:'open',saved});setReference('');setOpenVersion(value=>value+1);}
  useEffect(()=>{if(openScenario){
    if(!state.saved && (state.result || state.editRevision>0))setPendingOpen(openScenario);
    else open(openScenario);
    onOpened();
  }},[openScenario,onOpened]);
  useEffect(()=>{
    let alive=true;
    setComparison(undefined);setComparisonError('');
    if(fresh && result){
      if(!registered){setComparisonError('当前来源不可用或已换版；原结果保留，本次不重新计算差值。');return;}
      const body={snapshot_id:result.snapshot.snapshot_id,expected_snapshot_sha256:result.snapshot.snapshot_sha256,assumptions:result.assumptions};
      api.compare(body,reference,result.input_hash).then(value=>{if(alive)setComparison(value);})
        .catch(error=>{if(alive)setComparisonError(error.message);});
    }
    return()=>{alive=false;};
  },[fresh,result,reference,registered]);
  useEffect(()=>{
    const guard=(event:BeforeUnloadEvent)=>{if(!state.saved && (state.result || state.draft.creditPercent)){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',guard);return()=>window.removeEventListener('beforeunload',guard);
  },[state.saved,state.result,state.draft.creditPercent]);
  async function calculate(){
    if(!valid || !registered)return;
    const requestId=++sequence.current,revision=state.inputRevision;
    const body:CalculationRequest={snapshot_id:state.snapshot.snapshot_id,expected_snapshot_sha256:state.snapshot.snapshot_sha256,
      assumptions:{credit_share:share!,delay_days:state.draft.delayDays}};
    dispatch({type:'calculate-start',requestId});
    try{dispatch({type:'calculate-success',requestId,revision,result:await api.calculate(body)});}
    catch(error){dispatch({type:'calculate-error',requestId,revision,message:(error as Error).message});}
  }
  async function save(){
    if(!registered || !fresh || !result || !state.title.trim() || state.saving)return;
    const body={snapshot_id:result.snapshot.snapshot_id,expected_snapshot_sha256:result.snapshot.snapshot_sha256,
      assumptions:result.assumptions,title:state.title,expected_input_hash:result.input_hash};
    const fingerprint=JSON.stringify(body);
    if(saveRequest.current?.fingerprint!==fingerprint)saveRequest.current={fingerprint,key:crypto.randomUUID()};
    const requestId=++sequence.current,revision=state.editRevision;
    dispatch({type:'save-start',requestId});
    try{const saved=await api.save(body,saveRequest.current.key);dispatch({type:'save-success',requestId,revision,saved});await refreshHistory();}
    catch(error){dispatch({type:'save-error',requestId,revision,message:(error as Error).message});}
  }
  return {state,dispatch,share,valid,fresh,registered,result,reference,setReference,comparison,comparisonError,calculate,save,
    openVersion,pendingOpen,cancelOpen:()=>setPendingOpen(undefined),confirmOpen:()=>{if(pendingOpen)open(pendingOpen);setPendingOpen(undefined);}};
}
