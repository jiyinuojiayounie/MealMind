"""Opt-in single-provider smoke probe. Uses a fixed synthetic request and no storage."""

import argparse
import json

from app.core.settings import Settings
from app.schemas.meal_plans import MealPlanRequest
from app.services.meal_plans import PlannerFailure, PlannerTimeout, PlannerUnavailable, generate_meal_plan

SMOKE_REQUEST = (
    "帮我安排明天的一日三餐。我一个人做饭，偏爱中式家常菜，想吃得健康但也要好吃。"
    "早餐最好10分钟以内，中饭和晚饭各20分钟以内，食材要常见，尽量少洗锅，不要推荐重复的菜。"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Authorize exactly one Gemini attempt with the fixed sample.")
    parser.add_argument("--show", action="store_true", help="Print the synthetic rendered prompt and returned raw response.")
    args = parser.parse_args()
    if not args.live:
        parser.error("Use --live to explicitly authorize the one-request smoke test.")
    settings = Settings()
    trace = {"model": settings.gemini_model}
    capture = {} if args.show else None
    try:
        generate_meal_plan(
            MealPlanRequest(user_request=SMOKE_REQUEST, scope="single_meal", language="zh-CN", ingredient_mode="flexible"),
            settings, infer_scope=True, trace=trace, fixture_capture=capture,
        )
    except (PlannerFailure, PlannerTimeout, PlannerUnavailable):
        return 1
    finally:
        print(json.dumps({"trace": trace, **({"fixture": capture} if capture is not None else {})}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
