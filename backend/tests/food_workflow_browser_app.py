"""Isolated Chrome fixture app. Start only from the browser regression runner."""

import json

from app.core.settings import Settings
from app.main import create_app
from app.schemas.food_recognition import QuotedFoodItem, QuotedFoods
from app.services import food_recognition
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
app = create_app(Settings(_env_file=None, GEMINI_API_KEY="", environment="development"))
