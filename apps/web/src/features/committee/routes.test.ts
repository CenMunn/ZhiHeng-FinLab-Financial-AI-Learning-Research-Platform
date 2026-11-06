import {describe,it,expect} from 'vitest';
import {committeeSection,committeeHash,embeddedPath,isLocalOrigin} from './routes';

describe('committee feature ownership',()=>{
  it('owns legacy risk and evidence routes and defaults to the full committee',()=>{
    expect(committeeSection('')).toBe('research');
    expect(committeeSection('#/risk')).toBe('scenarios');
    expect(committeeSection('#/evidence')).toBe('evidence');
    expect(committeeHash('scenarios')).toBe('#/committee/scenarios');
    expect(committeeSection('#/committee/forecast')).toBe('forecast');
    expect(committeeSection('#/unknown')).toBe('research');
  });
  it('keeps native calculations out of the embedded application paths',()=>{
    expect(embeddedPath('research')).toBe('/');
    expect(embeddedPath('filings')).toBe('/filings');
    expect(embeddedPath('scenarios')).toBeNull();
  });
  it('never embeds a remote or credential-bearing origin',()=>{
    expect(isLocalOrigin('http://127.0.0.1:3155')).toBe(true);
    for(const url of ['javascript:alert(1)','https://example.com','http://x@localhost:3155','http://127.0.0.1:3155/extra'])expect(isLocalOrigin(url)).toBe(false);
  });
});
