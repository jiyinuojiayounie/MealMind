// Run from the repository root: node scripts/test_food_binding_browser.mjs
// Uses local Chrome, a compiled development frontend and a temporary SQLite database.
import assert from 'node:assert/strict'
import http from 'node:http'
import { spawn, spawnSync } from 'node:child_process'
import { mkdtemp, readFile, rm } from 'node:fs/promises'

const api = 'http://127.0.0.1:5921'
const writes = []
const planningRequests = []
const mock = http.createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'http://127.0.0.1:5918')
  res.setHeader('Access-Control-Allow-Headers', 'content-type')
  res.setHeader('Access-Control-Allow-Methods', 'GET,POST,PUT,OPTIONS')
  res.setHeader('Content-Type', 'application/json')
  if (req.method === 'OPTIONS') return res.end()
  const path = req.url.split('?')[0]
  // Recognition is forwarded only to the isolated backend with an injected fixture provider.
  if (!/^\/api\/v1\/(?:health|meal-plans\/generate|replan\/(?:context|preview)|food-normalization\/preview|food-logs(?:\/recognize-text|\/[0-9a-f-]+(?:\/confirm)?)?|nutrition\/daily)$/.test(path)) {
    res.statusCode = 404
    return res.end('{}')
  }
  let body = ''
  for await (const chunk of req) body += chunk
  if ((path === '/api/v1/food-logs' && req.method === 'POST') || req.method === 'PUT') writes.push(JSON.parse(body))
  if (path === '/api/v1/meal-plans/generate') planningRequests.push(req.url)
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
  backend=spawn('.venv/bin/python',['-m','uvicorn','food_workflow_browser_app:app','--app-dir','tests','--host','127.0.0.1','--port','5921'],
    {cwd:'backend',env:{...process.env,GEMINI_API_KEY:'',MEALMIND_ENVIRONMENT:'development',
      MEALMIND_FOOD_LOG_DB_PATH:profile+'/isolated.sqlite',MEALMIND_CATALOG_PERSONALIZATION:'false'},stdio:['ignore','ignore','pipe']})
  let backendOutput = ''
  backend.stderr.on('data', (chunk) => { backendOutput += chunk })
  await until(() => backend.exitCode === null && backendOutput.includes('Uvicorn running on ' + api))
  const env={...process.env,NODE_ENV:'development',VITE_CATALOG_PLANNING_PREVIEW:'true',VITE_API_BASE_URL:'http://127.0.0.1:5919'}
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
    const predicate = `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(label)} && b.getClientRects().length > 0)`
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
  const recognizedCases = [
    { description: '吃了150g去皮去骨鸡胸肉（生）', amount: 150, evidence: '150g', bind: true, calculate: true },
    { description: '吃了150g去皮去骨鸡胸肉（生）', amount: 150, evidence: '150g', calculate: false, reason: 'portion_needs_review' },
    { description: '吃了150g去皮去骨鸡胸肉（生）', amount: 150, evidence: '150g', editAmount: 151, calculate: false, reason: 'portion_needs_review' },
    { description: '买了200g鸡胸肉，只吃了一部分', amount: null, evidence: '200g', calculate: false },
    { description: '半碗糙米饭', amount: .5, evidence: '半碗', calculate: false },
    { description: '吃了些低芥酸菜籽油', amount: null, evidence: null, calculate: false, reason: 'quantity_unknown' },
  ]
  for (const scenario of recognizedCases) {
    await open('/log')
    await until(() => js("!!document.querySelector('textarea')"))
    await fill('textarea', scenario.description)
    await click('AI 识别食物')
    await visible('原文：「')
    if (scenario.amount === null) {
      assert.equal(await js("document.querySelector('input[type=number]').value"), '')
    } else {
      assert.equal(Number(await js("document.querySelector('input[type=number]').value")), scenario.amount)
    }
    const before = writes.length
    await click('保存草稿')
    await until(() => writes.length > before)
    assert.equal(writes.at(-1).source, 'ai_text')
    assert.equal(writes.at(-1).items[0].quantity, scenario.amount)
    assert.equal(writes.at(-1).items[0].recognition_evidence.portion_text, scenario.evidence)
    let draft = await until(async () => (await logs()).find((log) => log.status === 'draft'))
    assert.equal(draft.recognition_weight_review, true)
    assert.deepEqual(draft.items[0].recognition_evidence, writes.at(-1).items[0].recognition_evidence)
    if (scenario.bind) {
      await click('纠正草稿')
      await visible('原文：「')
      await click('查看食物匹配')
      await until(() => js("!!document.querySelector('input[type=checkbox]')"))
      await toggle()
      await confirmReference()
      await click('保存草稿')
      draft = await until(async () => (await logs()).find((log) => log.status === 'draft' && log.revision === 2))
      assert.equal(writes.at(-1).items[0].reference_binding.edible_weight_confirmed, true)
      assert.equal(draft.items[0].reference_binding.food_id, raw)
      assert.deepEqual(draft.items[0].recognition_evidence, writes.at(-1).items[0].recognition_evidence)
    }
    if (scenario.editAmount) {
      await click('纠正草稿')
      await visible('原文：「')
      await fill('input[type=number]', String(scenario.editAmount))
      await until(() => js("!document.body.innerText.includes('原文：「')"))
      await click('保存草稿')
      draft = await until(async () => (await logs()).find((log) => log.status === 'draft' && log.revision === 2))
      assert.equal(writes.at(-1).items[0].recognition_evidence, undefined)
      assert.equal(draft.items[0].recognition_evidence, undefined)
      assert.equal(draft.items[0].quantity, scenario.editAmount)
      assert.equal(draft.recognition_weight_review, true)
    }
    await click('确认实际吃过')
    const confirmed = await until(async () => (await logs()).find((log) => log.status === 'confirmed'))
    assert.deepEqual(confirmed.items, draft.items)
    const daily = await (await fetch(api + '/api/v1/nutrition/daily?date=' + date)).json()
    const result = daily.logs.find((log) => log.log_id === confirmed.id).items[0]
    assert.equal(result.status, scenario.calculate ? 'calculated' : 'not_calculable')
    assert.equal(daily.calculated_item_count, scenario.calculate ? 1 : 0)
    if (scenario.calculate) {
      assert.equal(Number(result.edible_grams), 150)
      assert(Object.values(result.nutrients).every((value) => value !== null))
    } else {
      assert.equal(result.edible_grams, null)
      if (scenario.reason) assert(result.reasons.includes(scenario.reason))
    }
    await open('/today')
    await visible(scenario.calculate ? '已计算 1/1' : '已计算 0/1')
    const timeOrigin = await js('performance.timeOrigin')
    await cdp('Page.reload')
    await until(async () => (await js('performance.timeOrigin')) !== timeOrigin)
    await visible(scenario.calculate ? '已计算 1/1' : '已计算 0/1')
    const deleted = await fetch(api + '/api/v1/food-logs/' + confirmed.id + '?expected_revision=' + confirmed.revision, { method: 'DELETE' })
    assert.equal(deleted.status, 204)
    console.log(`PASS recognition: ${scenario.description}; bound=${Boolean(scenario.bind)}; calculated=${scenario.calculate}`)
  }

  const cookingCases = [
    ['炒菜用了8g油，但锅里还剩一些。', [''], [''], '炒菜用了8g油'],
    ['炒菜用了8g油，但锅里还剩一些。 ', [''], [''], '炒菜用了8g油'],
    ['炒菜用了8g油，但锅里还剩一些', [''], [''], '炒菜用了8g油'],
    ['我吃了6g低芥酸菜籽油。', ['低芥酸菜籽油'], ['6'], null],
    ['做菜用了9g菜籽油，这些油没吃，倒掉了。', [''], [''], '做菜用了9g菜籽油'],
    ['我吃了150g糙米饭、一个鸡蛋，炒菜用了8g油，但锅里还剩一些。', ['糙米饭', '鸡蛋'], ['150', '1'], '炒菜用了8g油'],
    ['没有吃午饭。', [''], [''], null],
    ['我吃了食物，但测试提供方出错。', [''], [''], null, true],
  ]
  for (const [description, expectedNames, expectedQuantities, cookingQuote, fails] of cookingCases) {
    await open('/log')
    await until(() => js("!!document.querySelector('textarea')"))
    await fill('textarea', description)
    const count = writes.length
    await click('AI 识别食物')
    const errorText = 'AI 未能生成有效的识别建议。请重试或手动录入。'
    if (fails) {
      await visible(errorText)
    } else if (cookingQuote) {
      await visible('烹调用量证据。实际食用量未知。')
      assert(await js(`[...document.querySelectorAll('li')].some(el=>el.textContent===${JSON.stringify(cookingQuote)})`))
    } else if (expectedNames[0]) {
      await visible('原文：「')
    } else {
      await visible('没有识别到食物。你可以手动添加，或调整描述后重试。')
    }
    assert.deepEqual(await js(`[...document.querySelectorAll(${JSON.stringify(names)})].map(el=>el.value)`), expectedNames)
    assert.deepEqual(await js("[...document.querySelectorAll('input[type=number]')].map(el=>el.value)"), expectedQuantities)
    assert.equal(await js(`document.body.innerText.includes(${JSON.stringify(errorText)})`), Boolean(fails))
    assert.equal(writes.length, count)
    assert.deepEqual(await logs(), [])
    console.log(`PASS cooking evidence with mocked provider: ${description}`)
  }

  async function pickOption(value) {
    await until(() => js(`[...document.querySelectorAll('select')].some(el=>[...el.options].some(o=>o.value===${JSON.stringify(value)}))`))
    await js(`(()=>{const select=[...document.querySelectorAll('select')].find(el=>[...el.options].some(o=>o.value===${JSON.stringify(value)})); select.value=${JSON.stringify(value)}; select.dispatchEvent(new Event('change',{bubbles:true}));})()`)
  }
  async function clickPlanningOptions() {
    await visible('更多选项')
    await js(`[...document.querySelectorAll('summary')].find(el => el.textContent.includes('更多选项')).click()`)
  }
  async function submitPlan(text, button = '生成餐单') {
    await until(() => js("!!document.querySelector('textarea[name=requirements]')"))
    await fill('textarea[name=requirements]', text)
    await click(button)
  }
  const tomorrow = '帮我安排明天的一日三餐。我一个人做饭，偏爱中式家常菜，想吃得健康但也要好吃。早餐最好10分钟以内，中饭和晚饭各20分钟以内，食材要常见，尽量少洗锅，不要推荐重复的菜。'
  await open('/')
  await visible('直接开始')
  await js("Array.from(document.querySelectorAll('a')).find(a=>a.textContent.includes('直接开始')).click()")
  await until(() => js("location.pathname === '/today'"))
  await visible('今天吃什么？')
  assert(await js("location.pathname === '/today' && !!document.querySelector('.blind-wheel') && !document.querySelector('.blind-result')"))
  const navLinks = () => js(`[...document.querySelectorAll('.site-nav a')].map(a => [a.getAttribute('href'), a.textContent.trim()])`)
  assert.deepEqual(await navLinks(), [['/today', '今日'], ['/plan', '智能规划'], ['/log', '记录'], ['/profile', '我的']])
  assert(await js(`!document.querySelector('#shortcuts-title, .shortcut, a[href="/pantry"]')`))
  const followNav = (path) => js(`[...document.querySelectorAll('.site-nav a')].find(a=>a.getAttribute('href')===${JSON.stringify(path)}).click()`)
  await followNav('/plan')
  await until(() => js("location.pathname === '/plan'"))
  await submitPlan('我只有番茄、鸡蛋和土豆，帮我规划一顿晚餐。')
  await visible('测试番茄鸡蛋土豆')
  assert.deepEqual(await js(`[...document.querySelectorAll('article ul li')].map(node=>node.firstElementChild.textContent)`), ['番茄', '鸡蛋', '土豆'])
  await followNav('/log')
  await until(() => js("location.pathname === '/log' && !!document.querySelector('main h1')"))
  await followNav('/profile')
  await until(() => js("location.pathname === '/profile'"))
  await visible('个人设置')
  await followNav('/today')
  await until(() => js("location.pathname === '/today'"))
  await visible('今天吃什么？')
  await open('/pantry')
  await until(() => js("location.pathname === '/today' && !!document.querySelector('.blind-wheel')"))
  assert(await js(`!document.querySelector('a[href="/pantry"]') && !document.body.innerText.includes('快捷操作')`))
  console.log('PASS navigation: Today, Smart Planning, Food Log, Profile, legacy Pantry redirect, and text-only ingredients')

  const writesBeforeDraw = writes.length
  const drawMetrics = await js(`(() => {
    const counts = { requests: 0, writes: 0 }
    const fetch = window.fetch
    window.fetch = (...args) => { counts.requests++; return fetch(...args) }
    const originals = Object.fromEntries(['put', 'add', 'delete', 'clear'].map((key) => [key, IDBObjectStore.prototype[key]]))
    for (const [key, original] of Object.entries(originals)) {
      IDBObjectStore.prototype[key] = function (...args) { counts.writes++; return original.apply(this, args) }
    }
    window.finishBlindBoxTest = () => {
      window.fetch = fetch
      Object.assign(IDBObjectStore.prototype, originals)
      return counts
    }
    return true
  })()`)
  assert(drawMetrics)
  const resultTitle = () => js("document.querySelector('.blind-meal h2')?.innerText")
  const decoration = () => js(`[...document.querySelectorAll('.blind-wheel-spoke span')].map(icon => icon.textContent)`)
  const icons = ['🥬', '🍜', '🍅', '🍚', '🥕', '🍳', '🍄', '🥟']
  assert.deepEqual(await decoration(), icons)
  await js(`window.originalBlindBoxRandom = Math.random; Math.random = () => 0.999999`)
  const lastAdded = ['鸡丝生菜卷饼', '青菜豆腐煎饼配木耳', '青菜豆腐煎饼配木耳']
  const viewports = [[375, 667], [390, 844], [360, 740]]
  const bounds = () => js(`(() => {
    const rect = selector => document.querySelector(selector).getBoundingClientRect()
    return {
      wheelTop: Math.round(rect('.blind-wheel').top),
      wheelWidth: document.querySelector('.blind-wheel').offsetWidth,
      redrawBottom: Math.round(rect('.blind-stage > button').bottom),
      resultTop: Math.round(rect('.blind-result').top),
      resultBottom: Math.round(rect('.blind-meal').bottom),
      navTop: Math.round(rect('.site-nav').top),
      scrollY: window.scrollY,
    }
  })()`)
  async function pressKey(key, code) {
    await cdp('Input.dispatchKeyEvent', { type:'rawKeyDown', key, windowsVirtualKeyCode:code })
    await cdp('Input.dispatchKeyEvent', { type:'keyUp', key, windowsVirtualKeyCode:code })
  }
  for (const [index, label] of ['早餐', '午餐', '晚餐'].entries()) {
    const [width, height] = viewports[index]
    await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: true })
    await js('window.scrollTo(0, 0)')
    await js(`document.querySelectorAll('input[name=blind-box-slot]')[${index}].click()`)
    if (index === 0) {
      const idle = await js(`({
        wheelWidth: document.querySelector('.blind-wheel').offsetWidth,
        drawBottom: Math.round(document.querySelector('.blind-stage > button').getBoundingClientRect().bottom),
        navTop: Math.round(document.querySelector('.site-nav').getBoundingClientRect().top),
      })`)
      assert(idle.wheelWidth >= 210 && idle.drawBottom <= idle.navTop, JSON.stringify(idle))
      console.log('PASS Blind Box idle mobile', JSON.stringify(idle))
      assert(await js(`(() => {
        const button = document.querySelector('.blind-stage > button')
        button.click()
        button.click()
        return true
      })()`))
      await visible('转盘转动中…')
      assert(await js("document.querySelector('.blind-stage > button').disabled && !document.querySelector('.blind-result')"))
      assert(await js("[...document.querySelectorAll('[name=blind-box-slot]')].every(input=>input.matches(':disabled'))"))
    } else {
      await click('开始抽取')
    }
    const first = await until(resultTitle)
    assert.equal(first, lastAdded[index])
    await visible('一人份')
    assert(await js(`document.querySelector('.blind-meta span').textContent === ${JSON.stringify(label)}`))
    assert.deepEqual(await decoration(), icons)
    assert(await js("!document.querySelector('.blind-wheel [data-recipe-id]')"))
    assert(await js("document.querySelector('.blind-meal').getBoundingClientRect().top >= document.querySelector('.blind-wheel').getBoundingClientRect().bottom"))
    await until(() => js("document.querySelector('.blind-result').getAnimations().every(animation => animation.playState === 'finished')"))
    const measurement = await bounds()
    assert(measurement.wheelTop >= 0 && measurement.wheelWidth <= 80
      && measurement.resultBottom <= measurement.navTop && measurement.redrawBottom <= measurement.navTop,
      JSON.stringify({ width, height, ...measurement }))
    console.log('PASS Blind Box viewport', JSON.stringify({ width, height, ...measurement }))
    assert(await js("!document.querySelector('#blind-box-recipe').open"))
    await click('查看做法')
    assert(await js("document.querySelector('#blind-box-recipe').matches(':modal') && document.querySelector('#blind-box-recipe ol li') !== null"))
    await pressKey('Tab', 9)
    assert(await js("document.querySelector('#blind-box-recipe').contains(document.activeElement)"))
    await pressKey('Escape', 27)
    await until(() => js("!document.querySelector('#blind-box-recipe').open && document.activeElement.textContent === '查看做法'"))
    await js('window.scrollTo(0, 20)')
    const before = await bounds()
    await click('再抽一次')
    await visible('转盘转动中…')
    assert.equal(await resultTitle(), first)
    const during = await bounds()
    assert.deepEqual([during.scrollY, during.wheelWidth], [before.scrollY, before.wheelWidth])
    await until(async () => { const title = await resultTitle(); return title && title !== first })
    const after = await bounds()
    assert.deepEqual([after.scrollY, after.wheelWidth], [before.scrollY, before.wheelWidth])
    assert.deepEqual(await decoration(), icons)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))
  }
  await js("document.querySelector('.blind-restrictions summary').click()")
  await js("document.querySelector('.blind-restrictions input[type=checkbox]').click()")
  assert.equal(await resultTitle(), undefined)
  await click('开始抽取')
  await visible('暂无可推荐餐食')
  assert.equal(await resultTitle(), undefined)
  assert(await js('document.documentElement.scrollWidth <= innerWidth'))
  await js("Math.random = window.originalBlindBoxRandom; delete window.originalBlindBoxRandom")
  const onDisk = await logs()
  assert.deepEqual(onDisk, [])
  assert.equal(writes.length, writesBeforeDraw)
  assert.deepEqual(await js('window.finishBlindBoxTest()'), { requests: 0, writes: 0 })
  await cdp('Emulation.setDeviceMetricsOverride', { width: 375, height: 667, deviceScaleFactor: 1, mobile: true })
  await js('window.scrollTo(0, 0)')
  await click('English')
  await visible('No meal can be recommended')
  assert.deepEqual(await navLinks(), [['/today', 'Today'], ['/plan', 'Smart Planning'], ['/log', 'Food Log'], ['/profile', 'Profile']])
  await js("document.querySelector('.blind-restrictions input[type=checkbox]').click()")
  await js("document.querySelector('.blind-restrictions').open = false")
  await cdp('Emulation.setEmulatedMedia', { features: [{name:'prefers-reduced-motion', value:'reduce'}] })
  await js('window.mealmindOriginalRandom = Math.random; Math.random = () => 0.999999')
  await click('Start draw')
  await visible('One serving')
  const englishMobile = await bounds()
  assert(englishMobile.resultBottom <= englishMobile.navTop, JSON.stringify(englishMobile))
  console.log('PASS Blind Box English mobile', JSON.stringify(englishMobile))
  assert(await js("!document.querySelector('.blind-wheel-disc').classList.contains('is-spinning')"))
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false })
  const desktop = await bounds()
  assert(desktop.wheelWidth >= 260)
  console.log('PASS Blind Box desktop', JSON.stringify(desktop))
  assert.deepEqual(await decoration(), icons)
  await cdp('Emulation.setEmulatedMedia', { features: [] })
  await cdp('Emulation.clearDeviceMetricsOverride')
  await js('Math.random = window.mealmindOriginalRandom; delete window.mealmindOriginalRandom')
  await click('中文')
  await visible('一人份')
  console.log('PASS Today hero: decorative wheel, three slots, redraw, reduced motion, bilingual mobile and desktop, zero fetches and plan writes')

  await open('/plan')
  await until(() => js("!!document.querySelector('textarea[name=requirements]')"))
  for (const width of [375, 1280]) {
    await cdp('Emulation.setDeviceMetricsOverride', { width, height: 800, deviceScaleFactor: 1, mobile: width < 500 })
    assert(await js("!document.querySelector('option[value=catalog], option[value=prompt_only]')"))
  }
  await cdp('Emulation.clearDeviceMetricsOverride')
  await submitPlan('帮我生成今天的一日三餐')
  assert.equal(planningRequests.at(-1), '/api/v1/meal-plans/generate?infer_scope=true')
  await visible('测试早餐炒蛋吐司')
  await visible('测试香菇青菜焖饭')
  await visible('测试豆腐皮炒西葫芦')
  await open('/plan')
  await clickPlanningOptions()
  await pickOption('dinner')
  await submitPlan('晚餐只做一道菜')
  await visible('测试替换晚餐番茄豆腐饭')
  await open('/plan')
  await submitPlan('我对花生过敏，请帮我安排晚餐')
  await visible('MealMind 无法核验生成餐食是否符合这项饮食限制。')
  await open('/plan')
  await submitPlan(tomorrow)
  await visible('测试早餐炒蛋吐司')
  await visible('测试午餐豆腐小白菜饭')
  await visible('测试晚餐番茄鸡肉面')
  await submitPlan(tomorrow.replace('明天', '今天'))
  await click('加入计划')
  await visible('当前餐单 · 第 1 版')
  await submitPlan('模拟失败')
  await visible('暂时无法生成餐单，请重试或调整需求。')
  await visible('当前餐单 · 第 1 版')
  await submitPlan('模拟服务暂不可用', '重试')
  await visible('餐食规划服务暂不可用，请稍后重试。')
  await visible('当前餐单 · 第 1 版')
  assert(planningRequests.every((url) => !url.includes('planning_mode')))
  console.log('PASS Smart Planning: mobile/desktop selector absent, default API path, results, saving and errors')

  await open('/log')
  await until(() => js(`!!document.querySelector(${JSON.stringify(names)})`))
  await fill(names, '熟长粒糙米')
  await fill('input[type=number]', '150')
  await fill(unit, 'g')
  await pickOption('lunch')
  await click('保存草稿')
  await until(async () => (await logs()).some((record) => record.status === 'draft'))
  const beforeConfirm = await (await fetch(api + '/api/v1/nutrition/daily?date=' + date)).json()
  assert.equal(beforeConfirm.status, 'no_confirmed_logs')
  await click('确认实际吃过')
  const smokeLog = await until(async () => (await logs()).find((record) => record.status === 'confirmed'))
  assert.equal(smokeLog.meal_type, 'lunch')
  await open('/today')
  await visible('已计算 1/1')
  await visible('已锁定餐次：午餐。')
  await js("Array.from(document.querySelectorAll('summary')).find(s=>s.textContent.trim()==='重新规划一餐').click()")
  assert(await js("!document.querySelector('option[value=catalog], option[value=prompt_only]')"))
  await pickOption('none_declared')
  await click('生成预览')
  await visible('测试替换晚餐番茄豆腐饭')
  await click('保留当前餐单')
  await visible('当前餐单 · 第 1 版')
  await click('生成预览')
  await visible('测试替换晚餐番茄豆腐饭')
  await click('接受并保存这一餐')
  await visible('当前餐单 · 第 2 版')
  await open('/today')
  await visible('原始采纳餐单 · 第 1 版')
  await visible('当前餐单 · 第 2 版')
  const savedMeals = await js(`Array.from(document.querySelectorAll('details')).filter(el=>el.querySelector('summary')?.textContent.includes('版')).map(el=>el.textContent)`)
  assert(savedMeals.some(text=>text.includes('第 2 版') && text.includes('测试早餐炒蛋吐司') &&
    text.includes('测试午餐豆腐小白菜饭') && text.includes('测试替换晚餐番茄豆腐饭')))
  assert(savedMeals.some(text=>text.includes('第 1 版') && text.includes('测试晚餐番茄鸡肉面')))
  const mealSnapshot = (day = date) => js(`new Promise((resolve, reject) => {
    const open = indexedDB.open('mealmind-meal-plans')
    open.onerror = reject
    open.onsuccess = () => {
      const db = open.result
      const tx = db.transaction('plans')
      const get = tx.objectStore('plans').get(${JSON.stringify(day)})
      get.onsuccess = () => resolve(get.result)
      get.onerror = reject
      tx.oncomplete = () => db.close()
    }
  })`)
  const initial = await mealSnapshot()
  await visible('今天吃什么？')
  await js(`document.querySelectorAll('input[name=blind-box-slot]')[1].click()`)
  await click('开始抽取')
  await click('加入计划')
  await click('检查餐次并保存')
  await visible('这餐已有确认的食用记录，无法替换。')
  assert.deepEqual(await mealSnapshot(), initial)
  await js(`document.querySelectorAll('input[name=blind-box-slot]')[2].click()`)
  await js('Math.random = () => 0')
  await click('开始抽取')
  await visible('鸡蛋小白菜炒饭')
  await click('查看做法')
  await visible('熟米饭 170 g')
  await click('关闭')
  await click('加入计划')
  await click('检查餐次并保存')
  await visible('当前餐食：测试替换晚餐番茄豆腐饭')
  await click('取消')
  assert.deepEqual(await mealSnapshot(), initial)
  await until(() => js("!document.querySelector('#blind-box-save').open && document.activeElement.textContent === '加入计划'"))
  await click('加入计划')
  await click('检查餐次并保存')
  await visible('当前餐食：测试替换晚餐番茄豆腐饭')
  await js(`new Promise((resolve, reject) => {
    const open = indexedDB.open('mealmind-meal-plans')
    open.onerror = reject
    open.onsuccess = () => {
      const db = open.result
      const tx = db.transaction('plans', 'readwrite')
      const record = ${JSON.stringify(initial)}
      record.revision++
      record.revisions.push({ ...record.revisions.at(-1), revision: record.revision, acceptanceId: crypto.randomUUID() })
      tx.objectStore('plans').put(record)
      tx.oncomplete = () => { db.close(); resolve(true) }
      tx.onabort = reject
    }
  })`)
  await click('确认替换')
  await visible('餐单或食用记录已更新')
  assert.equal((await mealSnapshot()).revision, 3)
  await click('检查餐次并保存')
  await visible('当前餐食：测试替换晚餐番茄豆腐饭')
  await js(`(() => {
    const button = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '确认替换')
    button.click()
    button.click()
  })()`)
  await visible('已保存到餐单。')
  await visible('当前餐单 · 第 4 版')
  const accepted = await mealSnapshot()
  assert.equal(accepted.revision, 4)
  assert.deepEqual(accepted.revisions.slice(0, 2), initial.revisions)
  assert.equal(accepted.revisions.at(-1).source, 'blind_box')
  assert.deepEqual(accepted.revisions.at(-1).plan.meals.slice(0, 2), initial.revisions.at(-1).plan.meals.slice(0, 2))
  assert.equal(accepted.revisions.at(-1).plan.meals[2].dishes[0].ingredients[0].name, '熟米饭')
  assert.deepEqual(await logs(), [smokeLog])
  await open('/today')
  await visible('当前餐单 · 第 4 版')
  await js("Array.from(document.querySelectorAll('summary')).find(s=>s.textContent.trim()==='重新规划一餐').click()")
  assert(await js("!document.querySelector('option[value=catalog], option[value=prompt_only]')"))
  await pickOption('none_declared')
  await click('生成预览')
  await visible('测试替换晚餐番茄豆腐饭')
  await click('保留当前餐单')
  assert.deepEqual(await mealSnapshot(), accepted)
  await open('/blind-box')
  await js("Math.random = () => 0")
  await click('开始抽取')
  await visible('鸡蛋小白菜炒饭')
  await click('加入计划')
  const futureDate = '2099-01-02'
  await js(`(() => {
    const dateInput = document.querySelector('#blind-box-save input[type=date]')
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(dateInput, ${JSON.stringify(futureDate)})
    dateInput.dispatchEvent(new Event('input', { bubbles: true }))
  })()`)
  await pickOption('lunch')
  await click('检查餐次并保存')
  await visible('将这份餐食加入所选餐次？')
  await click('确认加入计划')
  await visible('已保存到餐单。')
  const future = await mealSnapshot(futureDate)
  assert.equal(future.revision, 1)
  assert.deepEqual(future.revisions[0].plan.meals.map((meal) => meal.meal_type), ['lunch'])
  assert.deepEqual(await mealSnapshot(), accepted)
  assert.deepEqual(await logs(), [smokeLog])
  console.log('PASS Blind Box save: selected date and slot, lock, cancel, stale version, replacement, duplicate click, reload and Replan compatibility')
  assert.equal((await fetch(api + '/api/v1/food-logs/' + smokeLog.id + '?expected_revision=' + smokeLog.revision,
                           { method: 'DELETE' })).status, 204)
  console.log('PASS Core MVP: browser Plan → Log → Analyze → Replan; first version and locked lunch preserved')

  // Manual entry through the UI, then a synthetic pre-policy AI record in this database only.
  await open('/log')
  await until(() => js(`!!document.querySelector(${JSON.stringify(names)})`))
  await fill(names, '低芥酸菜籽油')
  await fill('input[type=number]', '6')
  await fill(unit, 'g')
  await click('保存草稿')
  await until(async () => (await logs()).some((log) => log.status === 'draft'))
  assert.equal(writes.at(-1).source, 'manual_text')
  await click('确认实际吃过')
  const manual = await until(async () => (await logs()).find((log) => log.status === 'confirmed'))
  assert.equal(manual.recognition_weight_review, undefined)
  await open('/today')
  await visible('已计算 1/1')
  assert.equal((await fetch(api + '/api/v1/food-logs/' + manual.id + '?expected_revision=' + manual.revision,
                           { method: 'DELETE' })).status, 204)

  const legacyDraft = await (await fetch(api + '/api/v1/food-logs', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      source: 'ai_text', consumed_at: date + 'T12:00:00+08:00',
      items: [{ name: '低芥酸菜籽油', quantity: 6, unit: 'g' }],
    }),
  })).json()
  const legacyResponse = await fetch(api + '/api/v1/food-logs/' + legacyDraft.id + '/confirm', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: 1 }),
  })
  assert.equal(legacyResponse.status, 200)
  const legacy = await legacyResponse.json()
  delete legacy.recognition_weight_review
  const legacySeed = spawnSync('.venv/bin/python', ['-c', `
import sqlite3, sys
from contextlib import closing
with closing(sqlite3.connect(sys.argv[1])) as db, db:
 db.execute('UPDATE food_logs SET document = ? WHERE id = ?', (sys.argv[2], sys.argv[3]))
`, profile + '/isolated.sqlite', JSON.stringify(legacy), legacy.id], { cwd: 'backend', encoding: 'utf8' })
  assert.equal(legacySeed.status, 0, legacySeed.stderr)
  const beforeAnalysis = await readFile(profile + '/isolated.sqlite')
  await open('/today')
  await visible('已计算 1/1')
  assert.deepEqual(await readFile(profile + '/isolated.sqlite'), beforeAnalysis)
  console.log('PASS manual and pre-policy unbound entries: SQLite → Daily Nutrition → Today')
} finally {
  ws?.close()
  chrome?.kill()
  vite?.kill()
  backend?.kill()
  mock.close()
  await sleep()
  await rm(profile, { recursive: true, force: true })
}
