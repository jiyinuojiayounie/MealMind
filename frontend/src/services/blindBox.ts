import catalog from '../../../data/recipe_catalog/catalog-v4.json'
import publicPool from '../data/public-demo-meals.json'
import batch02 from '../data/blind-box-batch-02.json'
import type { MealPlan, MealPlanRequest, MealType } from './mealPlans'

export type BlindBoxMeal = Exclude<MealType, 'snack'>
type Language = MealPlanRequest['language']

const demoRecipes = import.meta.env.DEV ? [...publicPool.recipes, ...batch02.recipes] : publicPool.recipes

const ingredientNames = new Map(
  (import.meta.env.DEV ? [...catalog.ingredients, ...batch02.ingredients] : publicPool.ingredients)
    .map((ingredient) => [ingredient.ingredient_id, ingredient.names]),
)

const cookedNames = new Map<string, Record<Language, string>>([
  ['ingredient_rice', { 'zh-CN': '熟米饭', 'en-US': 'Cooked rice' }],
  ['ingredient_chicken', { 'zh-CN': '熟鸡腿肉', 'en-US': 'Cooked chicken thigh' }],
])

function demoMealCandidates(mealType: BlindBoxMeal) {
  return demoRecipes.filter((recipe) =>
    recipe.review.status === 'draft' && recipe.servings === 1 && recipe.meal_types.includes(mealType),
  )
}

export function drawDemoMeal(mealType: BlindBoxMeal, hasRestriction: boolean, previousId?: string) {
  // Eligibility for users with explicit restrictions still requires reviewed evidence.
  if (hasRestriction) return undefined
  const eligible = demoMealCandidates(mealType)
  const alternatives = eligible.filter((recipe) => recipe.recipe_id !== previousId)
  const pool = alternatives.length ? alternatives : eligible
  return pool[Math.floor(Math.random() * pool.length)]
}

export function demoMealPlan(
  recipe: NonNullable<ReturnType<typeof drawDemoMeal>>, mealType: BlindBoxMeal,
  language: Language, servingLabel: string,
): MealPlan {
  const title = recipe.names[language]
  const assumptions = recipe.times.starting_assumptions?.[language]
  const shrimpNote = recipe.recipe_id === 'recipe_000017'
    ? (language === 'zh-CN'
      ? '开始计时前，备好妥善保存的熟米饭，以及已安全解冻、去壳并去虾线的虾仁。'
      : 'Before starting the timer, have safely stored cooked rice and safely thawed, peeled and deveined shrimp ready.')
    : undefined
  const steps = recipe.recipe_id === 'recipe_000023'
    ? (language === 'zh-CN' ? [
      '选无需预泡的快煮细米粉，先看包装所需的煮制时间。烧水时洗切小白菜，梗、叶分开。',
      '水开后打入鸡蛋，转小火保持微沸，煮至蛋白和蛋黄全熟。',
      '加菜梗和米粉，按包装时间煮至米粉熟软，最后加入菜叶煮软，加盐盛出。',
    ] : [
      'Choose quick rice vermicelli that needs no presoak and check the package cooking time. Wash and chop the bok choy while heating water, separating stems and leaves.',
      'Crack the egg into the boiling water, reduce to a gentle simmer and cook until the white and yolk are fully set.',
      'Add the stems and noodles. Cook the noodles according to the package, then add the leaves and cook until tender. Season and serve.',
    ])
    : recipe.steps[language]
  const assumption = shrimpNote ?? assumptions
  // Allow additional handling and cleanup time for raw chicken; pending a cook-through.
  const minutes = recipe.recipe_id === 'recipe_000025' ? 24 : recipe.times.total_minutes
  return {
    title,
    explanation: servingLabel,
    additional_ingredients: [],
    meals: [{
      meal_type: mealType,
      estimated_preparation_minutes: minutes,
      dishes: [{
        name: title,
        ingredients: recipe.ingredients.map((ingredient) => ({
          name: ((ingredient.state === 'cooked' && cookedNames.get(ingredient.ingredient_id)) || ingredientNames.get(ingredient.ingredient_id))
            ?.[language] ?? ingredient.ingredient_id,
          quantity: ingredient.quantity,
          unit: ingredient.unit,
        })),
        instructions: [...(assumption ? [assumption] : []), ...steps],
      }],
    }],
  }
}

export function publicPlanningExample(language: Language, title: string, explanation: string, serving: string): MealPlan {
  const slots = [['breakfast', 'recipe_000021'], ['lunch', 'recipe_000018'], ['dinner', 'recipe_000026']] as const
  return {
    title, explanation, additional_ingredients: [],
    meals: slots.map(([slot, id]) => {
      const recipe = publicPool.recipes.find((candidate) => candidate.recipe_id === id)
      if (!recipe) throw new Error('Missing public example recipe')
      return demoMealPlan(recipe, slot, language, serving).meals[0]
    }),
  }
}
