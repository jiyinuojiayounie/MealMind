# MealMind nutrition reference snapshot v1

[`reference-v1.json`](reference-v1.json) is a curated extract of the USDA FoodData Central **SR Legacy April 2018** release. The selected food records have the FoodData Central publication date **2019-04-01**, which is separate from the dataset release. The extract was checked against the public USDA CSV archive on 2026-11-21. USDA publishes FoodData Central data under CC0 1.0 and requests source attribution. [USDA data and licensing](https://fdc.nal.usda.gov/) · [Official downloads](https://fdc.nal.usda.gov/download-datasets/)

Suggested attribution: U.S. Department of Agriculture, Agricultural Research Service, Beltsville Human Nutrition Research Center. FoodData Central. Accessed 2026-11-21.

## Coverage and use

| Category | Food-state rows | Examples |
| --- | ---: | --- |
| Grains | 6 | White and brown long-grain rice, dry and cooked oats |
| Noodles | 4 | Dry and cooked rice noodles and Japanese soba |
| Eggs | 3 | Raw, hard-boiled and poached whole eggs |
| Poultry | 3 | Raw skinless boneless chicken breast, roasted and stewed breast meat |
| Soy | 2 | Raw calcium-set firm tofu and boiled, drained edamame kernels |
| Other vegetables | 6 | Raw and unsalted boiled bok choy, broccoli and carrots |
| Tubers | 4 | Raw and boiled potatoes, raw and baked sweet potatoes |
| Fruit and oil | 2 | Raw peeled banana and canola oil |
| **Total** | **30** | |

Values are for 100 g of the described edible food. Energy is USDA nutrient 1008 in kcal, not recomputed. Protein (1003), carbohydrate by difference (1005), and total lipid (1004) are in grams and retain the source definitions. The extract has all four source values for each food. A release with missing or unreviewed qualified data must use explicit null for that value. A USDA row reporting zero remains zero. The metadata pins the release, archive URL and SHA-256. Each food carries its original USDA description, FDC ID/link, legacy NDB number, publication date and nutrient-row IDs.

Names and aliases are curated for exact variant matching. Use both bilingual names and the explicit aliases after NFKC, case folding and whitespace normalization. Generic or ambiguous labels are withheld from automatic matching. For example, `鸡胸肉`, `豆腐`, `米饭`, `青菜` and `noodles` may require state, variety or preparation details. Never substitute raw for cooked, water-boiled for stir-fried, or plain ingredients for mixed dishes. This is a small US reference extract, so products, cultivars, coagulants, cooking methods, water uptake and added oil can differ from an actual meal.

Three optional portion records retain exact USDA `food_portion.csv` IDs, modifiers, measure unit IDs and edible gram weights. They apply only to a USDA large raw whole egg, a USDA large hard-boiled whole egg, or a medium raw banana matching the source's length descriptor. Match the specific state and edible basis. A generic egg, banana, bowl, cup, piece or serving does not have an automatic conversion. No other portion conversions are bundled.

## Reproduce the audit

Download only the official April 2018 SR Legacy CSV archive to a location outside the repository. Run the offline audit from the repository root:

```sh
cd backend
.venv/bin/python -m scripts.verify_nutrition_reference /path/to/FoodData_Central_sr_legacy_food_csv_2018-04.zip
```

The tool verifies the archive checksum and compares the extract with `food.csv`, `sr_legacy_food.csv`, `nutrient.csv`, `food_nutrient.csv`, and `food_portion.csv`. It checks values as decimals without nutrient imputation. The ZIP is needed only for the audit. The backend validator can load the curated extract offline and uses existing Pydantic dependencies. New releases should document source and alias review and keep published food IDs stable. No food-log or meal-planning path reads this snapshot yet.
