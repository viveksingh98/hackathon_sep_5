import json
from pathlib import Path

from graph.nodes.log_reader import _parse_log

_FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


def test_sample_oom_parses_with_no_dropped_lines():
    raw_log = (_FIXTURES_DIR / "sample_oom.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 3
    assert any("OutOfMemory" in e.message or "OOM" in e.message for e in events)


def test_sample_db_timeout_parses_with_no_dropped_lines():
    raw_log = (_FIXTURES_DIR / "sample_db_timeout.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 2


def test_sample_mixed_severity_contains_multiple_services_or_messages():
    raw_log = (_FIXTURES_DIR / "sample_mixed_severity.json").read_text()
    events, dropped = _parse_log(raw_log)
    assert dropped == 0
    assert len(events) >= 5
    levels = {e.level for e in events}
    assert "ERROR" in levels or "FATAL" in levels
    assert "INFO" in levels
