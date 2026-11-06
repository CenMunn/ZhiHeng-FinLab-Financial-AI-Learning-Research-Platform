// Exercise the packaged API and UI against a NEW disposable database, never the bound account store.
const fs = require('node:fs'), path = require('node:path'), os = require('node:os');
const assert = require('node:assert/strict'), { spawn, spawnSync } = require('node:child_process');
const { createRequire } = require('node:module'), { pathToFileURL } = require('node:url');
const root = path.resolve(__dirname, '..'), app = path.join(root, 'apps/committee');
const appRequire = createRequire(path.join(app, 'package.json'));
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "C:/Users/g'g/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright");
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
(async () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, '.local/committee/config.json'), 'utf8'));
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'platform-portfolio-'));
  const origin = 'http://127.0.0.1:3175', upstream = 'http://127.0.0.1:3185';
  const env = { ...process.env, NODE_ENV: 'production', NEXT_TELEMETRY_DISABLED: '1',
    DATABASE_URL: 'file:' + path.join(temp, 'fixture.sqlite').replaceAll('\\', '/'),
    APP_ORIGIN: origin, HOSTNAME: '127.0.0.1', PORT: '3185', FILINGS_DATA_DIR: path.join(temp, 'filings'),
    DEEPSEEK_API_KEY: '', OPENAI_API_KEY: '', ZAI_API_KEY: '', MIMO_API_KEY: '', LLM_AUDIT_LOG: '',
  };
  delete env.NODE_OPTIONS; delete env.NODE_PATH;
  const schema = spawnSync(process.execPath, [appRequire.resolve('prisma/build/index.js'), 'db', 'push',
    '--schema', path.join(app, 'prisma/schema.prisma'), '--skip-generate'], { cwd: temp, env, encoding: 'utf8', windowsHide: true });
  assert.equal(schema.status, 0, schema.stderr);
  const child = spawn(process.execPath, [path.join(config.runtimeDir, 'server.js')], { cwd: config.runtimeDir,
    env, windowsHide: true, stdio: ['ignore', fs.openSync(path.join(temp, 'server.log'), 'a'), fs.openSync(path.join(temp, 'error.log'), 'a')] });
  let gateway, browser;
  try {
    const { createGateway } = await import(pathToFileURL(path.join(root, 'scripts/committee-runtime.mjs')));
    gateway = createGateway({ upstreamOrigin: upstream, platformOrigin: 'http://127.0.0.1:5174', identity: { buildId: 'qa' } });
    await new Promise((resolve, reject) => { gateway.once('error', reject); gateway.listen(3175, '127.0.0.1', resolve); });
    let ready = false;
    for (let i = 0; i < 120; i++) {
      try { const r = await fetch(origin + '/api/auth/me', { signal: AbortSignal.timeout(2000) }); if (r.ok) { ready = true; break; } } catch {}
      await pause(250);
    }
    assert(ready, 'packaged server ready');
    const sample = [{ name: '600519', weight: 30 }, { name: '茅台', weight: 30 }, { name: '五粮液', weight: 40 }];
    assert.equal((await fetch(origin + '/api/portfolio', { method: 'POST', headers: { Origin: origin, 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings: sample }) })).status, 401);
    browser = await chromium.launch({ channel: 'msedge', headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const registered = await context.request.post(origin + '/api/auth/register', { headers: { Origin: origin },
      data: { username: 'portfolio_regression', password: require('node:crypto').randomUUID(), displayName: '组合回归测试' } });
    assert.equal(registered.status(), 201, await registered.text());
    const response = await context.request.post(origin + '/api/portfolio', { headers: { Origin: origin }, data: { holdings: sample } });
    assert.equal(response.status(), 200, await response.text());
    const result = (await response.json()).result;
    assert.equal(result.concentrationHHI, 5200); assert.equal(result.metrics[0].value, '60%'); assert.equal(result.riskLevel, 'Very High');
    assert.equal(result.holdings.length, 2);
    const boundary = await context.request.post(origin + '/api/portfolio', { headers: { Origin: origin },
      data: { holdings: [30,20,20,20,10].map((weight,i) => ({ name: `未知${i}`, weight })) } });
    assert.equal(boundary.status(), 200);
    assert.equal((await boundary.json()).result.riskLevel, 'Medium');
    assert.equal((await context.request.post(origin + '/api/portfolio', { headers: { Origin: 'https://outside.invalid' }, data: { holdings: sample } })).status(), 403);
    const page = await context.newPage(), errors = [], consoleErrors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
    // Market quotes are outside this regression. Avoid unrelated external data calls.
    await page.route('**/api/indices*', route => route.fulfill({ json: { groups: {}, markets: {}, sparks: {}, ts: Date.now() } }));
    await page.goto(origin, { waitUntil: 'networkidle' });
    await page.getByRole('button', { name: '组合体检', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('heading', { name: '组合诊断', exact: true }).waitFor();
    await dialog.getByRole('button', { name: '添加持仓' }).click();
    await dialog.getByRole('button', { name: '添加持仓' }).click();
    for (let i = 0; i < sample.length; i++) {
      await dialog.getByLabel('持仓股票名称', { exact: true }).nth(i).fill(sample[i].name);
      await dialog.getByLabel(`第 ${i + 1} 只持仓权重百分比`, { exact: true }).fill(String(sample[i].weight));
    }
    const submit = dialog.getByRole('button', { name: '开始诊断', exact: true });
    await submit.focus(); await page.keyboard.press('Enter');
    await dialog.getByText('组合风险 · Very High', { exact: true }).waitFor();
    assert.match(await dialog.innerText(), /5,?200/);
    const positions = dialog.getByText('Holdings · 合并后持仓权重', { exact: true }).locator('..');
    const text = await positions.innerText();
    assert.match(text, /贵州茅台\s+60\.0%/); assert.match(text, /五粮液\s+40\.0%/);
    assert.equal((text.match(/贵州茅台/g) || []).length, 1);
    assert.equal(await page.locator('nextjs-portal').count(), 0);
    await page.screenshot({ path: path.join(temp, 'desktop.png'), fullPage: false });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    const box = await dialog.boundingBox(); assert(box.x >= 0 && box.x + box.width <= 391);
    await page.screenshot({ path: path.join(temp, 'mobile.png'), fullPage: false });
    await page.keyboard.press('Escape'); await dialog.waitFor({ state: 'hidden' });
    assert.deepEqual(errors, []); assert.deepEqual(consoleErrors, []);
    const report = { status: 'passed', api: { hhi: result.concentrationHHI, maxSingle: result.metrics[0].value,
      riskLevel: result.riskLevel, mergedHoldings: result.holdings, exact30Boundary: 'Medium', guest401: true, crossOrigin403: true },
      browser: { engine: 'Edge/Playwright', fallback: 'Browser plugin not available', desktop: '1440x1000', mobile: '390x844',
        actualApi: true, mergedBars: true, keyboardSubmitAndClose: true, reducedMotion: true, pageErrors: errors, consoleErrors },
      database: 'new disposable fixture only; no original account data writes', modelApiKeys: false, evidenceDir: temp };
    fs.writeFileSync(path.join(temp, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally {
    if (browser) await browser.close();
    if (gateway) await new Promise(resolve => gateway.close(resolve));
    child.kill();
  }
})().catch(e => { console.error(e); process.exitCode = 1; });
