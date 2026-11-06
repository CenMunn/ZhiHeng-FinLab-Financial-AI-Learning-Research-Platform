// Read-only recovery check. Browser plugin not available; use existing Playwright.
// No login, scenario calculation, model request, account, or private database access.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{createRequire}=require('node:module');
const {chromium}=createRequire(path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json'))('playwright');
const base='http://127.0.0.1:5174',output=path.join(os.tmpdir(),'financial-committee-recovery-20261106');
(async()=>{
 fs.mkdirSync(output,{recursive:true});const browser=await chromium.launch({channel:'msedge',headless:true});let page;
 const errors=[],consoleEvents=[],blockedWrites=[],checks=[];
 try{
  page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(45000);
  page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(['error','warning'].includes(m.type()))consoleEvents.push({type:m.type(),text:m.text(),url:m.location().url});});
  await page.route('**/*',route=>{const request=route.request();if(!['GET','HEAD','OPTIONS'].includes(request.method())){blockedWrites.push({method:request.method(),url:request.url()});return route.abort('blockedbyclient');}return route.continue();});
  const healthResponse=await page.request.get('http://127.0.0.1:8010/api/v1/integrations/committee');assert.equal(healthResponse.status(),200);const integration=await healthResponse.json();assert.equal(integration.state,'ready');assert.equal(integration.available,true);assert.equal(integration.build_id,'8qbH7PFegsy1GDb7aQjfJ');
  await page.goto(base+'/#/committee/research');assert.equal(await page.title(),'金融实验室');
  const iframe=page.locator('iframe');await iframe.waitFor();const frame=page.frameLocator('iframe'),nav=page.getByRole('navigation',{name:'智投委功能'});
  const sections=[['research','投研工作台',/从财报原文/],['evidence','财报核验与比较','财报核验与同行比较'],['filings','财务原页','上传财报 · 形成可追溯报告'],['forecast','价格预测实验','股票价格变化预测']];
  for(const [key,label,heading] of sections){
   await nav.getByRole('link',{name:label,exact:true}).click();await frame.getByRole('heading',{name:heading,exact:typeof heading==='string'}).waitFor();
   assert.ok(page.url().endsWith('#/committee/'+key));assert.ok((await iframe.getAttribute('src')).includes('127.0.0.1:3155'));
   assert.doesNotMatch(await frame.locator('body').innerText(),/猫猫小分队|智投委\s*AI|AI Investment Committee/i);
   assert.equal(await frame.locator('nav[aria-label="主要导航"]').isVisible(),false);
   assert.equal(await page.locator('.committee-connection').count(),0);checks.push(key+' renders expected heading and embedded app without duplicate branding');
  }
  await frame.getByRole('button',{name:'登录 / 注册',exact:true}).click();await frame.getByRole('dialog').waitFor();await page.keyboard.press('Escape');await frame.getByRole('dialog').waitFor({state:'hidden'});checks.push('login dialog opens and closes without login');
  await nav.getByRole('link',{name:'投研工作台',exact:true}).click();await frame.getByRole('heading',{name:/从财报原文/}).waitFor();
  await page.screenshot({path:path.join(output,'desktop.png')});
  await page.setViewportSize({width:375,height:960});await nav.getByRole('link',{name:'财务原页',exact:true}).click();await frame.getByRole('heading',{name:'上传财报 · 形成可追溯报告',exact:true}).waitFor();
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert.ok(await frame.locator('html').evaluate(e=>e.scrollWidth<=innerWidth+1));await page.screenshot({path:path.join(output,'narrow-375.png')});checks.push('375px parent and embedded app have no horizontal page overflow');
  await page.emulateMedia({reducedMotion:'reduce'});const link=nav.getByRole('link',{name:'财报核验与比较',exact:true});await link.focus();await page.keyboard.press('Enter');await frame.getByRole('heading',{name:'财报核验与同行比较',exact:true}).waitFor();assert.equal(await link.evaluate(e=>getComputedStyle(e).transform),'none');checks.push('keyboard navigation and reduced motion work');
  assert.deepEqual(errors,[]);assert.deepEqual(consoleEvents,[]);assert.deepEqual(blockedWrites,[]);
  const report={status:'passed',created_at:new Date().toISOString(),entry:base+'/#/committee/research',integration,browser:'Playwright Edge; Browser plugin not available',viewports:['1440x1000','375x960'],checks,read_only:true,login_performed:false,model_calls:0,private_database_access:false,blockedWrites,pageErrors:errors,consoleEvents,output,limitations:['Anonymous pages only; no account or private report data inspected','No physical touch device or other browser verified']};
  fs.writeFileSync(path.join(process.cwd(),'docs/research/2026-11-06-committee-recovery.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }catch(error){if(page)await page.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});throw error;}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
