from jules_tg_orchestrator.gemini_cli import GeminiCli


def test_extracts_json_response_with_terminal_warning() -> None:
    output = '{"response":"OK","stats":{}}\nWarning: 256-color support not detected.'
    assert GeminiCli._extract_response(output) == "OK"


def test_extract_response_falls_back_to_plain_text() -> None:
    assert GeminiCli._extract_response("plain output") == "plain output"
