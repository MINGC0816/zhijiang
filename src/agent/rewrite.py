from __future__ import annotations

# 口语/简称 → 制度检索用语。Agent 先改写再检索，而不是把用户原话直接 embedding。
_ALIASES: tuple[tuple[str, str], ...] = (
    ("年假", "年休假"),
    ("年休", "年休假"),
    ("调休", "年休假 延期"),
    ("请假", "事假 病假 休假"),
    ("报销", "差旅 费用报销"),
    ("差旅费", "差旅 报销 住宿"),
    ("酒店", "住宿上限"),
    ("住宿", "住宿上限 差旅"),
    ("机票", "飞机 经济舱"),
    ("试用", "试用期 转正"),
    ("转正", "试用期结束 转正评估"),
    ("工牌", "入职当日 工牌 员工手册"),
    ("入职", "入职当日 劳动合同"),
    ("OA", "出差申请单 OA"),
)

_FOLLOWUP = ("呢", "那", "这个", "那个", "还有吗", "和去年", "相比", "刚才", "上面", "前面说")


def rewrite_query(question: str) -> dict:
    """把口语化问题展开成独立检索查询（不调用 LLM，结果可单测）。"""
    original = (question or "").strip()
    if not original:
        return {
            "original": "",
            "primary": "",
            "alternatives": [],
            "applied": [],
            "needs_context": False,
        }

    expanded = original
    applied: list[str] = []
    for src, dst in _ALIASES:
        if src in original and dst.split()[0] not in original:
            expanded = expanded.replace(src, f"{src} {dst}")
            applied.append(f"{src}→{dst}")

    alternatives = [original]
    if expanded != original:
        alternatives.append(expanded)

    needs_context = any(h in original for h in _FOLLOWUP) and len(original) <= 24
    if needs_context:
        contextual = f"{expanded} 结合上文主题 制度条款 是否变更"
        if contextual not in alternatives:
            alternatives.append(contextual)
    primary = alternatives[-1]
    return {
        "original": original,
        "primary": primary,
        "alternatives": alternatives,
        "applied": applied,
        "needs_context": needs_context,
    }


def format_rewrite_result(result: dict) -> str:
    if not result.get("primary"):
        return "问题为空，无法改写。"
    lines = [
        f"主查询：{result['primary']}",
        "备选：" + " | ".join(result.get("alternatives") or [result["primary"]]),
    ]
    if result.get("applied"):
        lines.append("已展开：" + "；".join(result["applied"]))
    if result.get("needs_context"):
        lines.append("提示：问法含指代/对比，请结合最近一轮对话补全省略成分后再检索。")
    lines.append("请用「主查询」调用 search_knowledge；若主查询召回为空，再试备选。")
    return "\n".join(lines)
