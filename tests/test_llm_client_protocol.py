from graph.state import Incident, LogEvent, Remediation, Severity
from tests.fakes import FakeLLMClient


def test_fake_llm_client_classify_returns_configured_incidents():
    incident = Incident(
        id="inc-001",
        category="oom",
        severity=Severity.CRITICAL,
        summary="OOM crash",
        source_events=[],
    )
    client = FakeLLMClient(classify_result=[incident])

    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_fake_llm_client_recommend_returns_configured_remediation():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod"],
        rationale="Known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    client = FakeLLMClient(recommend_result=remediation)
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])

    result = client.recommend(incident, {"fix_steps": ["Restart pod"]})

    assert result == remediation
