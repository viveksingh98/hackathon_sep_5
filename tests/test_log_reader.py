import json

from graph.nodes import log_reader
from graph.state import Incident, IncidentState, Severity
from tests.fakes import FakeLLMClient


def test_log_reader_parses_json_array_and_classifies():
    raw_log = json.dumps([
        {"timestamp": "t1", "service": "checkout-api", "level": "ERROR", "message": "OutOfMemoryError"},
    ])
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[])
    client = FakeLLMClient(classify_result=[incident])
    state = IncidentState(raw_log=raw_log)

    node = log_reader.run(client)
    result = node(state)

    assert len(result["parsed_events"]) == 1
    assert result["parsed_events"][0].service == "checkout-api"
    assert result["incidents"] == [incident]
    assert result["errors"] == []


def test_log_reader_recovers_partial_json_lines_and_records_error():
    raw_log = "\n".join([
        json.dumps({"timestamp": "t1", "service": "svc", "level": "INFO", "message": "ok"}),
        "not valid json",
        json.dumps({"timestamp": "t2", "service": "svc", "level": "ERROR", "message": "boom"}),
    ])
    client = FakeLLMClient(classify_result=[])
    state = IncidentState(raw_log=raw_log)

    node = log_reader.run(client)
    result = node(state)

    assert len(result["parsed_events"]) == 2
    assert len(result["errors"]) == 1
    assert "Dropped" in result["errors"][0].message


def test_log_reader_records_error_on_classify_failure():
    class RaisingClient:
        def classify(self, events):
            raise RuntimeError("model unavailable")

    state = IncidentState(raw_log=json.dumps([{"timestamp": "t", "service": "s", "level": "ERROR", "message": "m"}]))

    node = log_reader.run(RaisingClient())
    result = node(state)

    assert result["errors"][0].node == "log_reader"
    assert "model unavailable" in result["errors"][0].message
