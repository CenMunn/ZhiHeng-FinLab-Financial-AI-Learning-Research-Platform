import test from 'node:test';
import assert from 'node:assert/strict';
import {isOwnedProcess} from '../scripts/stop_platform.mjs';
test('stop guard requires exact process generation and this project entry',()=>{
 const root='D:\\project';const record={role:'committee',pid:123,startedAt:'2026-10-25T01:00:00.000Z'};
 const info={ProcessId:123,CommandLine:'node D:\\project\\scripts\\start_committee.mjs',CreatedAt:record.startedAt};
 assert.equal(isOwnedProcess(record,info,root),true);
 assert.equal(isOwnedProcess(record,{...info,CreatedAt:'2026-10-25T02:00:00.000Z'},root),false);
 assert.equal(isOwnedProcess(record,{...info,CommandLine:'node D:\\other\\scripts\\start_committee.mjs'},root),false);
 assert.equal(isOwnedProcess(record,{...info,ProcessId:456},root),false);
 assert.equal(isOwnedProcess({...record,role:'unknown'},info,root),false);
});
