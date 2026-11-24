# Blind Box candidate review

Ten one-serving candidates from the 26 drafts in `catalog-v4.json`. The development shortlist covers four breakfast, seven lunch and six dinner choices (some meals fit two slots). All times include the preparation and cooking recorded in the draft, subject to the listed starting conditions. Amounts, time, and practical yield still need a cook-through. Dietary concerns below are ingredient-screening notes only. Packaged ingredients and cross-contact are unverified for all candidates.

| Recipe ID and meal | Slots | Ingredients | Estimated total and prerequisites | Dietary concerns | Why shortlist |
|---|---|---|---|---|---|
| `recipe_000003` 玉米燕麦粥 | Breakfast | Oats, corn, water | 14 min with quick oats and frozen corn | Check oats for gluten cross-contact | Simple warm breakfast with one pot and three ingredients |
| `recipe_000021` 香蕉酸奶燕麦碗 | Breakfast | Yogurt, banana, ready-to-eat oats | 5 min, no cooking | Milk; check oats for gluten cross-contact | No-cook option with minimal washing |
| `recipe_000022` 炒蛋全麦面包配黄瓜 | Breakfast | Eggs, whole-grain bread, cucumber, oil, salt | 11 min | Egg and wheat; check bread label | One cooked component with ready-to-eat sides |
| `recipe_000023` 鸡蛋小白菜汤米粉 | Breakfast, lunch | Egg, bok choy, rice vermicelli, water, salt | 15 min with no-soak quick rice vermicelli | Egg; check noodle label | Hot one-pot option suitable for two slots |
| `recipe_000016` 鸡蛋小白菜炒饭 | Lunch, dinner | Cooked rice, eggs, bok choy, oil, salt | 16 min with safely stored cooked rice | Egg | Makes practical use of ready cooked rice |
| `recipe_000017` 虾仁西兰花盖饭 | Lunch, dinner | Cooked rice, shrimp, broccoli, garlic, oil, water, soy sauce | 20 min with safely stored cooked rice and thawed, peeled shrimp | Crustacean shellfish and soy; sauce may contain wheat | Adds seafood and a rice bowl to the rotation |
| `recipe_000018` 豆腐香菇青菜汤面 | Lunch, dinner | Wheat noodles, tofu, shiitake, bok choy, water, salt | 21 min from cold water with dry noodles and drained tofu | Wheat and soy; check noodles for other ingredients | One-pot soup noodle with supermarket staples |
| `recipe_000024` 番茄青菜豆腐燕麦羹 | Lunch, dinner | Tofu, tomato, bok choy, oats, water, salt | 19 min with quick oats | Soy; check oats for gluten cross-contact | Savory oat option for variety without a separate side |
| `recipe_000025` 鸡肉卷心菜炒乌冬 | Lunch, dinner | Chicken, cabbage, carrot, packaged udon, oil, soy sauce, water | 19 min with thawed boneless chicken and ready-to-use cooked udon | Soy; verify wheat and any other allergens on sauce and noodle labels | One-pan option with familiar ingredients |
| `recipe_000026` 番茄土豆鹰嘴豆炖菜 | Lunch, dinner | Cooked chickpeas, potato, tomato, water, salt | 24 min with cooked chickpeas; rinsing uses separate process water | Chickpeas; check packaged product label | Legume-and-potato meal with one pot |

These selections are eligible only in the Vite development demo. Their catalog review status remains `draft`. Every explicit restriction blocks these demo candidates because there is no reviewed compatibility evidence. With no restriction declaration, eligibility conveys no allergy or dietary assurance.

The other 16 drafts are mostly sides, soups, separate mains or slower breakfasts. Review the ten proposed recipes for taste, one-person yield, cook-through time, instructions, and packaged ingredient evidence before approving a production pool. Confirm whether the lighter corn and oat porridge is substantial enough for the intended breakfast offering.

## Step 2 demo pool

The product owner selected nine recipes for the initial pool. The tomato and greens tofu oat bowl stays in the catalog and is excluded from the box. The corn and oat porridge remains a standalone light breakfast. These choices approve the content direction for the demo. The catalog retains draft status and packaged ingredient and allergen evidence remains unverified.

Blind Box displays cooked rice for the two recipes using 170 g of cooked rice. The shrimp bowl explicitly requires safely thawed, peeled and deveined shrimp before timing starts. The rice vermicelli instructions cook the egg first and follow the no-presoak noodle package timing. The chicken udon card uses a provisional 24-minute total, allowing five more minutes for handling raw chicken and cleaning utensils. A cook-through is still needed. These adjustments apply to Blind Box only.

Saving uses the existing browser plan store. The preview shows the current target slot and requires confirmation. A fresh local food-log context blocks a consumed slot, and an IndexedDB transaction checks the accepted plan version before merging the recipe snapshot. SQLite and IndexedDB do not share an atomic transaction, so a food log confirmed after the final context check can still race with acceptance. The draw itself performs no persistence or provider calls.

## Public portfolio selection

The nine Step 2 selections are authorized for the public portfolio demo and copied into a separate, closed public asset. They retain their draft catalog status. Content selection does not add cook-through, packaging, or allergen evidence. The nine are original MealMind development recipes. HowToCook adaptations and the second batch remain outside the public pool. Declaring an allergy or dietary restriction still prevents recommendation from this pool.
