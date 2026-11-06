import fs from 'node:fs/promises'
import assert from 'node:assert/strict'
import {fileURLToPath} from 'node:url'
import {buildPriceFeatures,predictTreeModel} from '../src/lib/forecast/model.ts'
const base=fileURLToPath(new URL('../../复赛深化/forecast-experiment-2026-10-03/',import.meta.url))
const read=async name=>JSON.parse(await fs.readFile(base+name,'utf8'))
const model=await read('model-v1.json'),predictions=await read('inference-parity-fixture.json'),features=await read('feature-parity-fixture.json')
let maximumPredictionError=0,maximumFeatureError=0
for(const row of predictions){const diff=Math.abs(predictTreeModel(model,row.features)-row.expected);maximumPredictionError=Math.max(maximumPredictionError,diff);assert.ok(diff<1e-12,`${row.code} ${row.date} inference mismatch`)}
for(const row of features){const actual=buildPriceFeatures(row.bars);assert.equal(actual.length,row.lastFeatures.length);actual.forEach((v,i)=>{const diff=Math.abs(v-row.lastFeatures[i]);maximumFeatureError=Math.max(maximumFeatureError,diff);assert.ok(diff<1e-12,`${row.code} feature ${i} mismatch`)})}
const report={verifiedAt:new Date().toISOString(),testPredictionsChecked:predictions.length,stocksFeaturesChecked:features.length,maximumPredictionError,maximumFeatureError,reference:'actual LightGBM Python outputs; no fake model response',status:'passed'}
await fs.writeFile(base+'inference-verification.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report))
