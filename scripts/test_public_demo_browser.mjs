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
      const evaluated = await cdp('Runtime.evaluate', { expression, returnByValue: true })
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

    for (const path of ['/log', '/profile', '/blind-box', '/pantry']) {
      await open(path)
      await until(() => js(`location.pathname === '${path === '/pantry' ? '/today' : path}' && !!document.querySelector('main h1')`))
      if (path === '/log') assert(await js("!document.querySelector('main form')"))
    }
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
