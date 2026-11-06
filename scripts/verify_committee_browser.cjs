// Browser plugin not available; use bundled Playwright against the actual local services.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const {createRequire}=require('node:module');
const runtime=path.join(process.env.USERPROFILE,'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
const {chromium}=createRequire(path.join(runtime,'package.json'))('playwright');

(async()=>{
 const output=path.resolve('.local/committee/browser-qa');fs.mkdirSync(output,{recursive:true});
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage(),errors=[],consoleEvents=[];page.on('pageerror',e=>errors.push(e.message));
  page.on('console',message=>{if(['error','warning'].includes(message.type()))consoleEvents.push({type:message.type(),text:message.text(),url:message.location().url});});
  const main='http://127.0.0.1:5174/';
  await page.goto(main);await page.locator('iframe').waitFor({timeout:30000});
  let frame=page.frameLocator('iframe');
  await frame.getByRole('heading',{name:/从财报原文/}).waitFor();
  assert.equal(await page.locator('.committee-connection').count(),0);
  assert.doesNotMatch(await frame.locator('body').innerText(),/猫猫小分队|智投委\s*AI|AI Investment Committee/i);
  assert.equal(await frame.locator('nav[aria-label="主要导航"]').isVisible(),false);
  assert.match(await page.title(),/金融研究平台/);
  await page.screenshot({path:path.join(output,'desktop.png')});
  await frame.getByRole('button',{name:'什么是市盈率',exact:true}).click();
  await frame.getByRole('dialog').waitFor();
  assert.match(await frame.getByRole('dialog').innerText(),/本地金融词典/);await page.keyboard.press('Escape');
  await frame.getByRole('button',{name:'登录 / 注册',exact:true}).click();await frame.getByRole('dialog').waitFor();await page.keyboard.press('Escape');
  await frame.getByRole('button',{name:'切换到亮色模式',exact:true}).click();
  await frame.getByRole('button',{name:'切换到暗色模式',exact:true}).click();
  const draft=frame.getByPlaceholder(/输入公司、财务问题或黑话/);await draft.fill('尚未提交的研究草稿');
  const navigation=page.getByRole('navigation',{name:'智投委功能'});
  await navigation.getByRole('link',{name:'回款压力推演',exact:true}).click();
  await page.locator('#credit-share').fill('80');await page.locator('#delay-days').fill('15');
  const responsePromise=page.waitForResponse(r=>r.url().includes('/risk/receivables-delay')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'计算情景',exact:true}).click();
  const result=await (await responsePromise).json();assert.equal(result.occupancy_change,'69158975.62');
  await page.locator('.result-amount.is-current').waitFor();
  await page.screenshot({path:path.join(output,'scenarios.png')});
  await page.getByRole('button',{name:/历史情景/}).click();await page.getByRole('dialog').waitFor();await page.keyboard.press('Escape');
  await navigation.getByRole('link',{name:'投研工作台',exact:true}).click();
  assert.equal(await draft.inputValue(),'尚未提交的研究草稿');
  for(const [label,heading] of [['财报核验与比较','财报核验与同行比较'],['财务原页','上传财报 · 形成可追溯报告'],['价格预测实验','股票价格变化预测']]){
    await navigation.getByRole('link',{name:label,exact:true}).click();
    await frame.getByRole('heading',{name:heading,exact:true}).waitFor();
    assert.doesNotMatch(await frame.locator('body').innerText(),/猫猫小分队|智投委\s*AI|AI Investment Committee/i);
    await frame.getByRole('button',{name:'登录 / 注册',exact:true}).waitFor({state:'visible'});
  }
  assert.match(await frame.locator('body').innerText(),/请登录/);
  await navigation.getByRole('link',{name:'回款压力推演',exact:true}).click();assert.equal(await page.locator('#credit-share').inputValue(),'80');
  await page.emulateMedia({reducedMotion:'reduce'});
  await navigation.getByRole('link',{name:'财报核验与比较',exact:true}).hover();
  const transform=await navigation.getByRole('link',{name:'财报核验与比较',exact:true}).evaluate(e=>getComputedStyle(e).transform);assert.equal(transform,'none');
  await page.locator('.skip-link').focus();await page.keyboard.press('Enter');assert.match(page.url(),/committee\/scenarios/);
  await page.setViewportSize({width:390,height:844});
  await navigation.getByRole('link',{name:'财务原页',exact:true}).click();
  await frame.getByRole('heading',{name:'上传财报 · 形成可追溯报告',exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  await page.screenshot({path:path.join(output,'mobile.png')});
  assert.equal(await frame.locator('html').evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  // Transport can fail independently of M1. Retry must restore the embedded module.
  let offline=true;
  await page.route('**/api/v1/integrations/committee',route=>offline?route.fulfill({status:503,body:'offline'}):route.continue());
  await page.getByRole('heading',{name:'工作区暂时无法打开',exact:true}).waitFor({timeout:20000});
  await navigation.getByRole('link',{name:'回款压力推演',exact:true}).click();assert.equal(await page.locator('#credit-share').inputValue(),'80');
  await navigation.getByRole('link',{name:'财务原页',exact:true}).click();offline=false;
  await page.getByRole('button',{name:'重新加载',exact:true}).click();
  await frame.getByRole('heading',{name:'上传财报 · 形成可追溯报告',exact:true}).waitFor();
  const origin='http://127.0.0.1:3155';
  const denied=await context.request.post(origin+'/api/filings',{headers:{Origin:origin},data:{action:'list'}});assert.equal(denied.status(),401);
  const csrf=await context.request.post(origin+'/api/filings',{headers:{Origin:'https://example.com'},data:{action:'list'}});assert.equal(csrf.status(),403);
  const forecast=await context.request.get(origin+'/api/forecast');assert.equal(forecast.status(),401);
  assert.deepEqual(errors,[]);
  const unexpectedConsole=consoleEvents.filter(event=>!(event.url.includes('/api/v1/integrations/committee')&&event.text.includes('503')));
  assert.deepEqual(unexpectedConsole,[]);
  const report={status:'passed',browser:'Playwright Edge; Browser plugin not available',pages:4,nativeScenario:true,amount:result.occupancy_change,
    preservesDraft:true,historyDrawer:true,localConceptQuestion:true,loginDialog:true,mobile:true,reducedMotion:true,keyboardSkip:true,
    offlineRetry:true,guestRejected:true,crossOriginWriteRejected:true,brandingRemovedAcrossPages:true,connectionBarRemoved:true,paidModelCalls:0,pageErrors:errors,consoleEvents,
    limitations:['No real account login or existing private report export performed','No new multi-agent research/model calls','No physical touch-device test']};
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
