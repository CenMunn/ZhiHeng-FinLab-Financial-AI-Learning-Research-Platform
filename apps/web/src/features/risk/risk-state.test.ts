import { describe, expect, it } from 'vitest';
import { initialState, reducer, currentResult, percentToRatio } from './risk-state';
import type { CalculationResult, CaseSnapshot, SavedScenario } from './api';

const snapshot = {snapshot_id:'one',snapshot_sha256:'a'.repeat(64)} as CaseSnapshot;
const result = {input_hash:'hash',snapshot,assumptions:{credit_share:'0.8',delay_days:'15'}} as CalculationResult;
const saved = {scenario_id:'saved',title:'情景A',result} as SavedScenario;

describe('parameter and request isolation', () => {
  it('converts percentages as exact strings without filling missing values', () => {
    expect(percentToRatio('80.125')).toBe('0.80125');
    expect(percentToRatio('100')).toBe('1');
    expect(percentToRatio('0')).toBe('0');
    expect(percentToRatio('')).toBeNull();
    expect(percentToRatio('100.0001')).toBeNull();
  });
  it('ignores old success and error after a parameter edit', () => {
    let state=reducer(initialState(snapshot),{type:'edit',field:'creditPercent',value:'80'});
    state=reducer(state,{type:'calculate-start',requestId:1});
    const revision=state.inputRevision;
    state=reducer(state,{type:'edit',field:'delayDays',value:'20'});
    expect(reducer(state,{type:'calculate-success',requestId:1,revision,result})).toEqual(state);
    expect(reducer(state,{type:'calculate-error',requestId:1,revision,message:'old error'})).toEqual(state);
  });
  it('retains old result but prevents treating it as current', () => {
    let state=reducer(initialState(snapshot),{type:'calculate-start',requestId:1});
    state=reducer(state,{type:'calculate-success',requestId:1,revision:state.inputRevision,result});
    expect(currentResult(state)).toBe(true);
    state=reducer(state,{type:'edit',field:'delayDays',value:'20'});
    expect(state.result).toBe(result);
    expect(currentResult(state)).toBe(false);
  });
  it('title edits retain calculation but invalidate an old save completion', () => {
    let state=reducer(initialState(snapshot),{type:'calculate-start',requestId:1});
    state=reducer(state,{type:'calculate-success',requestId:1,revision:state.inputRevision,result});
    state=reducer(state,{type:'save-start',requestId:2});
    const revision=state.editRevision;
    state=reducer(state,{type:'title',value:'changed'});
    expect(currentResult(state)).toBe(true);
    expect(reducer(state,{type:'save-success',requestId:2,revision,saved}).saved).toBeUndefined();
  });
  it('opening a saved scenario restores inputs and isolates late responses', () => {
    let state=reducer(initialState(snapshot),{type:'calculate-start',requestId:1});
    const revision=state.inputRevision;
    state=reducer(state,{type:'open',saved});
    expect(state.draft.creditPercent).toBe('80');
    expect(currentResult(state)).toBe(true);
    expect(state.saved?.scenario_id).toBe('saved');
    expect(reducer(state,{type:'calculate-error',requestId:1,revision,message:'old'})).toEqual(state);
  });
  it('never marks another calculation identity as the displayed saved result', () => {
    let state=reducer(initialState(snapshot),{type:'calculate-start',requestId:1});
    state=reducer(state,{type:'calculate-success',requestId:1,revision:0,result});
    state=reducer(state,{type:'save-start',requestId:2});
    const changed={...saved,result:{...result,input_hash:'different'}};
    state=reducer(state,{type:'save-success',requestId:2,revision:0,saved:changed});
    expect(state.saved).toBeUndefined();
    expect(state.saveError).toContain('版本');
    expect(state.result).toBe(result);
  });
});
