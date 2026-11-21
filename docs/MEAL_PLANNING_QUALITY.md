# Meal planning quality v1

Proposed for Day 4 review. This specification refines FR04 and supplies evaluation criteria for a future implementation. [PRD](PRD.md) and [decision record](DECISIONS.md) remain the product baseline. The companion design defines catalog metadata, candidate selection, and API compatibility. [Recipe catalog design](RECIPE_CATALOG_DESIGN.md)

## Request intent and meal composition

Classify what each requested slot should deliver: a complete meal, a requested dish, or a snack. An unqualified request such as “plan dinner” defaults to a complete meal. “Give me a garlic greens recipe” requests one dish. “Plan dinner around garlic greens” requests a complete meal anchored on that dish. Ask a short question when interpreting the request would materially change the result and the intended scope is unclear.

Use culinary roles as a planning heuristic. They describe what is on the table and do not establish nutrient adequacy, calorie targets, or portion requirements for an individual.

| Request | Default composition |
| --- | --- |
| Complete lunch or dinner | Cover a protein component, staple or starchy component, and a vegetable component. A one-pot or mixed dish can cover multiple roles when its reviewed ingredients and serving justify them. A garnish or a few pieces of an ingredient do not establish role coverage. |
| Complete breakfast | Prefer a staple and a practical protein component. Fruit or vegetables can round it out when suitable. Respect preferences for light or simple breakfasts. |
| Full day | Plan breakfast, lunch, and dinner, with an optional snack. Apply the slot defaults and assess repetition across the day. Keep specified or confirmed meals intact and support variety in the remaining slots when that context is available. |
| Requested dish or snack | Return the requested item or snack-sized suggestion. Optional pairings can be offered if relevant and permitted by the user's constraints. |
| Explicit combination or omission | Preserve the requested combination or role omission. Explain a meaningful departure from the complete-meal default without trying to compensate at a later meal. |

Present quantities for the requested servings, with one serving as the default when unspecified. Avoid calorie restriction, compensatory meal skipping, weight-loss targets, and mandatory portions. Honor feasible preferences for effort, equipment, and familiar Chinese home cooking.

## Constraints and exceptions

1. **Check safety first.** Exclude known conflicts with stated allergies and strict dietary exclusions, including compound ingredients, substitutions, seasonings, and instructions. Treat unresolved aliases or unknown allergen applicability as unknown. With relevant uncertainty, ask for clarification or withhold the candidate. Review packaged-product labels and cross-contact separately from recipe metadata. Never guarantee allergy safety.
2. **Apply explicit request constraints.** Respect named dishes, food combinations, portions, ingredients, equipment, time, and scope. Combine compatible structured fields and natural-language requirements. Apply a default only when the user has left that choice open. Ask when explicit requirements conflict or have materially different interpretations. Keep preferences soft unless the user makes them mandatory.
3. **Check availability by mode.** Existing mode requires every ingredient, including water, oils, and seasonings, to be confirmed under the current contract. Unknown quantities indicate uncertain sufficiency. Flexible mode may suggest additions when the request permits them and should list what is missing from the known supply. Update mode can apply the existing-mode rule to a user-confirmed fresh snapshot once that flow exists.
4. **Check feasibility before relaxing defaults.** If the hard constraints leave only a vegetable dish for a complete dinner, explain the unmet meal roles and offer the feasible dish as a labeled partial option or ask which constraint the user wants to change. Preserve all safety, timing, and inventory restrictions. Treat a labeled partial option as distinct from a completed plan.
5. **Explain estimates and uncertainty.** Use recipe-scale estimates. Avoid claiming a meal is nutritionally complete, treats a condition, or satisfies precise calorie or macro targets. Future nutrient estimates must come from the deterministic nutrition engine and structured sources described in FR07.

## Times and quantities

- Define active preparation time as hands-on work before cooking. Define cooking time as time under heat. Record passive waits such as soaking, resting, and marinating separately. Report estimated total elapsed time from the assumed starting state until serving, including waits and sequencing. List assumptions such as already cooked rice or ready-to-use stock.
- For multi-dish meals, use a conservative sequential total by default. Count overlapping work only if a reviewed schedule and available equipment support it. Treat an under-20-minute request as a total elapsed-time limit unless the user explicitly specifies cooking-only time. If the intended timing metric is unclear and changes feasibility, ask.
- Keep the numeric quantity and unit for scaling. Prefer a reviewed household display measure when suitable, for example “about ½ block (100 g)” only for the documented block size and ingredient state. Use count, spoon, cup, or package fractions only with an appropriate reference. Retain metric units when no trustworthy conversion exists. Avoid vague measures for meaningful amounts and show approximation when size varies.

## Diversity rules

Apply diversity ranking after hard filtering. For a full day, disallow repeated dish families by default. Flag a repeated primary ingredient when it is prominent in two or more meal slots, regardless of alias or language. Prefer feasible combinations with distinct primary proteins or produce and a mix of cooking methods. Exempt pantry seasonings and neutral staples used as accompaniments. A staple that defines the dish can count as a primary ingredient.

Allow repetition when the user requests batch cooking, leftovers, a specific combination, or when the safe available pool is too small. Explain material repetition caused by constraints. Keep exact repetitions and family repetitions visible in evaluation, even when the exception is valid.

## Proposed acceptance criteria

Use versioned fictional fixtures and a fixed catalog revision. Measure deterministic rules with mocked output. In a later approved evaluation, score bilingual natural-language intent and result quality with a reviewed rubric. Report each numerator and denominator and track clarified, infeasible, and provider-error cases individually.

| Measure | Proposed v1 target and denominator |
| --- | --- |
| Hard constraints | Zero violating returned plans in the safety and feasibility fixture suite. Include aliases, hidden allergens, uncertain metadata, all used ingredients, and aggregate time. A case passes only if it returns a valid result or a correct clarification or refusal. |
| Complete meal roles | At least 95% of feasible, unqualified complete-meal slots cover their required roles. Count blank or partial outputs on feasible cases as failures. Score explicit dish, snack, and approved omission fixtures independently. |
| Explicit intent | At least 90% of annotated requests produce the requested outcome type and scope or the expected clarification. Include Chinese, English, and mixed-language inputs. |
| Within-day variety | Zero unjustified repeated families in feasible full days with reviewed distinct alternatives. At least 90% of those days avoid repeating non-exempt primary ingredients where feasible. Report allowed-repeat counts and reasons separately. |
| Approximate measures | Every displayed conversion traces to a reviewed reference or explicit approximation. On ingredients with a reviewed household conversion, at least 90% of applicable ingredient lines show it. Verify round-trip scaling within the reference's stated tolerance. |
| Timing | Every accepted time-limited fixture fits the declared metric using the reviewed schedule. At least 90% of reviewed multi-dish examples clearly distinguish total elapsed time from time under heat. Record estimate errors in later cook-through checks. |
| Product claims | Zero unsupported numeric nutrition, medical or allergy-safety claims in the reviewed outputs. Track missing results separately from output violations. |

### Example fixtures

| Input or setup | Expected |
| --- | --- |
| “给我安排一份中式晚餐”, only vegetable side returned | Reject as a complete dinner. A reviewed mixed dish covering three roles can pass on its own. |
| “只想做一道蒜蓉青菜” and “晚餐想以蒜蓉青菜为主” | First is a dish request. Second is a complete dinner anchored on the named vegetable dish. |
| “A light breakfast”, “one afternoon snack”, and “tofu and rice, no side dish” | Respect lightness, snack scope, or explicit pairing. Avoid silently adding required dishes. |
| “Plan breakfast, lunch and dinner”, duplicate tomato-and-egg family under translated names | Prefer distinct families when feasible. Count repetition by canonical ID even across aliases. |
| Existing mode with only cabbage, water, and salt, complete dinner requested | Explain role shortfall or ask how to proceed. Do not add oil, protein, or rice without permission. |
| Peanut allergy, sauce with unknown allergen metadata, or a packaged substitution | Reject a known conflict. Exclude or clarify the unknown and never claim cross-contact safety. |
| 20-minute limit, recipe needs a thirty-minute soak before brief cooking | Reject if starting from dry ingredients. Accept a faster version only if its starting state is confirmed. |
| Two 12-minute dishes and one burner | Reject a 20-minute elapsed limit under sequential prep. Accept a reviewed overlapping schedule only when feasible. |
| 100 g tofu, unknown block size, one serving | Display grams. Offer a package fraction only when a valid reference is available. |
| “A mushroom dinner, one main and rice, no advice about weight loss” | Offer the requested pairing, explain any deliberate role omission, and avoid medical or calorie claims. |

## Product-owner review

Confirm the meal-role templates and exception language, which timing metric the existing limit will use, whether partial plans or clarification should take priority when inputs are infeasible, and the proposed evaluation targets. These decisions are proposals for review before implementation.
