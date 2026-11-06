import {describe,it,expect} from 'vitest';
import {platformRoute} from './platform-routes';

describe('independent platform modules',()=>{
  it('starts at overview and keeps planned modules out of committee',()=>{
    expect(platformRoute('')).toEqual({module:'home'});
    expect(platformRoute('#/')).toEqual({module:'home'});
    for(const module of ['lab','cashflow','training'])expect(platformRoute(`#/${module}`)).toEqual({module});
    expect(platformRoute('#/unknown')).toEqual({module:'home'});
  });
  it('preserves existing committee and legacy deep links',()=>{
    expect(platformRoute('#/committee/filings')).toEqual({module:'committee',section:'filings'});
    expect(platformRoute('#/risk')).toEqual({module:'committee',section:'scenarios'});
    expect(platformRoute('#/evidence')).toEqual({module:'committee',section:'evidence'});
  });
});
