// Run from the repository root: node scripts/test_food_binding_browser.mjs
// Uses local Chrome, a compiled development frontend and a temporary SQLite database.
import assert from 'node:assert/strict'
import http from 'node:http'
import { spawn, spawnSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'

const api = 'http://127.0.0.1:5921'
const writes = []
const mock = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:5918')
  res.setHeader('Access-Control-Allow-Headers', 'content-type')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,OPTIONS')
  res.setHeader('Content-Type', 'application/json')
  if (req.method === 'OPTIONS') return res.end()
  const path = req.url.split('?')[0]
  // Only forward the routes under test. In particular, no AI endpoints.
  if (!/^\/api\/v1\/(?:health|food-normalization\/preview|food-logs(?:\/[0-9a-f-]+(?:\/confirm)?)?|nutrition\/daily)$/.test(path)) {
    res.statusCode = 404
    return res.end('{}')
  }
  let body = ''
  for await (const chunk of req) body += chunk
  if ((path === '/api/v1/food-logs' && req.method === 'POST') || req.method === 'PUT') writes.push(JSON.parse(body))
  const response = await fetch(api + req.url, {
    method: req.method, headers: { 'Content-Type': 'application/json' }, body: body || undefined,
  })
  res.statusCode = response.status
  res.end(await response.text())
})

const profile = await mkdtemp('/tmp/mealmind-chrome-')
let chrome, vite, ws, backend
const sleep = () => new Promise(r=>setTimeout(r,75))
async function until(fn) { for(let n=0;n<130;n++){ try { const result=await fn(); if(result)return result } catch {} await sleep() } throw Error('Timed out waiting for '+fn.toString()) }
try {
  await new Promise((resolve, reject) => {
    mock.once('error', reject)
    mock.listen(5919, '127.0.0.1', resolve)
  })
  backend=spawn('.venv/bin/python',['-m','uvicorn','app.main:app','--host','127.0.0.1','--port','5921'],
    {cwd:'backend',env:{...process.env,GEMINI_API_KEY:'',MEALMIND_ENVIRONMENT:'development',
      MEALMIND_FOOD_LOG_DB_PATH:profile+'/isolated.sqlite',MEALMIND_CATALOG_PERSONALIZATION:'false'},stdio:['ignore','ignore','pipe']})
  let backendOutput = ''
  backend.stderr.on('data', (chunk) => { backendOutput += chunk })
  await until(() => backend.exitCode === null && backendOutput.includes('Uvicorn running on ' + api))
  const env={...process.env,NODE_ENV:'development',VITE_API_BASE_URL:'http://127.0.0.1:5919'}
  const build=spawnSync('node',['node_modules/vite/bin/vite.js','build','--mode','development','--outDir',profile+'/site'],
    {cwd:'frontend',env,encoding:'utf8'})
  assert.equal(build.status,0,build.stdout+build.stderr)
  vite=spawn('node',['node_modules/vite/bin/vite.js','preview','--outDir',profile+'/site','--host','127.0.0.1','--port','5918','--strictPort'],
    {cwd:'frontend',env,stdio:'ignore'})
  await until(async()=> vite.exitCode === null && (await fetch('http://127.0.0.1:5918/log')).ok)
  chrome=spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    ['--headless','--remote-debugging-port=5920','--no-first-run','--no-default-browser-check','--user-data-dir='+profile,'about:blank'], {stdio:'ignore'})
  const target=await until(async()=> (await (await fetch('http://127.0.0.1:5920/json/list')).json()).find(x=>x.type==='page'))
  ws=new WebSocket(target.webSocketDebuggerUrl)
  await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j})
  let id=0; const tasks=new Map()
  ws.onmessage=({data})=>{const m=JSON.parse(data); if(m.id) { tasks.get(m.id)?.(m);tasks.delete(m.id) }}
  const cdp=(method,params={})=>new Promise((r,j)=>{
    tasks.set(++id,(m)=>m.error?j(Error(m.error.message)):r(m.result));ws.send(JSON.stringify({id,method,params}))
  })
  const js=async expression=>{
    const a=await cdp('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true})
    if(a.exceptionDetails) throw Error(a.exceptionDetails.exception?.description||a.exceptionDetails.text)
    return a.result.value
  }
  const visible=(phrase)=>until(()=>js(`document.body.innerText.includes(${JSON.stringify(phrase)})`))
  const click=async(label)=>{
    const predicate = `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)})`
    await until(()=>js(`!!(${predicate}) && !(${predicate}).matches(':disabled')`))
    await js(`(${predicate}).click()`)
  }
  const fill=async(sel,value)=>{
    await js(`(()=>{const e=document.querySelector(${JSON.stringify(sel)}); e.focus(); e.select()})()`)
    await cdp('Input.insertText',{text:value})
  }
  const raw = 'chicken_breast_skinless_boneless_raw'
  const catalog = JSON.parse(await readFile('data/nutrition/reference-v1.json', 'utf8'))
  const reference = catalog.foods.find((food) => food.food_id === raw)
  const formatter = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 1 })
  const nutrientLabels = { energy_kcal: '热量', protein_g: '蛋白质', carbohydrate_g: '碳水化合物', fat_g: '脂肪' }
  const cooked = 'chicken_breast_meat_stewed'
  const names = 'fieldset input[required][maxlength]'
  const unit = 'input[maxlength="120"]:not([required]):not([type="number"])'
  const open = (path) => cdp('Page.navigate', { url: 'http://127.0.0.1:5918' + path })
  const checkbox = () => js("document.querySelector('input[type=checkbox]').checked")
  const toggle = () => js("document.querySelector('input[type=checkbox]').click()")
  async function choose(foodId) {
    const query = `[...document.querySelectorAll('select')].find(el=>[...el.options].some(o=>o.value===${JSON.stringify(foodId)}))`
    await until(() => js(`!!(${query})`))
    await js(`(()=>{const el=${query};el.value=${JSON.stringify(foodId)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`)
  }
  async function confirmReference() {
    const label = await until(() => js("[...document.querySelectorAll('button')].find(el=>el.textContent.includes('确认参考：'))?.textContent.trim()"))
    await click(label)
  }
  function assertBinding(item, foodId, weight, expectedUnit) {
    assert.equal(item.name, '鸡胸肉')
    assert.equal(item.quantity, expectedUnit === '碗' ? 0.5 : 150)
    assert.equal(item.unit, expectedUnit)
    assert.equal(item.reference_binding?.food_id, foodId)
    assert.equal(item.reference_binding?.reference_version, 'usda-sr-legacy-v1')
    assert.equal(item.reference_binding?.confirmed, true)
    assert.equal(item.reference_binding?.edible_weight_confirmed, weight)
  }
  const date = new Date().toLocaleDateString('sv-SE')
  const logs = async () => {
    const result = spawnSync('.venv/bin/python', ['-c', `
import json, sqlite3, sys
from contextlib import closing
from pathlib import Path
with closing(sqlite3.connect(Path(sys.argv[1]).as_uri() + '?mode=ro', uri=True)) as db:
 print(json.dumps([json.loads(row[0]) for row in db.execute('SELECT document FROM food_logs')]))
`, profile + '/isolated.sqlite'], { cwd: 'backend', encoding: 'utf8' })
    return result.status === 0 ? JSON.parse(result.stdout) : []
  }
  async function save(foodId, weight, expectedUnit, revision) {
    const before = writes.length
    await click('保存草稿')
    await until(() => writes.length > before)
    const payload = writes.at(-1)
    assertBinding(payload.items[0], foodId, weight, expectedUnit)
    assert.equal(payload.expected_revision, revision === 1 ? undefined : revision - 1)
    const saved = await until(async () => (await logs()).find((log) => log.revision === revision && log.status === 'draft'))
    assertBinding(saved.items[0], foodId, weight, expectedUnit)
    return saved
  }
  async function reopen() {
    await click('纠正草稿')
    await visible('参考已随草稿保存')
    await click('查看食物匹配')
    await until(() => js("!!document.querySelector('input[type=checkbox]')"))
    assert.equal(await checkbox(), true)
  }
  async function settle({ foodId, weight, expectedUnit, shouldCalculate, reason }) {
    await click('确认实际吃过')
    await visible('食物记录已确认')
    const confirmed = await until(async () => (await logs()).find((log) => log.status === 'confirmed'))
    assertBinding(confirmed.items[0], foodId, weight, expectedUnit)
    const daily = await (await fetch(api + '/api/v1/nutrition/daily?date=' + date)).json()
    assert.equal(daily.item_count, 1)
    assert.equal(daily.calculated_item_count, shouldCalculate ? 1 : 0)
    const result = daily.logs.find((log) => log.log_id === confirmed.id).items[0]
    assert.equal(result.provenance.food_id, foodId)
    assert.equal(result.status, shouldCalculate ? 'calculated' : 'not_calculable')
    if (shouldCalculate) {
      assert.equal(Number(result.edible_grams), 150)
      assert.deepEqual(Object.keys(result.nutrients).sort(), ['carbohydrate_g','energy_kcal','fat_g','protein_g'])
      assert.equal(result.provenance.fdc_id, reference.source.fdc_id)
      for (const [key, value] of Object.entries(result.nutrients)) {
        assert.notEqual(value, null)
        assert(Math.abs(Number(value) - Number(reference.nutrients[key].amount) * 1.5) < 1e-9)
      }
    } else {
      assert.deepEqual(result.reasons, [reason])
      assert.equal(result.edible_grams, null)
      assert(Object.values(result.nutrients).every((value) => value === null))
    }
    await open('/today')
    const zh = shouldCalculate ? '已计算 1/1' : '已计算 0/1'
    await visible(zh)
    if (shouldCalculate) {
      const displayed = await js(`Array.from(document.getElementById('nutrition-title').closest('section')
        .querySelector('dl').querySelectorAll('dt'), (label) => [label.textContent, label.nextElementSibling.textContent])`)
      assert.deepEqual(Object.fromEntries(displayed), Object.fromEntries(Object.entries(result.nutrients).map(([key, value]) => [
        nutrientLabels[key], `${formatter.format(Number(value))} ${key === 'energy_kcal' ? '千卡' : '克'}`,
      ])))
    }
    // Delete only the synthetic entry from this test's isolated backend.
    const deleted = await fetch(api + '/api/v1/food-logs/' + confirmed.id + '?expected_revision=' + confirmed.revision, { method: 'DELETE' })
    assert.equal(deleted.status, 204)
    assert.deepEqual(await logs(), [])
  }

  await cdp('Emulation.setDeviceMetricsOverride', { width: 360, height: 800, deviceScaleFactor: 1, mobile: false })
  for (const scenario of ['A','B','C','D','E','F','G']) {
    const expectedUnit = scenario === 'G' ? '碗' : 'g'
    await open('/log')
    await until(() => js(`!!document.querySelector(${JSON.stringify(names)})`))
    await fill(names, '鸡胸肉')
    await fill('input[type=number]', scenario === 'G' ? '0.5' : '150')
    await fill(unit, expectedUnit)
    await click('查看食物匹配')
    await choose(raw)
    if (scenario === 'B') {
      await confirmReference()
      await toggle()
    } else {
      if (scenario !== 'G') await toggle()
      await confirmReference()
    }
    let foodId = raw
    if (scenario === 'E') await toggle()
    if (scenario === 'F') {
      await choose(cooked)
      assert.equal(await checkbox(), false)
      await fill(names, '青菜')
      await fill(names, '鸡胸肉')
      await click('查看食物匹配')
      await choose(cooked)
      assert.equal(await checkbox(), false)
      await confirmReference()
      foodId = cooked
    }
    if (scenario === 'G') {
      await visible('暂无已验证的重量换算')
      assert.equal(await js("!!document.querySelector('input[type=checkbox]')"), false)
    }
    const weight = 'ABCD'.includes(scenario)
    await save(foodId, weight, expectedUnit, 1)
    if (scenario === 'C' || scenario === 'D') {
      await reopen()
      if (scenario === 'D') await confirmReference()
      await save(foodId, true, expectedUnit, 2)
    }
    await settle({ foodId, weight, expectedUnit, shouldCalculate: weight,
      reason: scenario === 'G' ? 'unsupported_serving_conversion' : 'portion_needs_review' })
    console.log(`PASS ${scenario}: outgoing payload → SQLite → confirmed log → Daily Nutrition → Today`)
  }
} finally {
  ws?.close()
  chrome?.kill()
  vite?.kill()
  backend?.kill()
  mock.close()
  await sleep()
  await rm(profile, { recursive: true, force: true })
}
