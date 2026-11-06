const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const Module = require('node:module');
const root = path.resolve(__dirname, '../apps/committee');
const req = Module.createRequire(path.join(root, 'package.json'));
const ts = req('typescript');
let saved, prompt, authorized = true;
const cache = {};
function load(file) {
  if (cache[file]) return cache[file].exports;
  const full = path.join(root, file), mod = new Module(full);
  cache[file] = mod;
  mod.require = id => {
    if (id === '@/lib/db') return { db: { portfolioAnalysis: { create: async value => { saved = value.data; } } } };
    if (id === '@/lib/ai/llm') return { tryChatJSON: async (_system, user) => { prompt = user; return null; } };
    if (id === '@/lib/auth/server') return {
      requireUser: async (_req, options) => { assert.equal(options.write, true); if (!authorized) throw Error('AUTH'); return { id: 'test-owner' }; },
      authErrorResponse: e => e.message === 'AUTH' ? Response.json({ error: 'login' }, { status: 401 }) : null,
    };
    if (id.startsWith('@/')) return load('src/' + id.slice(2) + '.ts');
    return req(id);
  };
  mod._compile(ts.transpileModule(fs.readFileSync(full, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true,
  } }).outputText, full + '.cjs');
  return mod.exports;
}
const api = load('src/app/api/portfolio/route.ts');
async function diagnose(holdings) {
  saved = null; prompt = null;
  const response = await api.POST(new Request('http://localhost/api/portfolio', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ holdings }),
  }));
  return { status: response.status, ...(await response.json()) };
}
const pair = [{ name: '贵州茅台', weight: 30 }, { name: '贵州茅台', weight: 30 }, { name: '五粮液', weight: 40 }];
test('duplicate positions produce HHI 5200, max 60%, Very High and one sector name per security', async () => {
  const { status, result } = await diagnose(pair);
  assert.equal(status, 200);
  assert.equal(result.concentrationHHI, 5200);
  assert.equal(result.riskLevel, 'Very High');
  assert.equal(result.metrics[0].value, '60%');
  assert.equal(result.metrics[3].value, '2/2');
  assert.deepEqual(result.sectorExposure, [{ sector: '消费', weight: 100, names: ['贵州茅台', '五粮液'] }]);
  assert.deepEqual(result.holdings, [{ name: '贵州茅台', weight: 60 }, { name: '五粮液', weight: 40 }]);
  assert(result.suggestions.some(s => s.name === '贵州茅台' && /60%/.test(s.reason)));
  const modelHoldings = JSON.parse(prompt.split('- 标的与权重：')[1].split('\n')[0]);
  assert.deepEqual(modelHoldings.map(h => [h.name, h.weight]), [['贵州茅台', 60], ['五粮液', 40]]);
  assert.equal(saved.ownerId, 'test-owner');
  assert.deepEqual(JSON.parse(saved.input), pair); // Raw input remains auditable.
  assert.deepEqual(JSON.parse(saved.result), result);
});
test('codes, exact names, aliases and autocomplete labels share one reliable identity', async () => {
  for (const name of ['600519', '茅台', 'MOUTAI', '贵州茅台(600519)', '贵州茅台（600519）', 'SH600519', '600519.SH']) {
    const { result } = await diagnose([{ name, weight: 3 }, { name: '贵州茅台', weight: 3 }, { name: '000858', weight: 4 }]);
    assert.equal(result.concentrationHHI, 5200, name);
    assert.equal(result.metrics[0].value, '60%', name);
    assert.equal(result.holdings.length, 2, name);
  }
});
test('different securities remain distinct even within the same sector', async () => {
  const { result } = await diagnose([{ name: '贵州茅台', weight: 30 }, { name: '五粮液', weight: 30 }, { name: '600036', weight: 40 }]);
  assert.equal(result.concentrationHHI, 3400);
  assert.equal(result.riskLevel, 'High');
  assert.equal(result.metrics[0].value, '40%');
  assert.equal(result.sectorExposure.find(s => s.sector === '消费').weight, 60);
  assert.equal(result.holdings.length, 3);
});
test('unknown exact repeats merge, but similar names, conflicting labels and markets do not', async () => {
  const { result } = await diagnose([{ name: '未知甲', weight: 30 }, { name: ' 未知甲 ', weight: 30 }, { name: '未知乙', weight: 40 }]);
  assert.equal(result.concentrationHHI, 5200);
  assert.equal(result.metrics[3].value, '0/2');
  for (const name of ['贵州茅台债券', '贵州', '五粮液(600519)', '贵州茅台(999999)', '600519.HK']) {
    const { result: distinct } = await diagnose([{ name, weight: 50 }, { name: '贵州茅台', weight: 50 }]);
    assert.equal(distinct.concentrationHHI, 5000, name);
    assert.equal(distinct.metrics[3].value, '1/2', name);
  }
});
test('permutations and proportional weights preserve the complete deterministic result', async () => {
  const baseline = (await diagnose(pair)).result;
  for (const rows of [pair.toReversed(), [pair[1], pair[2], pair[0]], pair.map(h => ({ ...h, weight: h.weight / 10 })), pair.map(h => ({ ...h, weight: h.weight * 1e300 }))]) {
    assert.deepEqual((await diagnose(rows)).result, baseline);
  }
});
test('invalid inputs are excluded and empty portfolios never invoke advice or storage', async () => {
  for (const holdings of [[], null, [{ name: '', weight: 1 }, { name: 'A', weight: 0 }, { name: 'B', weight: -2 }, { name: 'C', weight: 'invalid' }]]) {
    assert.equal((await diagnose(holdings)).status, 400);
    assert.equal(saved, null); assert.equal(prompt, null);
  }
  authorized = false;
  try { assert.equal((await diagnose(pair)).status, 401); assert.equal(saved, null); assert.equal(prompt, null); }
  finally { authorized = true; }
});
test('risk classification preserves inclusive HHI and strict single-security boundaries', () => {
  const { portfolioRiskLevel } = load('src/lib/portfolio.ts');
  for (const [hhi, max, expected] of [[1799,20,'Low'],[1800,20,'Medium'],[2999,20,'Medium'],[3000,20,'High'],[4499,20,'High'],[4500,20,'Very High'],[2000,30,'Medium'],[2000,30.001,'High'],[2000,40,'High'],[2000,40.001,'Very High']]) {
    assert.equal(portfolioRiskLevel(hhi,max),expected,`${hhi}/${max}`);
  }
});
test('ambiguous exact aliases never collapse distinct stock identities', async () => {
  const { STOCKS } = load('src/lib/data/stocks.ts');
  const original = STOCKS[1].alias;
  STOCKS[1].alias = [...original, 'moutai'];
  try {
    const { result } = await diagnose([{ name: 'moutai', weight: 50 }, { name: '600519', weight: 50 }]);
    assert.equal(result.concentrationHHI, 5000);
    assert.equal(result.metrics[3].value, '1/2');
  } finally { STOCKS[1].alias = original; }
});
test('finite weights near Number.MAX_VALUE normalize without overflowing', async () => {
  const { result } = await diagnose([{ name: '贵州茅台', weight: 1.5e308 }, { name: '五粮液', weight: 1e308 }]);
  assert.equal(result.concentrationHHI, 5200);
  assert.equal(result.metrics[0].value, '60%');
  assert(result.holdings.every(h => Number.isFinite(h.weight)));
});
test('normalization does not promote exact 30% holdings across the strict risk boundary', async () => {
  for (const factor of [1, 0.1, 1e300]) {
    const holdings = [30, 20, 20, 20, 10].map((weight, i) => ({ name: `未知${i}`, weight: weight * factor }));
    const { result } = await diagnose(holdings);
    assert.equal(result.concentrationHHI, 2200);
    assert.equal(result.riskLevel, 'Medium');
  }
});
