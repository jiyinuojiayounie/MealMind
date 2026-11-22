# Food normalization v1 evaluation design

Proposed gold cases against the current 30-record reference snapshot. These are fictional inputs, not measured results. Review the IDs, state rules, and portion evidence before freezing the set. Do not add aliases derived from held-out cases until the run is complete.

**Identity codes**: M = matched, C = clarification, G = known food or preparation absent from the catalog, U = unidentified. **Portion codes**: E = explicit edible mass, V = verified food-specific conversion, Q = unknown amount, X = no verified conversion, R = needs evidence review. Evaluate identity and portion independently. E never permits a calculation when identity is unresolved. Cases with conflicting or uncertain inputs must abstain from binding.

| ID | Input or draft evidence | Expected identity (ID or issue) | Portion |
|---|---|---|---|
| 01 | 无盐熟长粒白米（未强化）150克 | M white_rice_long_grain_unenriched_cooked | E |
| 02 | 生长粒白米（未强化）50g | M white_rice_long_grain_unenriched_raw | E |
| 03 | 熟长粒糙米 150g | M brown_rice_long_grain_cooked | E |
| 04 | 生长粒糙米 60 克 | M brown_rice_long_grain_raw | E |
| 05 | 半碗糙米饭 | C grain type not specified | X |
| 06 | 半碗熟长粒糙米 | M brown_rice_long_grain_cooked | X |
| 07 | 白米饭一碗 | C grain type and reference qualifiers | X |
| 08 | 150 g cooked long-grain brown rice | M brown_rice_long_grain_cooked | E |
| 09 | 150Ｇ 熟长粒糙米 | M brown_rice_long_grain_cooked | E |
| 10 | 未强化干燕麦片 40 克 | M oats_unfortified_dry | E |
| 11 | 150g鸡胸肉 | C cooking state and edible basis | R |
| 12 | 去皮去骨鸡胸肉，生重 150g | M chicken_breast_skinless_boneless_raw | E |
| 13 | 去皮去骨烤鸡胸肉 150g | M chicken_breast_meat_roasted | E |
| 14 | skinless boneless chicken breast, stewed, 100 g | M chicken_breast_meat_stewed | E |
| 15 | 熟鸡胸肉 150 克 | C cooking method and edible basis | R |
| 16 | 烤鸡胸肉（仅肉），150 g，生重 | C conflicting reference and measurement state | R |
| 17 | 生全蛋（去壳）50g | M whole_egg_raw | E |
| 18 | 一个水煮蛋 | C doneness if unspecified | X |
| 19 | 一个全熟白煮蛋（去壳） | M whole_egg_hard_boiled | X |
| 20 | 一个美标大号全熟去壳水煮蛋 | M whole_egg_hard_boiled | V |
| 21 | water-poached egg, 50 g edible | M whole_egg_poached | E |
| 22 | 炒鸡蛋 100g | G no exact stir-fried reference | E |
| 23 | 干米粉 60g | M rice_noodles_dry | E |
| 24 | cooked rice noodles, 150 g | M rice_noodles_cooked | E |
| 25 | 米粉 100g | C identity and measured state | E |
| 26 | Japanese soba (cooked), half a cup | M soba_cooked | X |
| 27 | 80g 日式干荞麦面 | M soba_dry | E |
| 28 | 一盘青菜 | C vegetable and preparation | X |
| 29 | 小白菜（水煮沥干，无盐）100 克 | M bok_choy_boiled_unsalted | E |
| 30 | raw pak choi | M bok_choy_raw | Q |
| 31 | raw brocoli 100g | C offer broccoli_raw from typo shortlist | E |
| 32 | 生西蘭花 80 克 | M broccoli_raw via reviewed script alias | E |
| 33 | 无盐水煮西兰花（沥干）一些 | M broccoli_boiled_unsalted | Q |
| 34 | 无盐水煮胡萝卜（沥干）100g | M carrot_boiled_unsalted | E |
| 35 | raw carrots 70 grams | M carrot_raw | E |
| 36 | 石膏凝固硬豆腐（未烹调）100g | M firm_tofu_calcium_sulfate_raw | E |
| 37 | 豆腐 100g | C firmness, coagulant and preparation | E |
| 38 | 一块煎豆腐 | G no exact pan-fried reference | X |
| 39 | edamame kernels, boiled, drained, no salt, 90 g | M green_soybeans_boiled_unsalted | E |
| 40 | baked sweet potato (flesh only, without salt) 90g | M sweet_potato_flesh_baked_unsalted | E |
| 41 | 一根美标中等香蕉（去皮，长度符合 USDA） | M banana_raw | V |
| 42 | 去皮生香蕉一根，大小不详 | M banana_raw | X |
| 43 | 拿铁咖啡一杯 | G no matching beverage | X |
| 44 | 海南鸡饭一份 | G no exact mixed-dish reference | X |
| 45 | beef noodle soup 一碗 | G no exact mixed-dish reference | X |
| 46 | 番茄炒蛋 100g | G no exact mixed-dish reference | E |
| 47 | 两个煎饺 | G no exact mixed-dish reference | X |
| 48 | oat milk 200 ml | G no matching beverage | X |
| 49 | some flarbo | U no identifiable food | Q |
| 50 | canola oil in the pan, 15g; amount eaten unknown | M canola_oil_as_sold | Q, preserve only the unknown consumed amount |

Case 50 tests that a pan input is not misread as an explicitly eaten weight. For cases marked E with unresolved identity, the amount is retained as evidence and no nutrient calculation is performed. Test label punctuation and script normalization in both directions.

## Execution protocol

- Use these cases through the draft normalization preview as structured inputs. For a subset, additionally run paired manual, mocked text recognition and mocked image-recognized rows with equivalent evidence. Include variants that remove evidence from the photo-derived row. A change of entry path alone must not change a match; weaker evidence can change the expected result. Add adversarial variants with instructions embedded in labels and out-of-shortlist provider IDs.
- Before implementation, have a second reviewer check each label against the reference snapshot and relevant portion evidence, then agree or mark it unresolved. Freeze target IDs, statuses and acceptable reasons. Use a separate tuning sample and leave this test set held out. Run deterministic and hybrid modes on identical inputs. Record counts, denominators and slices by language, state, portion and mixed-dish category. If real-model testing is later approved, keep input, model/version, prompt revision and local snapshot fixed. Use fictional data only.
- Report automatic results and assisted suggestions separately. Assisted accuracy counts the expected candidate ranking or correct abstention before any simulated user answer. Report verified identity coverage separately from nutrition calculability, including cases where identity matched but portion did not. The source snapshot and confirmed records must remain unchanged during evaluation.

| Metric | Proposed v1 gate |
|---|---|
| Exact deterministic ID accuracy | At least 95% on gold M cases, counting an abstention as a miss. Report precision separately over automatic bindings. |
| Incorrect/unsafe automatic actions | Zero across all cases and adversarial variants. Count wrong state or preparation, guessed grams, unavailable portion factors, and invented or mismatched IDs. |
| Unnecessary clarification | At most 5% of gold M cases for identity. A separate legitimate portion question is counted in the portion slice only. |
| Unsupported food | At least 90% recall on gold G cases, with zero forced matches. Report G-to-U confusion and correct U abstentions separately. |
| Model use | Zero calls for exact matches, confirmed-history analysis, known catalog gaps, and portion-only questions. At most one on an explicit assisted batch; target at most 20% of cases with a call when opt-in assistance is requested for all remaining eligible cases. |
| Latency | Measure p50/p95 end-to-end on the same local setup. Proposed p95 at most 500 ms for deterministic preview and 8 s for assisted preview, reporting timeout rate separately. Mock timings are only a plumbing check. |
| Improvement gate | Hybrid mode must improve correct identification among eligible C/U suggestions over the deterministic shortlist and preserve zero unsafe automatic actions. Report added latency and clarification counts before rollout. |
