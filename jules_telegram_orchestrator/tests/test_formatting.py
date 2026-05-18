from jules_tg_orchestrator.formatting import format_activity, split_message


def test_split_message_chunks_long_text() -> None:
    chunks = split_message("x" * 5000, limit=1000)
    assert len(chunks) == 5
    assert all(len(chunk) <= 1000 for chunk in chunks)


def test_format_plan_activity() -> None:
    text = format_activity(
        {
            "description": "Plan generated",
            "planGenerated": {
                "plan": {
                    "steps": [
                        {"index": 0, "title": "Inspect code", "description": "Find relevant files"},
                        {"index": 1, "title": "Patch tests", "description": "Add focused coverage"},
                    ]
                }
            },
        }
    )
    assert "Inspect code" in text
    assert "Patch tests" in text
