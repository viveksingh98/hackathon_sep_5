import json

from graph.build import build_graph
from graph.state import Incident, IncidentState, Remediation, Severity
from tests.fakes import FakeLLMClient, FakeSlackClient


def _make_llm_client():
    incidents = [
        Incident(id="inc-crit", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[]),
        Incident(id="inc-high", category="db_timeout", severity=Severity.HIGH, summary="DB timeout", source_events=[]),
    ]

    class SequencedClient(FakeLLMClient):
        def __init__(self):
            super().__init__(classify_result=incidents)
            self._remediations = {
                "inc-crit": Remediation(incident_id="inc-crit", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="runbook"),
                "inc-high": Remediation(incident_id="inc-high", fix_steps=["Check pool size"], rationale="r", risk="medium", effort="medium", source="runbook"),
            }

        def recommend(self, incident, runbook_entry):
            return self._remediations[incident.id]

    return SequencedClient()


def test_end_to_end_creates_ticket_only_for_critical_and_populates_cookbook():
    llm_client = _make_llm_client()
    slack_client = FakeSlackClient()
    graph = build_graph(llm_client, slack_client)

    raw_log = json.dumps([{"timestamp": "t", "service": "svc", "level": "ERROR", "message": "boom"}])
    result = graph.invoke(IncidentState(raw_log=raw_log))

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].incident_id == "inc-crit"
    assert "OOM crash" in result["cookbook"]
    assert "DB timeout" in result["cookbook"]
    assert result["notification_result"].summary_message_id is not None
    assert result["notification_result"].thread_reply_ids == {"inc-crit": result["notification_result"].thread_reply_ids["inc-crit"]}


def test_end_to_end_slack_failure_still_leaves_cookbook_populated():
    llm_client = _make_llm_client()
    slack_client = FakeSlackClient(raise_on_call={0})
    graph = build_graph(llm_client, slack_client)

    raw_log = json.dumps([{"timestamp": "t", "service": "svc", "level": "ERROR", "message": "boom"}])
    result = graph.invoke(IncidentState(raw_log=raw_log))

    assert result["notification_result"].error is not None
    assert "OOM crash" in result["cookbook"]
    assert len(result["tickets"]) == 1
