from pathlib import Path

from jules_tg_orchestrator.codex_cli import CodexCli


def test_build_chief_prompt_contains_telegram_message() -> None:
    prompt = CodexCli._build_prompt("Привет", user_id=1041149302, chat_id=1041149302)
    assert "chief Codex project orchestrator" in prompt
    assert "Prefer delegating implementation" in prompt
    assert "Привет" in prompt
    assert "1041149302" in prompt


def test_build_plan_prompt_is_approval_first() -> None:
    prompt = CodexCli._build_plan_prompt("Сделай задачу", user_id=1, chat_id=2)
    assert "Do not change files" in prompt
    assert "Which worker" in prompt
    assert "Exact prompt/task text" in prompt


def test_extracts_thread_id_from_jsonl() -> None:
    stdout = '{"type":"thread.started","thread_id":"019e3a7d-b5ef"}\n{"type":"turn.completed"}'
    assert CodexCli._extract_thread_id(stdout) == "019e3a7d-b5ef"


def test_resume_args_use_stored_session_id(tmp_path: Path) -> None:
    cli = CodexCli(command="codex", cwd=tmp_path)
    args = cli._build_exec_args(output_path=tmp_path / "out.txt", session_id="abc")
    cli._append_common_options(args)
    args.append("abc")
    args.append("-")
    assert Path(args[0]).name in {"codex", "codex.cmd"}
    assert args[1:3] == ["exec", "resume"]
    assert "abc" in args
    assert "--last" not in args
