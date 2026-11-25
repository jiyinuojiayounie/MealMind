// Run from the repository root after npm run build in frontend/.
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createServer } from 'node:http'
import { mkdtemp, readFile, rm, readdir } from 'node:fs/promises'

const chromePath = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const root = new URL('../frontend/dist/', import.meta.url)
const routes = new Set(['/', '/today', '/blind-box', '/plan', '/log', '/profile', '/pantry'])
const types = { html: 'text/html', css: 'text/css', js: 'text/javascript' }
const apiHits = []
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname
  if (path.startsWith('/api/')) apiHits.push(path)
  const asset = routes.has(path) ? 'index.html' : /^\/assets\/[\w.-]+$/.test(path) ? path.slice(1) : null
  try {
    if (request.method !== 'GET' || !asset) throw new Error('Missing route')
    const body = await readFile(new URL(asset, root))
    response.writeHead(200, { 'Content-Type': types[asset.split('.').at(-1)] })
    response.end(body)
  } catch {
    response.writeHead(404)
    response.end()
  }
})

async function until(check) {
  const deadline = Date.now() + 10000
  while (Date.now() < deadline) {
    try {
      const result = await check()
      if (result) return result
    } catch {}
    await new Promise(resolve => setTimeout(resolve, 50))
  }
  throw new Error('Timed out: ' + check)
}

async function browser(origin, run) {
  const profile = await mkdtemp('/tmp/mealmind-public-')
  const chrome = spawn(chromePath, ['--headless', '--remote-debugging-port=0', '--no-first-run',
    '--no-default-browser-check', '--user-data-dir=' + profile, 'about:blank'], { stdio: 'ignore' })
  let ws
  try {
    const port = await until(async () => (await readFile(profile + '/DevToolsActivePort', 'utf8')).split('\n')[0])
    const page = await until(async () => (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(item => item.type === 'page'))
    ws = new WebSocket(page.webSocketDebuggerUrl)
    await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
    const pending = new Map()
    let id = 0
    const outbound = []
    ws.onmessage = ({ data }) => {
      const event = JSON.parse(data)
      if (event.method === 'Network.requestWillBeSent') {
        const { url, method } = event.params.request
        if (/^https?:/.test(url) && (method !== 'GET' || url.startsWith(origin + '/api/') || !url.startsWith(origin))) outbound.push(url)
      }
      if (event.id) {
        pending.get(event.id)?.(event)
        pending.delete(event.id)
      }
    }
    const cdp = (method, params = {}) => new Promise((resolve, reject) => {
      pending.set(++id, response => response.error ? reject(new Error(response.error.message)) : resolve(response.result))
      ws.send(JSON.stringify({ id, method, params }))
    })
    const js = async expression => {
      const evaluated = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
      if (evaluated.exceptionDetails) throw new Error(evaluated.exceptionDetails.text)
      return evaluated.result.value
    }
    const visible = (phrase, selector = 'main') =>
      until(() => js(`document.querySelector(${JSON.stringify(selector)})?.innerText.includes(${JSON.stringify(phrase)})`))
    const click = async (label, selector = 'main') => {
      const button = `[...document.querySelectorAll(${JSON.stringify(selector + ' button')})].find(el=>el.textContent.trim()===${JSON.stringify(label)} && el.getClientRects().length && !el.matches(':disabled'))`
      await until(() => js(`!!(${button})`))
      await js(`(${button}).click()`)
    }
    await cdp('Network.enable')
    await run({ js, cdp, visible, click, outbound, open: path => cdp('Page.navigate', { url: origin + path }) })
  } finally {
    ws?.close()
    if (chrome.exitCode === null) {
      const exited = new Promise(resolve => chrome.once('exit', resolve))
      chrome.kill()
      await exited
    }
    await rm(profile, { recursive: true, force: true })
  }
}

try {
  const pool = JSON.parse(await readFile(new URL('../frontend/src/data/public-demo-meals.json', import.meta.url), 'utf8'))
  assert.equal(pool.recipes.length, 9)
  assert(pool.recipes.every(recipe => recipe.review.status === 'draft'))
  assert.equal(pool.contentReview.allergenEvidence, 'unverified')
  const bundle = (await Promise.all((await readdir(new URL('assets/', root)))
    .filter(name => name.endsWith('.js')).map(name => readFile(new URL('assets/' + name, root), 'utf8')))).join('\n')
  assert(!/AIza[\w-]{35}|family_000052|全麦卷饼皮/.test(bundle))
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const origin = 'http://127.0.0.1:' + server.address().port
  let previousPlan
  await browser(origin, async ({ js, cdp, visible, click, open, outbound }) => {
    const daily = 'section[aria-labelledby="public-plan-title"]'
    const currentSlots = () => js(`document.querySelector(${JSON.stringify(daily)}).querySelector('.meal-list').innerText`)
    const recipe = () => until(() => js("document.querySelector('.blind-meal h2')?.innerText"))
    const save = '#blind-box-save'
    const add = async () => {
      await click('加入计划', '.blind-meal')
      await click('检查餐次并保存', save)
      await click('确认加入计划', save)
      await visible('已保存到餐单。', save)
      await click('关闭', save)
    }
    async function setMobile(width, height) {
      await cdp('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: true })
      await js('window.scrollTo(0, 0)')
    }
    async function verifyBounds() {
      await until(() => js("document.querySelector('.blind-result').getAnimations().every(a=>a.playState==='finished')"))
      assert(await js(`document.documentElement.scrollWidth <= innerWidth &&
        document.querySelector('.blind-meal').getBoundingClientRect().bottom <= document.querySelector('.site-nav').getBoundingClientRect().top`))
    }
    await open('/today')
    await visible('今天吃什么？')
    await visible('暂无安排', daily)
    await setMobile(375, 667)
    await js('Math.random = () => 0')
    await click('开始抽取')
    const before = await recipe()
    await verifyBounds()
    await click('再抽一次')
    const dinner = await until(async () => { const name = await recipe(); return name !== before && name })
    await verifyBounds()
    assert(!(await currentSlots()).includes(dinner))
    await add()
    await visible(dinner, daily)

    await setMobile(390, 844)
    await js("document.querySelector('input[name=blind-box-slot]').click()")
    await click('开始抽取')
    const breakfast = await recipe()
    await verifyBounds()
    await add()
    await visible(breakfast, daily)
    assert((await currentSlots()).includes(dinner))

    await js("document.querySelectorAll('input[name=blind-box-slot]')[2].click()")
    await js(`Math.random = () => 0`)
    await click('开始抽取')
    const proposed = await recipe()
    await click('加入计划', '.blind-meal')
    await click('检查餐次并保存', save)
    await visible('当前餐食：' + dinner, save)
    await visible('拟保存餐食：' + proposed, save)
    assert((await currentSlots()).includes(dinner))
    await click('取消', save)
    await until(() => js("!document.querySelector('#blind-box-save').open"))
    assert((await currentSlots()).includes(dinner))
    await click('加入计划', '.blind-meal')
    await click('检查餐次并保存', save)
    await click('确认替换', save)
    await visible('已保存到餐单。', save)
    await open('/today')
    await visible(proposed, daily)
    assert((await currentSlots()).includes(breakfast))
    assert.equal(await js("document.querySelectorAll('#public-plan-title').length"), 1)
    await visible('历史版本', daily)

    await open('/plan')
    await visible('公开演示使用固定示例')
    assert(await js("!document.querySelector('textarea[name=requirements], option[value=catalog], option[value=prompt_only]')"))
    await click('查看示例餐单')
    await click('查看替换内容')
    await visible('请确认要替换的餐次')
    await visible('当前餐食：' + proposed)
    await visible('拟保存餐食：番茄土豆鹰嘴豆炖菜')
    await click('确认替换')
    await open('/today')
    await visible('番茄土豆鹰嘴豆炖菜', daily)


    const consumed = 'section[aria-labelledby="today-consumed-title"]'
    const nutrition = 'section[aria-labelledby="nutrition-title"]'
    const records = 'section[aria-labelledby="food-log-list"]'
    await visible('今天还没有已确认的食物记录。', consumed)
    await visible('当天还没有已确认的食物记录。', nutrition)
    const savedSlots = await currentSlots()
    const fill = (selector, value) => js(`(() => {
      const field = document.querySelector(${JSON.stringify(selector)});
      Object.getOwnPropertyDescriptor(Object.getPrototypeOf(field), 'value').set.call(field, ${JSON.stringify(value)});
      field.dispatchEvent(new Event('input', { bubbles: true }));
      field.dispatchEvent(new Event('change', { bubbles: true }));
    })()`)
    await open('/log')
    await visible('食物记录仅保存在当前浏览器')
    assert(await js("!document.querySelector('input[type=file]') && !document.querySelector('#food-recognition-help')"))
    await setMobile(375,667)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))
    await click('保存草稿')
    await visible('至少需要一项食物')
    await fill('form textarea','测试实际食用说明')
    await fill('form select','dinner')
    await fill('form input[required][maxlength]','熟长粒糙米')
    await fill('form input[type=number]','150')
    await fill('form input[maxlength="120"]:not([required])','g')
    await click('添加食物')
    await fill('form fieldset fieldset:last-of-type input[required]','牛肉面')
    await js("const save = document.querySelector('form [type=submit]'); save.click(); save.click()")
    await visible('牛肉面', records)
    await visible('熟长粒糙米 · 150 g', records)
    await visible('数量未知', records)
    assert.equal(await js(`document.querySelectorAll(${JSON.stringify(records+' article')}).length`),1)
    await open('/today')
    await visible('今天还没有已确认的食物记录。', consumed)
    await visible('当天还没有已确认的食物记录。', nutrition)
    assert.equal(await currentSlots(),savedSlots)
    await open('/log')
    await visible('熟长粒糙米',records)
    await click('确认实际吃过',records)
    await visible('食物记录已确认。',records)
    await cdp('Page.reload')
    await visible('测试实际食用说明',records)
    await visible('已确认',records)
    await setMobile(390,844)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))

    await open('/today')
    await visible('熟长粒糙米',consumed)
    await visible('已计算小计 · 仅覆盖部分记录', nutrition)
    await visible('已计算 1/2 项食物', nutrition)
    await visible('184.5 千卡', nutrition)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))
    await js(`document.querySelector(${JSON.stringify(nutrition + ' ul details summary')}).click()`)
    await visible('目录中没有匹配这道混合菜的参考数据', nutrition)
    await visible('没有记录实际吃了多少', nutrition)
    assert.equal(await currentSlots(),savedSlots)
    await until(() => js("document.querySelectorAll('input[name=blind-box-slot]').length === 3"))
    await js("document.querySelectorAll('input[name=blind-box-slot]')[2].click()")
    await click('开始抽取')
    await recipe()
    await click('加入计划','.blind-meal')
    await click('检查餐次并保存',save)
    await visible('这餐已有确认的食用记录',save)
    assert.equal(await currentSlots(),savedSlots)
    await click('关闭',save)

    await open('/log')
    await visible('熟长粒糙米',records)
    await click('更正记录',records)
    await fill('form input[required][maxlength]','熟长粒糙米')
    await fill('form input[type=number]','200')
    await click('保存更正')
    await visible('已更新确认食用记录。',records)
    await visible('熟长粒糙米 · 200 g',records)
    await open('/today')
    await visible('熟长粒糙米 200 g',consumed)
    await visible('246 千卡', nutrition)
    await cdp('Page.reload')
    await visible('246 千卡', nutrition)
    assert.equal(await currentSlots(),savedSlots)
    await open('/log')
    await visible('熟长粒糙米',records)
    await js('window.confirm = () => false')
    await click('删除记录',records)
    await visible('熟长粒糙米',records)
    await js('window.confirm = () => true')
    await click('删除记录',records)
    await visible('这一天没有食物记录。',records)
    await open('/today')
    await visible('今天还没有已确认的食物记录。',consumed)
    await visible('当天还没有已确认的食物记录。', nutrition)
    assert.equal(await currentSlots(),savedSlots)

    const replan = 'section[aria-labelledby="public-replan-title"]'
    const planData = () => readStore('plans')
    const logData = () => readStore('food-logs')
    function readStore(store, mutation = '') {
      return js(`new Promise((resolve, reject) => {
        const open = indexedDB.open('mealmind-meal-plans');
        open.onerror = reject;
        open.onsuccess = () => {
          const db = open.result;
          const tx = db.transaction(${JSON.stringify(store)}, ${JSON.stringify(mutation ? 'readwrite' : 'readonly')});
          const store = tx.objectStore(${JSON.stringify(store)});
          const get = store.getAll();
          get.onsuccess = () => { const rows = get.result; ${mutation} };
          tx.onabort = reject;
          tx.oncomplete = () => { db.close(); resolve(get.result); };
        };
      })`)
    }
    const optionValues = () => js(`[...document.querySelectorAll(${JSON.stringify(replan + ' form select:first-of-type option')})].map(el=>el.value).filter(Boolean).slice(0,3)`)
    await setMobile(375,667)
    await visible('管理餐次锁定', replan)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))
    const beforeLocks = (await planData())[0]
    await js(`document.querySelector(${JSON.stringify(replan + ' details summary')}).click()`)
    await js(`[...document.querySelectorAll(${JSON.stringify(replan + ' details label')})].find(el=>el.textContent.includes('保留午餐')).querySelector('input').click()`)
    await click('保存餐次锁定', replan)
    await visible('你锁定的餐次：午餐', replan)
    const lockedPlan = (await planData())[0]
    assert.deepEqual(lockedPlan.lockedMealTypes, ['lunch'])
    assert.deepEqual(lockedPlan.revisions, beforeLocks.revisions)
    assert(!((await optionValues()).includes('lunch')))

    // These real local records leave dinner as the sole eligible main meal.
    for (const [slot, food, quantity] of [['breakfast','熟长粒糙米','100'],['lunch','测试会话隔离餐食',null]]) {
      await open('/log')
      await visible('食物记录仅保存在当前浏览器')
      await fill('form select',slot)
      await fill('form input[required][maxlength]',food)
      if (quantity) {
        await fill('form input[type=number]',quantity)
        await fill('form input[maxlength="120"]:not([required])','g')
      }
      await click('保存草稿')
      await visible(food,records)
      await click('确认实际吃过',records)
      await visible('食物记录已确认。',records)
    }
    await open('/today')
    await setMobile(390,844)
    await visible('已确认食用：早餐 · 午餐',replan)
    assert.deepEqual(await js(`[...document.querySelector(${JSON.stringify(replan + ' form select')}).options].map(x=>x.value).filter(Boolean)`),['dinner'])
    await visible('已计算小计 · 仅覆盖部分记录',nutrition)
    await visible('123 千卡',nutrition)
    assert(await js('document.documentElement.scrollWidth <= innerWidth'))

    const choose = async (restriction = 'none_declared') => {
      await until(() => js(`!!document.querySelector(${JSON.stringify(replan + ' form select')})`))
      await fill(replan + ' form select','dinner')
      await fill(replan + ' form label:nth-of-type(2) select',restriction)
    }
    const check = (name) => js(`document.querySelector(${JSON.stringify(replan + ' input[name=' + name + ']')}).click()`)
    const previewNoodles = async () => {
      await choose()
      await check('noodles')
      await click('生成预览',replan)
      await visible('拟保存餐食：豆腐香菇青菜汤面',replan)
    }
    const baselineLogs = await logData()
    await choose('present')
    await visible('本预览无法核实关键饮食限制',replan)
    assert(await js(`document.querySelector(${JSON.stringify(replan + ' form button[type=submit]')}).disabled`))
    await choose()
    await check('noodles')
    await check('quick')
    await click('生成预览',replan)
    await visible('目前没有符合这些要求的餐食',replan)
    await check('quick')
    await check('avoidRepeat')
    await click('生成预览',replan)
    // The current lunch is this noodle dish. Avoiding earlier dishes removes it.
    await visible('拟保存餐食：鸡肉卷心菜炒乌冬',replan)
    await visible('其他已规划餐次保持不变：早餐 · 午餐',replan)
    await click('保留当前餐单',replan)
    assert.deepEqual(await planData(),[lockedPlan])
    assert.deepEqual(await logData(),baselineLogs)

    await click('生成预览',replan)
    await visible('拟保存餐食：鸡肉卷心菜炒乌冬',replan)
    await readStore('food-logs',"store.put({...rows[0], revision: rows[0].revision + 1});")
    await click('接受并保存这一餐',replan)
    await visible('已确认记录、日期或餐单已有变化',replan)
    assert.deepEqual(await planData(),[lockedPlan])

    await choose()
    assert(await js(`!document.querySelector(${JSON.stringify(replan + ' input[name=noodles]')}).checked`))
    await previewNoodles()
    await readStore('plans',`const plan = rows[0]; const last = plan.revisions.at(-1);
      store.put({...plan, revision: plan.revision + 1, revisions: [...plan.revisions,
        {...last, revision: plan.revision + 1, acceptanceId: crypto.randomUUID()}]});`)
    const afterConcurrentPlan = (await planData())[0]
    await click('接受并保存这一餐',replan)
    await visible('已确认记录、日期或餐单已有变化',replan)
    assert.deepEqual(await planData(),[afterConcurrentPlan])

    await previewNoodles()
    const beforeAcceptLogs = await logData()
    await click('接受并保存这一餐',replan)
    await visible('已保存为当前餐单',replan)
    const afterAccept = (await planData())[0]
    assert.equal(afterAccept.revision, afterConcurrentPlan.revision + 1)
    assert.deepEqual(afterAccept.revisions.slice(0,-1), afterConcurrentPlan.revisions)
    assert.deepEqual(afterAccept.lockedMealTypes,['lunch'])
    assert.deepEqual(afterAccept.revisions.at(-1).plan.meals.slice(0,2),afterConcurrentPlan.revisions.at(-1).plan.meals.slice(0,2))
    assert.deepEqual(await logData(),beforeAcceptLogs)
    await cdp('Page.reload')
    await visible('你锁定的餐次：午餐',replan)
    await visible('豆腐香菇青菜汤面',daily)
    assert.deepEqual(await planData(),[afterAccept])
    console.log('PASS production Replan: confirmed and user locks, preferences, no alternatives, cancel, stale logs/plan, accept and reload')
    console.log('PASS production Food Log: draft, duplicate suppression, unknown amount, confirm/reload, edit, cancel/delete, Today and locked slots')
    for (const path of ['/log', '/profile', '/blind-box', '/pantry']) {
      await open(path)
      await until(() => js(`location.pathname === '${path === '/pantry' ? '/today' : path}' && !!document.querySelector('main h1')`))
      if (path === '/log') assert(await js("!!document.querySelector('main form')"))
    }
    previousPlan = await js(`new Promise((resolve, reject) => {
      const open = indexedDB.open('mealmind-meal-plans');
      open.onerror = reject;
      open.onsuccess = () => {
        const db = open.result;
        const get = db.transaction('plans').objectStore('plans').getAll();
        get.onerror = reject;
        get.onsuccess = () => { db.close(); resolve(get.result[0]); };
      };
    })`)
    assert(previousPlan.revisions.length > 1)
    delete previousPlan.lockedMealTypes
    delete previousPlan.lockRevision
    assert.deepEqual(outbound, [])
    assert.deepEqual(apiHits, [])
  })
  await browser(origin, async ({ open, js, visible }) => {
    await open('/today')
    await visible('暂无安排', 'section[aria-labelledby="public-plan-title"]')
    await visible('今天吃什么？')
    assert.equal(await js("document.querySelectorAll('[aria-labelledby=public-plan-title] .meal-list li').length"), 3)
    await js("document.querySelector('.blind-restrictions summary').click(); document.querySelector('.blind-restrictions input').click()")
    await js("document.querySelector('.blind-stage > button').click()")
    await visible('暂无可推荐餐食')
    assert(await js("!document.querySelector('.blind-meal')"))
    await visible('今天还没有已确认的食物记录。', 'section[aria-labelledby="today-consumed-title"]')
    await visible('当天还没有已确认的食物记录。', 'section[aria-labelledby="nutrition-title"]')
    await visible('该日期还没有保存的餐单', 'section[aria-labelledby="public-replan-title"]')
    await open('/log')
    await visible('这一天没有食物记录。')
  })
  await browser(origin, async ({ open, js, visible, click, cdp, outbound }) => {
    await open('/')
    await until(() => js("!!document.querySelector('main')"))
    assert(await js(`new Promise((resolve, reject) => {
      const request = indexedDB.open('mealmind-meal-plans', 1);
      request.onerror = reject;
      request.onupgradeneeded = () => {
        request.result.createObjectStore('plans', { keyPath: 'date' }).add(${JSON.stringify(previousPlan)});
      };
      request.onsuccess = () => { request.result.close(); resolve(true); };
    })`))
    await open('/today')
    await visible('豆腐香菇青菜汤面', 'section[aria-labelledby="public-plan-title"]')
    await visible('历史版本', 'section[aria-labelledby="public-plan-title"]')
    assert.deepEqual(await js(`new Promise((resolve, reject) => {
      const request = indexedDB.open('mealmind-meal-plans', 2);
      request.onerror = reject;
      request.onsuccess = () => {
        const db = request.result;
        const get = db.transaction('plans').objectStore('plans').get(${JSON.stringify(previousPlan.date)});
        get.onerror = reject;
        get.onsuccess = () => { db.close(); resolve(get.result); };
      };
    })`), previousPlan)
    await cdp('Emulation.setTimezoneOverride', { timezoneId: 'Asia/Singapore' })
    await open('/log')
    await visible('这一天没有食物记录。')
    await js(`for (const [selector, value] of [['input[type=datetime-local]', '2001-10-10T00:05'], ['input[required][maxlength]', '熟长粒糙米'], ['input[type=number]', '100'], ['input[maxlength="120"]:not([required])','g']]) {
      const field = document.querySelector(selector);
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(field, value);
      field.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const mealType = document.querySelector('form select');
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set.call(mealType, 'breakfast');
    mealType.dispatchEvent(new Event('change', { bubbles: true }));`)
    await click('保存草稿')
    await visible('熟长粒糙米 · 100 g')
    assert.equal(await js("document.querySelector('section[aria-labelledby=food-log-list] input[type=date]').value"),'2001-10-10')
    assert.match(await js("document.querySelector('section[aria-labelledby=food-log-list] time').dateTime"), /2001-10-10T00:05:00\+08:00/)
    await click('确认实际吃过')
    await visible('食物记录已确认。')
    await open('/today')
    const nutrition = 'section[aria-labelledby="nutrition-title"]'
    await visible('当天还没有已确认的食物记录。', nutrition)
    await js(`(() => {
      const field = document.querySelector(${JSON.stringify(nutrition + ' input[type=date]')});
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'2001-10-10');
      field.dispatchEvent(new Event('input',{ bubbles:true }));
      field.dispatchEvent(new Event('change',{ bubbles:true }));
    })()`)
    await visible('123 千卡', nutrition)
    await visible('已计算 1/1 项食物', nutrition)
    const replan = 'section[aria-labelledby="public-replan-title"]'
    await visible('已确认食用：无',replan)
    await js(`(() => {
      const field = document.querySelector(${JSON.stringify(replan + ' input[type=date]')});
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(field,'2001-10-10');
      field.dispatchEvent(new Event('input',{ bubbles:true }));
      field.dispatchEvent(new Event('change',{ bubbles:true }));
    })()`)
    await visible('已确认食用：早餐',replan)
    assert(await js(`!document.querySelector(${JSON.stringify(replan + ' option[value=breakfast]')})`))
    await open('/log')
    await visible('这一天没有食物记录。')
    await click('English', 'header')
    await visible('Food records stay in this browser.')
    assert.deepEqual(outbound, [])
    console.log('PASS additive IndexedDB upgrade, historical plan equality, local date near midnight, complete nutrition and English')
  })
  const privatePaths = ['/api', '/api/', '/api/v1/health', '/api/v1/food-logs', '/api/v1/nutrition/daily',
    '/api/v1/replan/context', '/api/v1/meal-plans/generate']
  for (const path of privatePaths) {
    assert.equal((await fetch(origin + path)).status, 404, path)
  }
  assert.equal((await fetch(origin + '/api/v1/meal-plans/generate', { method: 'POST' })).status, 404)
  console.log('PASS production demo: local draw/redraw, mobile bounds, add/replace/cancel, history, refresh, session isolation, restriction gating, no frontend API calls, private paths 404')
} finally {
  await new Promise(resolve => server.close(resolve))
}
