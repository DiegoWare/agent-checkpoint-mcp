import json

from agent_checkpoint_mcp.transcript import extract_snapshot


def _write_jsonl(path, entries):
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")


def _assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def _assistant_todos(todos):
    return {
        "type": "assistant",
        "message": {
            "content": [{"type": "tool_use", "name": "TodoWrite", "input": {"todos": todos}}]
        },
    }


def test_snapshot_from_todos(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(
        transcript,
        [
            {"type": "user", "message": {"content": "do the thing"}},
            _assistant_todos(
                [
                    {"content": "Set up schema", "status": "completed"},
                    {"content": "Write endpoints", "status": "in_progress"},
                    {"content": "Add tests", "status": "pending"},
                ]
            ),
            _assistant_text("Finished the schema, now writing the POST endpoint."),
        ],
    )
    snap = extract_snapshot(transcript)
    assert snap["total_steps"] == 3
    assert snap["current_step"] == 2
    assert snap["step_status"] == "in_progress"
    assert "Set up schema" in snap["what_was_done"]
    assert "Write endpoints" in snap["what_remains"]
    assert "POST endpoint" in snap["what_remains"]


def test_snapshot_uses_last_todo_state(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(
        transcript,
        [
            _assistant_todos([{"content": "Step A", "status": "in_progress"}]),
            _assistant_todos([{"content": "Step A", "status": "completed"}]),
        ],
    )
    snap = extract_snapshot(transcript)
    assert snap["step_status"] == "done"
    assert snap["current_step"] == snap["total_steps"] == 1


def test_snapshot_without_todos_falls_back_to_text(tmp_path):
    transcript = tmp_path / "t.jsonl"
    _write_jsonl(transcript, [_assistant_text("I edited auth.py and ran the tests.")])
    snap = extract_snapshot(transcript)
    assert snap["total_steps"] == 1
    assert "auth.py" in snap["what_remains"]


def test_snapshot_empty_or_missing(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("", encoding="utf-8")
    assert extract_snapshot(empty) is None
    assert extract_snapshot(tmp_path / "missing.jsonl") is None


def test_snapshot_skips_malformed_lines(tmp_path):
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        "not json\n" + json.dumps(_assistant_text("still recovered")) + "\n",
        encoding="utf-8",
    )
    snap = extract_snapshot(transcript)
    assert "still recovered" in snap["what_remains"]
