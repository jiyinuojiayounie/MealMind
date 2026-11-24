"""Deterministic proxies for meal structure and preparation effort, not nutrition analysis."""

import re
import unicodedata

from app.schemas.meal_plans import Dish, GeneratedMealPlan, MealPlanRequest
from app.services.planning_intent import INGREDIENT_ALIASES, SINGLE_DINNER_DISH, SINGLE_DISH

# Multiword labels are kept intact rather than matching arbitrary ingredient substrings.
ENGLISH_ROLES = {
    "protein": set("egg|eggs|duck egg|chicken|chicken breast|chicken thigh|pork|beef|fish|salmon|shrimp|prawns|tuna|tofu|firm tofu|silken tofu|tempeh|edamame|lentils|chickpeas|black beans|kidney beans|soybeans".split("|")),
    "staple": set("rice|cooked rice|brown rice|white rice|noodles|rice noodles|soba|udon|oats|oatmeal|potato|sweet potato|bread|toast|millet|quinoa|couscous".split("|")),
    "vegetable": set("tomato|tomatoes|bok choy|cabbage|napa cabbage|broccoli|spinach|carrot|carrots|cucumber|zucchini|eggplant|bell pepper|cauliflower|mushroom|mushrooms|lettuce|green beans|kale".split("|")),
}
CHINESE_ROLES = {
    "protein": set("鸡蛋 鸭蛋 鸡肉 鸡胸肉 鸡腿肉 猪肉 牛肉 鱼肉 三文鱼 虾 虾仁 豆腐 豆腐皮 北豆腐 嫩豆腐 老豆腐 豆干 天贝 毛豆 扁豆 鹰嘴豆 黑豆 黄豆".split()),
    "staple": set("米饭 熟米饭 糙米饭 糙米 白米 大米 小米 米粉 米线 面条 荞麦面 乌冬面 燕麦 燕麦片 土豆 红薯 馒头 面包 吐司 藜麦".split()),
    "vegetable": set("番茄 西红柿 小白菜 上海青 青菜 白菜 大白菜 菠菜 菠菜叶 西兰花 胡萝卜 黄瓜 西葫芦 茄子 彩椒 花菜 蘑菇 鲜香菇 香菇 生菜 四季豆 油麦菜".split()),
}
CHINESE_WEIGHTS = {"克", "公克", "千克", "公斤"}
MASS = {"g", "gram", "grams", "kg", "kilogram", "kilograms"} | CHINESE_WEIGHTS
KILOGRAMS = {"kg", "kilogram", "kilograms", "千克", "公斤"}
LIGHT = re.compile(r"只(?:吃|做|要)(?:一道菜|蔬菜|一碗汤)|(?:想吃|来)(?:一顿)?简餐|\b(?:light meal|light dinner|light lunch|vegetable-only|only vegetables|just a bowl of soup)\b")
LIGHT_BY_SLOT = {
    "lunch": re.compile(r"午餐(?:只吃|只做)(?:蔬菜|一道菜|一碗汤)|\blight lunch\b"),
    "dinner": re.compile(r"晚餐(?:只吃|只做)(?:蔬菜|一道菜|一碗汤)|\blight dinner\b"),
}
NOT_LIGHT = re.compile(r"不要简餐|不是简餐|\b(?:not|no) (?:a )?light (?:meal|dinner|lunch)\b")
VEGETARIAN = re.compile(r"素食|全素|纯素|(?<![-\w])(?:vegetarian|vegan)\b")
NOT_VEGETARIAN = re.compile(r"(?:不是|不需要|不用)素食|\b(?:not|non[- ])(?:\s*a)?\s*(?:vegetarian|vegan)\b")
ANIMAL_FOODS = {
    *"chicken|chicken breast|chicken thigh|pork|beef|fish|salmon|shrimp|prawns|tuna|fish sauce|oyster sauce|chicken stock|beef stock".split("|"),
    *"鸡肉 鸡胸肉 鸡腿肉 猪肉 牛肉 鱼肉 三文鱼 虾 虾仁 鱼露 蚝油 鸡汤 牛肉汤".split(),
}
BLOCKING_QUALITY_ISSUES = frozenset({"explicit_diet_conflict"})
EGG_DAIRY = {"egg", "eggs", "duck egg", "milk", "yogurt", "cheese", "butter", "鸡蛋", "鸭蛋", "牛奶", "奶酪", "黄油", "酸奶"}
ELABORATE = re.compile(r"丰盛|多道菜|宴客|\b(?:elaborate|feast|banquet|multi.course)\b")
GROUP = re.compile(r"多人|两人份|三人份|四人份|\b(?:for (?:two|three|four|[2-9]|guests)|batch cooking)\b")
CULINARY_ACTIONS = (
    ("stir_fry", r"炒|stir[- ]fr"),
    ("steam", r"蒸|\bsteam"),
    ("simmer", r"煮|炖|焖|\b(?:simmer|boil|stew|poach)"),
    ("bake", r"烤|\b(?:roast|bake)"),
    ("fry", r"煎|炸|\b(?:fry|pan[- ]sear)"),
    ("mix", r"凉拌|拌匀|\b(?:mix|toss|assemble)\b"),
)
COOKED_STAPLES = {"cooked rice", "bread", "toast", "熟米饭", "米饭", "面包", "吐司", "馒头"}


def quality_key(text: str) -> str:
    return " ".join(re.findall(r"\w+", unicodedata.normalize("NFKC", text).casefold()))


def ingredient_role(name: str) -> str | None:
    key = quality_key(name)
    for role, labels in ENGLISH_ROLES.items():
        if key in labels or key in CHINESE_ROLES[role]:
            return role
    return None


def _mass_grams(quantity: float, unit: str) -> float | None:
    key = quality_key(unit)
    if key not in MASS:
        return None
    return quantity * (1000 if key in KILOGRAMS else 1)


def _core_key(name: str) -> str:
    alias = INGREDIENT_ALIASES.get(quality_key(name))
    return alias[0] if alias else quality_key(name)


def method(dish: Dish) -> str | None:
    for text in (dish.name, *dish.instructions):
        for key, pattern in CULINARY_ACTIONS:
            if re.search(pattern, text.casefold()):
                return key
    return None


def _simple_side(dish: Dish) -> bool:
    roles = {ingredient_role(ingredient.name) for ingredient in dish.ingredients}
    return roles == {"staple"} and all(quality_key(item.name) in COOKED_STAPLES for item in dish.ingredients)


def quality_issues(
    plan: GeneratedMealPlan,
    request: MealPlanRequest,
    *,
    missing_roles_by_meal: dict[str, list[str]] | None = None,
) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKC", request.user_request).casefold()
    light = not NOT_LIGHT.search(text) and (
        bool(LIGHT.search(text)) or any(
            clause.strip() in SINGLE_DISH | SINGLE_DINNER_DISH for clause in re.split(r"[,。;.!?]", text)
        )
    )
    default_effort = not (ELABORATE.search(text) or GROUP.search(text))
    plant_only = bool(re.search(r"全素|纯素|\bvegan\b", text))
    vegetarian = VEGETARIAN.search(text) and not NOT_VEGETARIAN.search(text)
    excluded = (ANIMAL_FOODS | EGG_DAIRY if plant_only else ANIMAL_FOODS) if vegetarian else set()
    seen_names: set[str] = set()
    seen_patterns: set[tuple[str, frozenset[str]]] = set()
    issues = []
    for meal in plan.meals:
        ingredients = tuple(item for dish in meal.dishes for item in dish.ingredients)
        # A trace garnish in an explicit gram entry is not a meal component.
        roles = {
            ingredient_role(item.name) for item in ingredients
            if (grams := _mass_grams(item.quantity, item.unit)) is None or grams >= 5
        }
        if excluded.intersection(quality_key(item.name) for item in ingredients):
            issues.append("explicit_diet_conflict")
        if meal.meal_type in LIGHT_BY_SLOT and not (
            light and (len(plan.meals) == 1 or LIGHT_BY_SLOT[meal.meal_type].search(text))
        ):
            missing = {"protein", "staple", "vegetable"} - roles
            if missing:
                issues.append("missing_complete_meal_roles")
                if missing_roles_by_meal is not None:
                    missing_roles_by_meal[meal.meal_type] = sorted(missing)
        if default_effort and meal.meal_type == "breakfast":
            cooked = sum(method(dish) not in {None, "mix"} for dish in meal.dishes if not _simple_side(dish))
            if cooked > 1 and meal.estimated_preparation_minutes > 25:
                issues.append("multiple_slow_breakfast_dishes")
        if default_effort and (
            len({quality_key(item.name) for item in ingredients}) > 12
            or any(
                ingredient_role(item.name) and (_mass_grams(item.quantity, item.unit) or 0) > 1000
                for item in ingredients
            )
        ):
            issues.append("impractical_meal_size_or_effort")

        for dish in meal.dishes:
            if _simple_side(dish):
                continue
            name = quality_key(dish.name)
            if name in seen_names:
                issues.append("repeated_dish")
            seen_names.add(name)
            core = frozenset(_core_key(item.name) for item in dish.ingredients if ingredient_role(item.name))
            cooking_method = method(dish)
            if len(core) >= 2 and cooking_method:
                pattern = cooking_method, core
                if pattern in seen_patterns:
                    issues.append("repeated_cooking_pattern")
                seen_patterns.add(pattern)
    return tuple(dict.fromkeys(issues))
