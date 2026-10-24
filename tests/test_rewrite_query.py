from src.agent.rewrite import format_rewrite_result, rewrite_query


def test_rewrite_expands_nianjia():
    result = rewrite_query("年假几天")
    assert "年休假" in result["primary"]
    assert any("年假→年休假" in item for item in result["applied"])
    text = format_rewrite_result(result)
    assert "主查询：" in text
    assert "search_knowledge" in text


def test_rewrite_followup_needs_context():
    result = rewrite_query("这个和去年比呢？")
    assert result["needs_context"] is True
    assert result["original"] == "这个和去年比呢？"
    assert "结合上文主题" in result["primary"]


def test_rewrite_complete_query_keeps_text():
    q = "连续工作满1年不满10年的年休假有几天？"
    result = rewrite_query(q)
    assert result["primary"] == q or "年休假" in result["primary"]
    assert result["needs_context"] is False


def test_rewrite_empty():
    result = rewrite_query("  ")
    assert result["primary"] == ""
    assert format_rewrite_result(result)
