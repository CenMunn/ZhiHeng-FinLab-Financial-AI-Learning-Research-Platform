import {describe,it,expect} from 'vitest';
import {splitPreview} from './foundation-presentation';
describe('draft split preview',()=>{
  it('shows actual counts and proportions without claiming server validation',()=>{
    expect(splitPreview(15,8,3)).toEqual({valid:true,counts:[8,3,4],fractions:[8/15,3/15,4/15]});
  });
  it('never turns missing, noninteger or overlapping counts into a valid chart',()=>{
    for(const [total,train,validation] of [[15,12,3],[15,16,3],[15,8,-1],[15,2,3],[15,8.5,3],[0,0,0],[15,NaN,3]]){
      expect(splitPreview(total,train,validation).valid).toBe(false);
    }
  });
});
