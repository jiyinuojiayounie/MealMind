"""Isolated Chrome fixture app. Start only from the browser regression runner."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from google.genai import errors

from app.core.settings import Settings
from app.main import create_app
from app.schemas.food_recognition import QuotedFoodItem, QuotedFoods
from app.services import food_recognition, meal_plans
from app.services.meal_plans import PlannerFailure

CASES = {
    "吃了150g去皮去骨鸡胸肉（生）": ("去皮去骨鸡胸肉（生）", "150g去皮去骨鸡胸肉（生）", "150g"),
    "炒菜用了8g油，但锅里还剩一些": ("油", "8g油", "8g"),
    "买了200g鸡胸肉，只吃了一部分": ("鸡胸肉", "200g鸡胸肉", "200g"),
    "半碗糙米饭": ("糙米饭", "半碗糙米饭", "半碗"),
    "吃了些低芥酸菜籽油": ("低芥酸菜籽油", "吃了些低芥酸菜籽油", None),
}


CONTEXT_CASES = {
    "炒菜用了8g油，但锅里还剩一些。": [],
    "炒菜用了8g油，但锅里还剩一些。 ": [("油", "8g油", "8g")],
    "炒菜用了8g油，但锅里还剩一些": [("油", "8g油", "8 g")],
    "我吃了6g低芥酸菜籽油。": [("低芥酸菜籽油", "6g低芥酸菜籽油", "6g")],
    "做菜用了9g菜籽油，这些油没吃，倒掉了。": [],
    "我吃了150g糙米饭、一个鸡蛋，炒菜用了8g油，但锅里还剩一些。": [
        ("糙米饭", "150g糙米饭", "150g"), ("鸡蛋", "一个鸡蛋", "一个"), ("油", "8g油", "8g"),
    ],
    "没有吃午饭。": [],
}


def recognition_fixture(_settings, *, contents, **_kwargs):
    description = json.loads(contents)["description"]
    cases = CONTEXT_CASES.get(description)
    if cases is None:
        case = CASES.get(description)
        if case is None:
            raise PlannerFailure
        cases = [case]
    return QuotedFoods(items=[
        QuotedFoodItem(name=name, evidence=evidence, portion_text=portion, preparation_method=None)
        for name, evidence, portion in cases
    ], needs_clarification=False)


food_recognition.generate_structured = recognition_fixture
def plan_fixture(**kwargs):
    request = json.loads(kwargs["contents"])
    if "模拟服务暂不可用" in request["user_request"]:
        raise errors.ServerError(503, {"error": {"message": "offline fixture"}})
    if "模拟失败" in request["user_request"]:
        return SimpleNamespace(text="{")
    data = [
        ("breakfast", "测试早餐炒蛋吐司", ("鸡蛋", "吐司"), 10),
        ("lunch", "测试午餐豆腐小白菜饭", ("豆腐", "小白菜", "米饭"), 15),
        ("dinner", "测试晚餐番茄鸡肉面", ("番茄", "鸡肉", "面条"), 18),
    ]
    if request["user_request"] == "帮我生成今天的一日三餐":
        data[1] = ("lunch", "测试香菇青菜焖饭", ("香菇", "小白菜", "大米"), 15)
        data[2] = ("dinner", "测试豆腐皮炒西葫芦", ("豆腐皮", "西葫芦"), 18)
    if request["user_request"] == "我只有番茄、鸡蛋和土豆，帮我规划一顿晚餐。":
        assert request["ingredient_mode"] == "flexible" and not request["available_ingredients"]
        data = [("dinner", "测试番茄鸡蛋土豆", ("番茄", "鸡蛋", "土豆"), 19)]
    if request.get("meal_type") == "dinner":
        data = [("dinner", "测试替换晚餐番茄豆腐饭", ("番茄", "豆腐", "米饭"), 14)]
    plan = {
        "title": "隔离测试餐单", "explanation": "测试提供方回包。",
        "meals": [
            {"meal_type": slot, "estimated_preparation_minutes": minutes, "dishes": [{
                "name": name, "ingredients": [{"name": item, "quantity": 80, "unit": "g"} for item in ingredients],
                "instructions": ["把食材做熟并装碗。"],
            }]}
            for slot, name, ingredients, minutes in data
        ],
    }
    return SimpleNamespace(text=json.dumps(plan, ensure_ascii=False))


fixture_client = MagicMock()
fixture_client.return_value.__enter__.return_value.models.generate_content.side_effect = plan_fixture
meal_plans.genai.Client = fixture_client
app = create_app(Settings(
    _env_file=None, GEMINI_API_KEY="offline-fixture", environment="development",
    catalog_planning_enabled=True, catalog_use_drafts=True, gemini_diagnostics=True,
))
