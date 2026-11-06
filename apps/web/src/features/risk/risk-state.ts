import type { CalculationResult, CaseSnapshot, SavedScenario } from './api';

export function percentToRatio(value: string): string | null {
  if (!/^(?:0|[1-9]\d*)(?:\.\d{1,4})?$/.test(value) || Number(value)>100) return null;
  const [whole,fraction=''] = value.split('.');
  const padded = whole.padStart(3,'0');
  return canonical(`${padded.slice(0,-2)}.${padded.slice(-2)}${fraction}`);
}
function canonical(value: string): string {
  const [whole,fraction=''] = value.split('.');
  const trimmed=fraction.replace(/0+$/,'');
  return (whole.replace(/^0+(?=\d)/,'') || '0') + (trimmed ? `.${trimmed}` : '');
}
export function ratioToPercent(value: string): string {
  const [whole,fraction='']=value.split('.');
  const padded=fraction.padEnd(2,'0');
  return canonical(`${whole}${padded.slice(0,2)}.${padded.slice(2)}`);
}
export function validDelay(value: string): boolean {
  return /^(?:0|[1-9]\d*)(?:\.\d{1,2})?$/.test(value) && Number(value)<=90;
}
export interface State {
  snapshot: CaseSnapshot; draft: {creditPercent:string;delayDays:string}; title: string;
  inputRevision: number; editRevision: number; resultInputRevision?: number;
  result?: CalculationResult; saved?: SavedScenario; error?: string; saveError?: string;
  calculating?: number; saving?: number;
}
export type Action =
  | {type:'edit';field:'creditPercent'|'delayDays';value:string}
  | {type:'title';value:string}
  | {type:'calculate-start';requestId:number}
  | {type:'calculate-success';requestId:number;revision:number;result:CalculationResult}
  | {type:'calculate-error';requestId:number;revision:number;message:string}
  | {type:'save-start';requestId:number}
  | {type:'save-success';requestId:number;revision:number;saved:SavedScenario}
  | {type:'save-error';requestId:number;revision:number;message:string}
  | {type:'open';saved:SavedScenario}
  | {type:'restore'};
export function initialState(snapshot:CaseSnapshot):State {
  return {snapshot,draft:{creditPercent:'',delayDays:'15'},title:'回款延迟情景',inputRevision:0,editRevision:0};
}
export function currentResult(state:State):boolean {
  return !!state.result && state.resultInputRevision===state.inputRevision;
}
export function reducer(state:State, action:Action):State {
  switch(action.type) {
    case 'edit': return {...state,draft:{...state.draft,[action.field]:action.value},inputRevision:state.inputRevision+1,
      editRevision:state.editRevision+1,calculating:undefined,saving:undefined,saved:undefined,error:undefined,saveError:undefined};
    case 'title': return {...state,title:action.value,editRevision:state.editRevision+1,saving:undefined,saved:undefined,saveError:undefined};
    case 'calculate-start': return {...state,calculating:action.requestId,error:undefined};
    case 'calculate-success':
      if(state.calculating!==action.requestId || state.inputRevision!==action.revision) return state;
      return {...state,result:action.result,resultInputRevision:action.revision,calculating:undefined,saved:undefined,error:undefined};
    case 'calculate-error':
      if(state.calculating!==action.requestId || state.inputRevision!==action.revision) return state;
      return {...state,calculating:undefined,error:action.message};
    case 'save-start': return {...state,saving:action.requestId,saveError:undefined};
    case 'save-success':
      if(state.saving!==action.requestId || state.editRevision!==action.revision) return state;
      if(state.result?.input_hash!==action.saved.result.input_hash)return {...state,saving:undefined,saveError:'保存返回的计算版本不同，请重新计算并核对。'};
      return {...state,saving:undefined,saved:action.saved,saveError:undefined};
    case 'save-error':
      if(state.saving!==action.requestId || state.editRevision!==action.revision) return state;
      return {...state,saving:undefined,saveError:action.message};
    case 'open': {
      const revision=state.inputRevision+1;
      return {...initialState(action.saved.result.snapshot),title:action.saved.title,result:action.saved.result,
        saved:action.saved,draft:{creditPercent:ratioToPercent(action.saved.result.assumptions.credit_share),delayDays:action.saved.result.assumptions.delay_days},
        inputRevision:revision,resultInputRevision:revision,editRevision:state.editRevision+1};
    }
    case 'restore':
      if(!state.result) return state;
      return {...state,draft:{creditPercent:ratioToPercent(state.result.assumptions.credit_share),delayDays:state.result.assumptions.delay_days},
        inputRevision:state.inputRevision+1,resultInputRevision:state.inputRevision+1,editRevision:state.editRevision+1,
        calculating:undefined,saving:undefined,error:undefined,saveError:undefined};
  }
}
