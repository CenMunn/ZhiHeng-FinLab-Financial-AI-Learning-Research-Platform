import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {localOrigin,createGateway} from '../scripts/committee-runtime.mjs';

test('origin is strictly loopback without credentials or routes',()=>{
  assert.equal(localOrigin('http://127.0.0.1:3155'),'http://127.0.0.1:3155');
  for(const value of ['https://example.com','http://user@127.0.0.1:3155','http://127.0.0.1:3155/page','http://127.0.0.1:3155?x=1'])assert.throws(()=>localOrigin(value));
});

test('gateway preserves bodies, cookie/download headers and reports true upstream readiness',async t=>{
  const upstream=http.createServer((req,res)=>{
    if(req.url==='/api/auth/me'){res.setHeader('Content-Type','application/json');res.end('{"user":null}');return;}
    res.setHeader('Content-Disposition','attachment; filename="report.md"');
    res.setHeader('Set-Cookie','investment_session=fixture; HttpOnly; Path=/');
    req.pipe(res);
  });
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));
  t.after(()=>upstream.close());
  const gateway=createGateway({upstreamOrigin:`http://127.0.0.1:${upstream.address().port}`,platformOrigin:'http://127.0.0.1:5174',identity:{buildId:'fixture',release:'fixture'}});
  await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
  t.after(()=>gateway.close());
  const origin=`http://127.0.0.1:${gateway.address().port}`;
  const health=await (await fetch(origin+'/__committee/health')).json();
  assert.equal(health.module,'committee');assert.equal(health.ready,true);assert.equal(health.buildId,'fixture');
  const response=await fetch(origin+'/api/echo',{method:'POST',body:'original body'});
  assert.equal(await response.text(),'original body');
  assert.match(response.headers.get('set-cookie'),/investment_session/);
  assert.match(response.headers.get('content-disposition'),/report.md/);
  assert.match(response.headers.get('content-security-policy'),/127\.0\.0\.1:5174/);
});

test('gateway applies platform presentation to every HTML page without rewriting application text',async t=>{
  const upstream=http.createServer((req,res)=>{
    if(req.url==='/api/data'){res.setHeader('Content-Type','application/json');res.end('{"value":"unchanged"}');return;}
    const first='<!doctype html><html><head><title>原页面</title></he',last='ad><body>原业务内容</body></html>';
    res.setHeader('Content-Type','text/html; charset=utf-8');res.setHeader('Content-Length',String(Buffer.byteLength(first+last)));
    res.write(first);res.end(last);
  });
  await new Promise(r=>upstream.listen(0,'127.0.0.1',r));t.after(()=>upstream.close());
  const gateway=createGateway({upstreamOrigin:`http://127.0.0.1:${upstream.address().port}`,platformOrigin:'http://127.0.0.1:5174',identity:{buildId:'fixture'}});
  await new Promise(r=>gateway.listen(0,'127.0.0.1',r));t.after(()=>gateway.close());
  const origin=`http://127.0.0.1:${gateway.address().port}`;
  for(const path of ['/','/filings','/evidence','/forecast']){
    const response=await fetch(origin+path,{headers:{Accept:'text/html'},signal:AbortSignal.timeout(2000)});
    const html=await response.text();assert.match(html,/\/__committee\/presentation.css/);assert.match(html,/原业务内容/);
    assert.equal(response.headers.get('content-length'),null);
  }
  const css=await(await fetch(origin+'/__committee/presentation.css')).text();
  assert.match(css,/智投委 AI 首页/);assert.match(css,/research-desk/);
  assert.deepEqual(await(await fetch(origin+'/api/data')).json(),{value:'unchanged'});
});
