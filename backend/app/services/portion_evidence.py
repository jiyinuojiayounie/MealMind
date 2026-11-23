"""Conservative evidence checks shared by recognition and deterministic matching."""

import re
import unicodedata

from app.schemas.food_normalization import PortionIssue

UNKNOWN_CONSUMPTION = re.compile(
    r"\b(?:amount eaten unknown|(?:not sure|don't know) how much (?:i )?ate)\b|实际食用量未知|用量不详|不知道吃了多少"
)
_COOKING = re.compile(r"\b(?:in(?:to)? (?:the |a )?(?:pan|skillet|wok|pot)|used (?:to cook|for cooking))\b|下锅|锅中用量|倒(?:入|进)锅|(?:炒菜|做菜|烹[饪調]|烹调)\s*用(?:了)?")
_PURCHASE = re.compile(
    r"\b(?:bought|purchased|weighed before (?:trimming|peeling)|weighed during (?:meal )?prep)\b|"
    r"\b(?:prepared|prepped)\s+\d|买了|购入|(?:切配|备菜|备料)时称"
)
_REMAINING = re.compile(
    r"\b(?:left (?:some |a little )?behind|left over|remaining|discarded|threw away|didn['’]t finish)\b|没吃完|剩下|剩余|锅里(?:还)?剩|倒掉|丢掉"
)
_PARTIAL = re.compile(
    r"\b(?:ate only (?:some|part|half)|only ate (?:some|part|half)|shared with)\b|(?:只|仅)吃了(?:一点|部分|一半)|分给"
)
_INEDIBLE = re.compile(
    r"\b(?:bone-in|with (?:the )?bones?|shell-on|weighed (?:with|including) (?:the )?(?:skin|shell|peel|bones?)|"
    r"including (?:the )?(?:peel|shell|bones?))\b|带骨|连骨|含骨|带壳称|连壳|含壳称|连皮称|连皮一起称"
)
_MEAT_SKIN = re.compile(r"\bskin-on\b|带皮鸡|鸡[^，。;]{0,12}连皮")
_STATE_UNKNOWN = re.compile(
    r"\b(?:raw or cooked|cooked or raw|not sure (?:if|whether) (?:it was )?(?:raw|cooked))\b"
    r"|不知道(?:是)?生重还是熟重|不确定(?:是)?生重|忘了怎么做"
)
_RAW_WEIGHT = re.compile(r"\b(?:raw weight|weighed raw|weighed before cooking)\b|生重|烹调前称")
_COOKED_WEIGHT = re.compile(r"\b(?:cooked weight|weighed cooked|weighed after cooking)\b|熟重|烹调后称")
_COOKED_FOOD = re.compile(r"\b(?:cooked|roasted|boiled|stewed|grilled|baked|fried)\b|烤|水煮|炖|炒|蒸")


def portion_context_issue(text: str) -> PortionIssue | None:
    text = unicodedata.normalize("NFKC", text).casefold()
    for pattern, reason in (
        (UNKNOWN_CONSUMPTION, "consumed_amount_unknown"),
        (_REMAINING, "remaining_or_discarded"),
        (_PARTIAL, "partial_consumption"),
        (_COOKING, "cooking_input"),
        (_PURCHASE, "purchased_or_prepared"),
        (_INEDIBLE, "edible_basis_unclear"),
        (_MEAT_SKIN, "edible_basis_unclear"),
        (_STATE_UNKNOWN, "measurement_state_unclear"),
    ):
        if pattern.search(text):
            return reason
    if _RAW_WEIGHT.search(text) and (_COOKED_WEIGHT.search(text) or _COOKED_FOOD.search(text)):
        return "measurement_state_unclear"
    return None
