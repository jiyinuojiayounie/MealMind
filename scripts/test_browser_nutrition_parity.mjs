// Run at repository root. Uses the Python fixture interpreter and the browser's TS module.
import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { createServer } from '../frontend/node_modules/vite/dist/node/index.js'

const report = JSON.parse(execFileSync('.venv/bin/python', ['-m', 'scripts.browser_nutrition_parity_cases'], {
  cwd: 'backend', encoding: 'utf8',
}))
assert.deepEqual(JSON.parse(readFileSync('data/nutrition/browser-rules-v1.json', 'utf8')), report.rules)
const server = await createServer({ root: 'frontend', configFile: false, server: { middlewareMode: true, ws: false } })

function decimal(actual, expected) {
  if (expected === null || Number(expected) === 0) assert.equal(actual === null ? null : Number(actual), expected === null ? null : 0)
  else {
    assert.notEqual(actual, null)
    assert(Math.abs(Number(actual) - Number(expected)) <= Math.abs(Number(expected)) * 1e-12)
  }
}

try {
  const { createLocalNutritionCalculator, summarizeLocalNutrition } = await server.ssrLoadModule('/src/services/localNutrition.ts')
  for (const [groupIndex, group] of report.groups.entries()) {
    const fixture = groupIndex === 1 ? {
      ...report.synthetic,
      foods: report.synthetic.foods.map((food) => ({
        ...food, nutrients: Object.fromEntries(Object.entries(food.nutrients).map(([key, value]) =>
          [key, value === null ? null : { ...value, amount: Number(value.amount) }])),
      })),
    } : undefined
    const calculator = createLocalNutritionCalculator(fixture)
    const actual = group.inputs.map((food, index) => calculator.calculateItem(food, index))
    for (const [index, row] of actual.entries()) {
      const expected = group.results[index]
      assert.deepEqual(row.reasons, expected.reasons, group.inputs[index].name)
      assert.equal(row.conversion, expected.conversion)
      assert.equal(row.provenance?.fdc_id, expected.provenance?.fdc_id)
      assert.equal(row.provenance?.state, expected.provenance?.state)
      assert.equal(row.provenance?.food_id, expected.provenance?.food_id)
      assert.equal(row.provenance?.portion_source_row_id ?? null, expected.provenance?.portion_source_row_id ?? null)
      assert.deepEqual(row.provenance?.nutrient_source_row_ids, expected.provenance?.nutrient_source_row_ids)
      for (const [key, value] of Object.entries(row.nutrients)) decimal(value, expected.nutrients[key])
    }
    const aggregate = summarizeLocalNutrition(actual)
    for (const [key, expected] of Object.entries(group.aggregate.nutrients)) {
      const row = aggregate.nutrients[key]
      assert.equal(row.contributing_items, expected.contributing_items)
      assert.equal(row.missing_items, expected.missing_items)
      decimal(row.subtotal, expected.subtotal)
    }
    for (const key of ['item_count', 'calculated_item_count', 'fully_calculated_item_count', 'uncalculated_item_count']) {
      assert.equal(aggregate[key], group.aggregate[key])
    }
  }
  console.log('PASS browser/Python nutrition parity:', report.groups.reduce((sum, group) => sum + group.inputs.length, 0), 'items, 2 aggregates and generated vocabulary')
} finally {
  await server.close()
}
