import {describe,it,expect} from 'vitest';
import {movingAverage,lessonSignal} from './signal-lesson';

describe('synthetic signal lesson',()=>{
  it('uses a complete trailing window and leaves the warmup undefined',()=>{
    expect(movingAverage([10,20,30,40],3)).toEqual([null,null,20,30]);
  });
  it('cannot change earlier values when future samples are appended',()=>{
    const prefix=[8,11,9,12];
    expect(movingAverage([...prefix,1000,-50],2).slice(0,4)).toEqual(movingAverage(prefix,2));
  });
  it('distinguishes unavailable, equal and above/below observations',()=>{
    expect(lessonSignal(10,null)).toBe('warmup');
    expect(lessonSignal(10,10)).toBe('equal');
    expect(lessonSignal(11,10)).toBe('above');
    expect(lessonSignal(9,10)).toBe('below');
  });
  it('rejects invalid windows and nonfinite sample values',()=>{
    for(const window of [0,-1,1.5,NaN])expect(()=>movingAverage([1,2],window)).toThrow();
    expect(()=>movingAverage([1,Infinity],2)).toThrow();
  });
});
