# Recipe review batch 01

Product-owner review packet for schema version 1, catalog version 1. Each recipe is revision 1. The source is the [development catalog](../data/recipe_catalog/catalog-v1.json). Apply the [meal planning quality rules](MEAL_PLANNING_QUALITY.md) and [catalog review policy](RECIPE_CATALOG_DESIGN.md) when recording a decision.

## Evidence and coverage

The catalog loader accepted all 20 recipes and 29 canonical ingredients and returned zero production candidates. All recipe IDs and family IDs are distinct in this snapshot. All ingredient references resolve, all records specify one serving, and all total times cover their recorded phases. Recorded totals range from 7 to 31 minutes. These are mechanical findings. The roles, yields, quantities, elapsed times, and cooking steps remain unverified estimates. No independent cook-through, nutritional review, allergen verification, or reuse clearance was performed.

The drafts cover Chinese home cooking with six breakfast, 18 lunch, 18 dinner, and four snack records. Tags overlap. Nine have a protein role, eight a staple role, 11 a vegetable role, and three an accompaniment role. Three combination dishes carry all three complete-meal roles. Seven cooking methods are represented, with six simmering and six stir-frying records. Sauce and water amounts are listed as stored. A listed amount may serve a cooking process and may not represent what is eaten.

## Inventory

Time is shown as preparation / cooking / total in minutes. Primary ingredients come from the stored primary flags. A lunch or dinner tag means the dish can appear at that meal. Check its roles separately before treating it as a complete meal.

| Recipe and Chinese name | Family ID | Meal categories | Dish roles | Primary ingredients | Prep / cook / total | Review |
| --- | --- | --- | --- | --- | --- | --- |
| `recipe_000001` 小米南瓜粥 | `family_000001` | breakfast, snack | staple | 小米, 南瓜 | 6 / 25 / 31 | draft |
| `recipe_000002` 葱花蒸蛋 | `family_000002` | breakfast, lunch, dinner | protein | 鸡蛋 | 5 / 12 / 17 | draft |
| `recipe_000003` 玉米燕麦粥 | `family_000003` | breakfast, snack | staple | 燕麦片, 玉米粒 | 4 / 10 / 14 | draft |
| `recipe_000004` 蒸红薯 | `family_000004` | breakfast, lunch, dinner, snack | staple | 红薯 | 5 / 20 / 25 | draft |
| `recipe_000005` 姜丝蒸鱼 | `family_000005` | lunch, dinner | protein | 白肉鱼片 | 6 / 12 / 18 | draft |
| `recipe_000006` 香菇焖鸡 | `family_000006` | lunch, dinner | protein, vegetable | 鸡腿肉, 鲜香菇 | 8 / 18 / 26 | draft |
| `recipe_000007` 葱香肉片 | `family_000007` | lunch, dinner | protein | 猪里脊 | 7 / 9 / 16 | draft |
| `recipe_000008` 番茄炒蛋 | `family_000008` | breakfast, lunch, dinner | protein, vegetable | 鸡蛋, 番茄 | 6 / 9 / 15 | draft |
| `recipe_000009` 葱香煎豆腐 | `family_000009` | lunch, dinner | protein | 北豆腐 | 6 / 11 / 17 | draft |
| `recipe_000010` 蒜蓉小白菜 | `family_000010` | lunch, dinner | vegetable | 小白菜 | 5 / 6 / 11 | draft |
| `recipe_000011` 醋炒卷心菜 | `family_000011` | lunch, dinner | vegetable | 卷心菜 | 5 / 7 / 12 | draft |
| `recipe_000012` 蒸西兰花胡萝卜 | `family_000012` | lunch, dinner | vegetable | 西兰花, 胡萝卜 | 7 / 8 / 15 | draft |
| `recipe_000013` 醋拌黄瓜 | `family_000013` | lunch, dinner, snack | vegetable, accompaniment | 黄瓜 | 7 / 0 / 7 | draft |
| `recipe_000014` 胡萝卜米饭 | `family_000014` | lunch, dinner | staple | 大米 | 6 / 21 / 27 | draft |
| `recipe_000015` 葱油拌面 | `family_000015` | breakfast, lunch, dinner | staple | 小麦面条 | 6 / 12 / 18 | draft |
| `recipe_000016` 鸡蛋小白菜炒饭 | `family_000016` | lunch, dinner | protein, staple, vegetable | 大米, 鸡蛋, 小白菜 | 6 / 10 / 16 | draft |
| `recipe_000017` 虾仁西兰花盖饭 | `family_000017` | lunch, dinner | protein, staple, vegetable | 大米, 虾仁, 西兰花 | 8 / 12 / 20 | draft |
| `recipe_000018` 豆腐香菇青菜汤面 | `family_000018` | lunch, dinner | protein, staple, vegetable | 小麦面条, 北豆腐, 小白菜 | 8 / 13 / 21 | draft |
| `recipe_000019` 冬瓜姜汤 | `family_000019` | lunch, dinner | vegetable, accompaniment | 冬瓜 | 7 / 15 / 22 | draft |
| `recipe_000020` 胡萝卜玉米清汤 | `family_000020` | lunch, dinner | vegetable, accompaniment | 胡萝卜, 玉米粒 | 6 / 15 / 21 | draft |

## Audit across the batch

| Area | Finding and review priority |
| --- | --- |
| Yield and quantities | Check the finished yield of the porridges and soups, combined solid and broth yield in the noodle soup, and snack suitability of the single-serving records. Separate consumed liquid from water used for steaming, boiling, or rinsing. The current data cannot always express that distinction. |
| Complete meals | Only recipes 000016–000018 carry protein, staple, and vegetable roles. Treat these as candidates pending review of finished portions. The other lunch and dinner tags indicate eligible dish placement. A plain staple, protein side, vegetable dish, or broth cannot fulfill all three roles on its own. |
| Times and starting state | Arithmetic is valid. The rice combinations explicitly start with cooked rice. Review boil-up, preheating, resting, thawing, and reheating assumptions. Verify 20-minute boundaries with a single burner before qualifying a recipe for a hard limit. |
| Family and repetition | Unique IDs do not prove culinary diversity. Review 000001/000003 for the breakfast porridge slot, 000019/000020 for the quick vegetable soup slot, and 000016/000017 for repeated cooked-rice meals. These are similarity candidates, with different primary ingredients or methods in each pair. Egg, bok choy, and rice each appear as a primary ingredient in three drafts. |
| Instructions and inventory | Review the missing steamer water in 000002, the distinction between rinse and cook water in 000014, and the implied use of oil in 000017. For non-selected rows, check cold-mix yield in 000013 and whether the noodle and scallion cooking phases in 000015 fit the estimate. |
| Claims and evidence | The catalog has no nutrition values, no populated dietary or allergen assessments, and no household conversions. Empty fields mean unknown. Review ingredient identity, packaged sauces and other compound products, and cross-contact separately before any allergy-related use. |
| Household units | Keep standard units until there is a reviewed basis for a conversion. Prioritize rice and noodle dry portions, tofu package fractions, small seasoning quantities, and egg size. Record the package or utensil basis and whether the measure applies to raw, cooked, or drained ingredients. |

## Selected recipe reviews

The 12 selections cover breakfast, protein dishes, vegetables, staples, soups, and all three draft combination meals. Ingredient quantities and instructions below reproduce the catalog. Risks and corrections are desk-review proposals.

### recipe_000001 小米南瓜粥

**Millet and pumpkin porridge** · `family_000001` · 1 serving

- **Classification** — breakfast, snack. Roles staple. Methods simmer.
- **Recorded time** — 6 min prep, 25 min cooking, 0 min modeled wait, 31 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 小米 / Millet | 40 g | dry |
| 南瓜 / Pumpkin | 80 g | raw |
| 水 / Water | 450 ml | ready_to_use |

**Catalog instructions, Chinese** — 冲洗小米，将南瓜切小块。加水煮沸后小火煮至小米和南瓜软烂。

**Catalog instructions, English** — Rinse the millet and dice the pumpkin. Bring the water to a boil and simmer both until soft.

**Potential issue** — 450 mL of water for 40 g of dry millet can give a large or thin serving. The same yield is tagged for breakfast and snack. The instruction does not specify when timing starts.

**Proposed correction** — Trial the current ratio and weigh the finished yield. Decide whether the snack needs a separate serving scale. Record water-to-boil time, the covered or uncovered simmer, and the target texture. Keep staple as the only role.

### recipe_000002 葱花蒸蛋

**Steamed eggs with scallion** · `family_000002` · 1 serving

- **Classification** — breakfast, lunch, dinner. Roles protein. Methods steam.
- **Recorded time** — 5 min prep, 12 min cooking, 0 min modeled wait, 17 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 鸡蛋 / Egg | 2 piece | raw |
| 水 / Water | 120 ml | ready_to_use |
| 葱 / Scallion | 5 g | raw |
| 盐 / Salt | 1 g | ready_to_use |

**Catalog instructions, Chinese** — 将鸡蛋、水和盐打匀后倒入浅碗，隔水蒸至蛋液凝固。撒上切碎的葱。

**Catalog instructions, English** — Whisk the eggs, water, and salt in a shallow bowl. Steam until set and top with chopped scallion.

**Potential issue** — The 120 mL water is mixed into the eggs. Water for the steamer is absent from the ingredient list. Egg size, dish depth, and preheating may change the result.

**Proposed correction** — Record steaming water separately from the consumed mixture and confirm how to represent the same ingredient used for two purposes. Trial the ratio with a stated egg size and shallow dish. Document when steaming starts and what setting looks like.

### recipe_000004 蒸红薯

**Steamed sweet potato** · `family_000004` · 1 serving

- **Classification** — breakfast, lunch, dinner, snack. Roles staple. Methods steam.
- **Recorded time** — 5 min prep, 20 min cooking, 0 min modeled wait, 25 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 红薯 / Sweet potato | 220 g | raw |
| 水 / Water | 500 ml | ready_to_use |

**Catalog instructions, Chinese** — 将红薯洗净切厚块，用水隔蒸至筷子可轻松穿透。

**Catalog instructions, English** — Wash and cut the sweet potato into thick pieces. Steam over the water until tender.

**Potential issue** — The 220 g amount does not say whether it is an edible or purchase weight. A full serving may differ from a snack. Starting with cold water could extend the recorded time.

**Proposed correction** — Specify skin and weighing convention, cut thickness, and steamer setup. Measure yield and time from cold water. Confirm the snack serving separately. Keep 500 mL as process water in the trial.

### recipe_000005 姜丝蒸鱼

**Steamed fish with ginger** · `family_000005` · 1 serving

- **Classification** — lunch, dinner. Roles protein. Methods steam.
- **Recorded time** — 6 min prep, 12 min cooking, 0 min modeled wait, 18 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 白肉鱼片 / White fish fillet | 140 g | raw |
| 姜 / Ginger | 8 g | raw |
| 水 / Water | 500 ml | ready_to_use |
| 酱油 / Soy sauce | 6 ml | ready_to_use |

**Catalog instructions, Chinese** — 将鱼片放入浅盘，铺上姜丝，隔水蒸至熟透。淋上酱油。

**Catalog instructions, English** — Lay sliced ginger on the fish in a shallow plate. Steam over the water until cooked through and add the soy sauce.

**Potential issue** — A generic fish fillet obscures species, thickness, and thawed or frozen state. The 500 mL water is for steaming. The word “cooked” provides little guidance for testing the estimate.

**Proposed correction** — Trial with a named, thawed fillet and recorded thickness. Mark the water as process water, include setup in elapsed time, and have a reviewer supply appropriate doneness guidance. Verify fish and the particular soy sauce label before any allergen-sensitive use.

### recipe_000006 香菇焖鸡

**Braised chicken and shiitake** · `family_000006` · 1 serving

- **Classification** — lunch, dinner. Roles protein, vegetable. Methods braise.
- **Recorded time** — 8 min prep, 18 min cooking, 0 min modeled wait, 26 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 鸡腿肉 / Chicken thigh | 150 g | raw |
| 鲜香菇 / Fresh shiitake | 90 g | raw |
| 姜 / Ginger | 5 g | raw |
| 水 / Water | 100 ml | ready_to_use |
| 酱油 / Soy sauce | 8 ml | ready_to_use |
| 食用油 / Cooking oil | 5 ml | ready_to_use |

**Catalog instructions, Chinese** — 将鸡肉和香菇切块。用油炒香姜和鸡肉，再加香菇、水和酱油焖至鸡肉熟透。

**Catalog instructions, English** — Cut the chicken and mushrooms into pieces. Fry the ginger and chicken in oil, then add the mushrooms, water, and soy sauce and braise until the chicken is cooked through.

**Potential issue** — The broad chicken-thigh label does not specify boneless or edible weight. The step gives no cut size or covered-simmer detail. Protein and vegetable tags leave the staple role uncovered.

**Proposed correction** — Confirm the starting cut and weigh the usable portion. Add a tested cut-size and simmer sequence, with reviewer-approved doneness guidance. Review whether the mushroom portion supports the vegetable role and treat the draft as a pairing component.

### recipe_000008 番茄炒蛋

**Tomato and scrambled eggs** · `family_000008` · 1 serving

- **Classification** — breakfast, lunch, dinner. Roles protein, vegetable. Methods stir fry.
- **Recorded time** — 6 min prep, 9 min cooking, 0 min modeled wait, 15 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 鸡蛋 / Egg | 2 piece | raw |
| 番茄 / Tomato | 180 g | raw |
| 食用油 / Cooking oil | 8 ml | ready_to_use |
| 盐 / Salt | 1 g | ready_to_use |

**Catalog instructions, Chinese** — 将番茄切块，鸡蛋打散。用部分油将鸡蛋炒至凝固，再用余油炒软番茄。混合后加盐。

**Catalog instructions, English** — Chop the tomato and beat the eggs. Scramble the eggs in some of the oil until set, soften the tomatoes in the rest, then combine and season.

**Potential issue** — An egg count plus tomato weight is understandable, but egg and tomato size affect yield and the oil split is underspecified. The same principal egg appears in two other drafts.

**Proposed correction** — Trial a documented egg size and tomato trim basis. Record how the oil is divided and include the transfer or holding step. Keep the dish as protein plus vegetable and avoid scheduling other egg-led drafts in the same day when alternatives fit.

### recipe_000010 蒜蓉小白菜

**Garlic bok choy** · `family_000010` · 1 serving

- **Classification** — lunch, dinner. Roles vegetable. Methods stir fry.
- **Recorded time** — 5 min prep, 6 min cooking, 0 min modeled wait, 11 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 小白菜 / Bok choy | 180 g | raw |
| 蒜 / Garlic | 6 g | raw |
| 食用油 / Cooking oil | 6 ml | ready_to_use |
| 盐 / Salt | 1 g | ready_to_use |

**Catalog instructions, Chinese** — 将小白菜洗净切段。用油炒香蒜末，再下小白菜炒熟，加盐。

**Catalog instructions, English** — Wash and cut the bok choy. Fry minced garlic in oil, stir-fry the greens until tender, and add salt.

**Potential issue** — The record specifies neither trimmed weight nor when to add stems and leaves. Six minutes of cooking may not reflect the reviewer’s pan and burner. This is a vegetable component.

**Proposed correction** — Specify whether 180 g is washed and trimmed weight. Test the cut size and whether stems need a head start. Leave salt in grams until a measured and reviewed household label is available.

### recipe_000014 胡萝卜米饭

**Carrot rice** · `family_000014` · 1 serving

- **Classification** — lunch, dinner. Roles staple. Methods simmer.
- **Recorded time** — 6 min prep, 21 min cooking, 0 min modeled wait, 27 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 大米 / Rice | 75 g | dry |
| 胡萝卜 / Carrot | 45 g | raw |
| 水 / Water | 160 ml | ready_to_use |

**Catalog instructions, Chinese** — 淘洗大米，将胡萝卜切小丁。与水同煮，转小火盖盖煮至米饭熟透。

**Catalog instructions, English** — Rinse the rice and finely dice the carrot. Bring both to a boil with the water, cover, and simmer until the rice is cooked.

**Potential issue** — The rice variety, rinsing water, and resting time are unspecified. The 160 mL appears to be cooking water. A 45 g carrot addition is tagged as supporting and may be mistaken for a full vegetable component.

**Proposed correction** — Distinguish cooking water from processing water and define the rice and pot assumptions. Trial the ratio and measure any covered rest separately. Keep the staple-only tag unless a later reviewed version changes role coverage.

### recipe_000016 鸡蛋小白菜炒饭

**Egg and bok choy fried rice** · `family_000016` · 1 serving

- **Classification** — lunch, dinner. Roles protein, staple, vegetable. Methods stir fry.
- **Recorded time** — 6 min prep, 10 min cooking, 0 min modeled wait, 16 min total. Start with cooked rice.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 大米 / Rice | 170 g | cooked |
| 鸡蛋 / Egg | 2 piece | raw |
| 小白菜 / Bok choy | 100 g | raw |
| 食用油 / Cooking oil | 8 ml | ready_to_use |
| 盐 / Salt | 1 g | ready_to_use |

**Catalog instructions, Chinese** — 小白菜洗净切碎。先用油炒熟鸡蛋，再加入小白菜和熟米饭炒至热透，加盐。

**Catalog instructions, English** — Wash and chop the bok choy. Scramble the eggs in oil until set, then stir-fry with the greens and cooked rice until hot throughout. Season with salt.

**Potential issue** — The 16-minute estimate starts with cooked rice. The steps omit how to handle the hot pan between eggs and greens, and a cold or clumped rice starting state could change timing.

**Proposed correction** — Clarify the starting rice condition and the order of transferring eggs and cooking stems and leaves. Record heat-up and elapsed time with a reviewer. Keep all three roles provisional until the cooked yield is checked.

### recipe_000017 虾仁西兰花盖饭

**Shrimp and broccoli rice bowl** · `family_000017` · 1 serving

- **Classification** — lunch, dinner. Roles protein, staple, vegetable. Methods stir fry.
- **Recorded time** — 8 min prep, 12 min cooking, 0 min modeled wait, 20 min total. Start with cooked rice.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 大米 / Rice | 170 g | cooked |
| 虾仁 / Peeled shrimp | 120 g | raw |
| 西兰花 / Broccoli | 130 g | raw |
| 蒜 / Garlic | 4 g | raw |
| 食用油 / Cooking oil | 6 ml | ready_to_use |
| 水 / Water | 35 ml | ready_to_use |
| 酱油 / Soy sauce | 6 ml | ready_to_use |

**Catalog instructions, Chinese** — 将熟米饭加热。炒香蒜，加西兰花和水焖至熟，再炒入虾仁至熟透。加酱油后盖在饭上。

**Catalog instructions, English** — Heat the cooked rice. Fry the garlic, cover the broccoli with the added water until tender, then stir-fry in the shrimp until cooked through. Season with soy sauce and serve over the rice.

**Potential issue** — The 20-minute estimate depends on cooked rice and on the shrimp’s starting condition. Reheating rice, chopping broccoli, and cooking toppings could exceed the limit on one burner. This shares cooked rice and a stir-fry method with recipe 000016.

**Proposed correction** — State thawing and prep assumptions, clarify that the listed oil is used in the frying step, and time the sequential version including reheating. Review the serving yield and product-specific label evidence. Keep distinct family IDs unless a reviewer finds the recipes indistinguishable for recommendations.

### recipe_000018 豆腐香菇青菜汤面

**Tofu, shiitake, and bok choy noodle soup** · `family_000018` · 1 serving

- **Classification** — lunch, dinner. Roles protein, staple, vegetable. Methods simmer.
- **Recorded time** — 8 min prep, 13 min cooking, 0 min modeled wait, 21 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 小麦面条 / Wheat noodles | 80 g | dry |
| 北豆腐 / Firm tofu | 140 g | ready_to_use |
| 鲜香菇 / Fresh shiitake | 55 g | raw |
| 小白菜 / Bok choy | 100 g | raw |
| 水 / Water | 520 ml | ready_to_use |
| 盐 / Salt | 2 g | ready_to_use |

**Catalog instructions, Chinese** — 香菇切片，豆腐切块，小白菜切段。将香菇和豆腐煮入汤中，再加入面条和小白菜煮熟，加盐。

**Catalog instructions, English** — Slice the mushrooms, cube the tofu, and chop the bok choy. Simmer the mushrooms and tofu in water, add the noodles and greens, cook until tender, and season.

**Potential issue** — The type of dry noodle can affect absorption, timing, and broth yield. Noodles and greens are added together without a tested sequence. The combined solid and broth yield could make one serving larger than intended.

**Proposed correction** — Trial a named noodle form and record when to add the greens. Check finished yield, texture, and the total from cold water. Retain weights until a verified noodle or tofu package reference is available.

### recipe_000019 冬瓜姜汤

**Winter melon and ginger soup** · `family_000019` · 1 serving

- **Classification** — lunch, dinner. Roles vegetable, accompaniment. Methods simmer.
- **Recorded time** — 7 min prep, 15 min cooking, 0 min modeled wait, 22 min total.
- **Source and status** — Original AI-assisted MealMind development draft. No independent verification, allergen evidence, or reuse clearance is recorded.

| Ingredient | Quantity | State |
| --- | --- | --- |
| 冬瓜 / Winter melon | 200 g | raw |
| 姜 / Ginger | 7 g | raw |
| 水 / Water | 450 ml | ready_to_use |
| 盐 / Salt | 1 g | ready_to_use |

**Catalog instructions, Chinese** — 冬瓜去皮切薄块，与姜片一同加水煮至冬瓜透明，加盐。

**Catalog instructions, English** — Peel and thinly slice the winter melon. Simmer with sliced ginger in water until translucent and season with salt.

**Potential issue** — The winter melon is peeled in the instructions, but the weight basis does not say whether it includes skin and seeds. Translucency varies with slice thickness. This is an accompaniment rather than a complete dinner.

**Proposed correction** — Define the 200 g on a reviewed trimmed basis, specify slice thickness and timing from cold water, and measure served broth and solids. Compare its use case with the carrot and corn soup before grouping or ranking the two.

## Decisions for the product owner

| Decision | Proposed disposition to confirm |
| --- | --- |
| Review outcome for each selected ID | Mark “revise and retest” or “hold” in the review record, and name the person who will test it. Keep draft status until corrections and evidence are reviewed. |
| Complete-meal candidates | Confirm 000016–000018 as the first candidates for a complete-meal cook-through. Confirm component-only defaults for the remaining nine selected dishes and decide whether 000001 and 000004 need distinct snack serving scales. |
| Inventory and yield conventions | Decide whether to track process water separately, use edible or as-purchased weights by ingredient, and report finished serving yield where liquid changes portion size. Resolve 000002 first because it uses both mixing and steaming water. |
| Timing review | Agree on a single-burner, cold-start default, when timer phases begin and end, and how to record the starting state. Decide whether to withhold the ≤20-minute label until the applicable scenario is timed. |
| Diversity | Decide whether the porridge and clear-soup pairs stay in distinct families with a similarity penalty or are grouped for diversity. Confirm that repeated cooked rice or eggs should be downranked where valid alternatives exist. |
| Household measures and safety | Prioritize the first measurement references and appoint the reviewers for portion evidence, recipe provenance and reuse, compound ingredients, allergen evidence, and cross-contact questions. Keep catalog eligibility closed where required evidence is absent. |
