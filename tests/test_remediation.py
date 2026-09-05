from graph.nodes import remediation
from graph.state import Incident, IncidentState, Remediation, Severity
from tests.fakes import FakeLLMClient


def _incident(category="oom"):
    return Incident(id="inc-001", category=category, severity=Severity.CRITICAL, summary="OOM crash", source_events=[])


def test_remediation_calls_llm_with_runbook_entry_for_known_category():
    seen = {}

    class RecordingClient:
        def recommend(self, incident, runbook_entry):
            seen["runbook_entry"] = runbook_entry
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Restart pod"],
                rationale="known fix",
                risk="low",
                effort="low",
                source="runbook",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("oom")])

    node = remediation.run(RecordingClient())
    result = node(state)

    assert seen["runbook_entry"] is not None
    assert "fix_steps" in seen["runbook_entry"]
    assert result["remediations"][0].source == "runbook"


def test_remediation_passes_none_runbook_entry_for_unknown_category():
    seen = {}

    class RecordingClient:
        def recommend(self, incident, runbook_entry):
            seen["runbook_entry"] = runbook_entry
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Investigate"],
                rationale="general reasoning",
                risk="unknown",
                effort="unknown",
                source="llm",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("mystery_category")])

    node = remediation.run(RecordingClient())
    result = node(state)

    assert seen["runbook_entry"] is None
    assert result["remediations"][0].source == "llm"


def test_remediation_records_error_and_continues_on_failure():
    class RaisingClient:
        def recommend(self, incident, runbook_entry):
            raise RuntimeError("model timeout")

    state = IncidentState(raw_log="{}", incidents=[_incident("oom")])

    node = remediation.run(RaisingClient())
    result = node(state)

    assert result["remediations"] == []
    assert result["errors"][0].node == "remediation"
    assert "model timeout" in result["errors"][0].message
