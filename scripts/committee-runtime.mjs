import http from 'node:http';
import {readFileSync} from 'node:fs';
import {Transform} from 'node:stream';

function presentationLink(){
  let pending=Buffer.alloc(0),sent=false;
  return new Transform({transform(chunk,encoding,done){
    if(sent){done(null,chunk);return;}
    pending=Buffer.concat([pending,chunk]);
    const end=pending.indexOf(Buffer.from('</head>'));
    if(end>=0){
      this.push(pending.subarray(0,end));this.push('<link rel="stylesheet" href="/__committee/presentation.css"/>');
      this.push(pending.subarray(end));pending=Buffer.alloc(0);sent=true;
    }else if(pending.length>256*1024){this.push(pending);pending=Buffer.alloc(0);sent=true;}
    done();
  },flush(done){if(pending.length)this.push(pending);done();}});
}

export function localOrigin(value){
  const url=new URL(value);
  if(url.protocol!=='http:'||!['127.0.0.1','localhost'].includes(url.hostname)||url.username||url.password||url.pathname!=='/'||url.search||url.hash||!url.port)throw Error('Only fixed loopback origins are allowed');
  return url.origin;
}

export function createGateway({upstreamOrigin,platformOrigin,identity}){
  const upstream=localOrigin(upstreamOrigin),platform=localOrigin(platformOrigin);
  const server=http.createServer(async(req,res)=>{
    if(req.url==='/__committee/presentation.css'){
      res.writeHead(200,{'Content-Type':'text/css; charset=utf-8','Cache-Control':'no-store'});
      res.end(readFileSync(new URL('./committee-presentation.css',import.meta.url)));return;
    }
    if(req.url==='/__committee/health'){
      let ready=false;
      try{
        const response=await fetch(upstream+'/api/auth/me',{signal:AbortSignal.timeout(1500),redirect:'error'});
        const data=await response.json();ready=response.ok&&Object.hasOwn(data,'user');
      }catch{}
      res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'no-store'});
      res.end(JSON.stringify({module:'committee',...identity,ready}));return;
    }
    const target=new URL(req.url??'/',upstream);
    // Absolute-form request targets cannot turn the gateway into an open proxy.
    if(target.origin!==upstream){res.writeHead(400);res.end('Invalid request target');return;}
    const headers={...req.headers};
    if(headers.accept?.includes('text/html'))headers['accept-encoding']='identity';
    const request=http.request(target,{method:req.method,headers},response=>{
      const outgoing={...response.headers,'content-security-policy':`frame-ancestors 'self' ${platform}`};
      const html=String(response.headers['content-type']).includes('text/html')&&!response.headers['content-encoding'];
      if(html){delete outgoing['content-length'];delete outgoing.etag;outgoing['cache-control']='no-store';}
      res.writeHead(response.statusCode??502,outgoing);
      if(html)response.pipe(presentationLink()).pipe(res);else response.pipe(res);
    });
    request.on('error',()=>{
      if(res.headersSent){res.destroy();return;}
      res.writeHead(502,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'智投委服务暂时不可用，请稍后重试。'}));
    });
    req.on('aborted',()=>request.destroy());
    res.on('close',()=>request.destroy());
    req.pipe(request);
  });
  server.requestTimeout=0;
  return server;
}
