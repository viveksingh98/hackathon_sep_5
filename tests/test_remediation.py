import json

from graph.nodes import remediation
from graph.state import Incident, IncidentState, Remediation, Severity


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


def test_remediation_continues_after_failure_with_multiple_incidents():
    """Verify that per-incident failure isolation works with multiple incidents.

    With one incident, "continue on failure" and "abort on first failure"
    produce identical observable results. This test with two incidents
    (first fails, second succeeds) proves the node continues processing.
    """
    class PartialFailureClient:
        def recommend(self, incident, runbook_entry):
            if incident.id == "inc-001":
                raise RuntimeError("model timeout")
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Restart pod"],
                rationale="second incident succeeded",
                risk="low",
                effort="low",
                source="llm",
            )

    state = IncidentState(
        raw_log="{}",
        incidents=[
            Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[]),
            Incident(id="inc-002", category="cpu", severity=Severity.HIGH, summary="CPU spike", source_events=[]),
        ],
    )

    node = remediation.run(PartialFailureClient())
    result = node(state)

    # Should have exactly 1 remediation (from the second incident only)
    assert len(result["remediations"]) == 1
    assert result["remediations"][0].incident_id == "inc-002"

    # Should have exactly 1 error (from the first incident's failure)
    assert len(result["errors"]) == 1
    assert result["errors"][0].node == "remediation"
    assert "inc-001" in result["errors"][0].message
    assert "model timeout" in result["errors"][0].message


def test_remediation_overrides_hallucinated_incident_id_and_source():
    """The LLM never sees incident.id, so the node must not trust its self-report.

    The fake returns a Remediation pointing at a different incident and claiming
    source="llm" for a category that DOES have a runbook entry. The node must
    normalize both fields, otherwise the downstream
    ``{r.incident_id: r}`` joins in ticket.py / cookbook.py silently misattach.
    """

    class HallucinatingClient:
        def recommend(self, incident, runbook_entry):
            return Remediation(
                incident_id="inc-999-hallucinated",
                fix_steps=["Restart pod"],
                rationale="r",
                risk="low",
                effort="low",
                source="llm",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("oom")])

    node = remediation.run(HallucinatingClient())
    result = node(state)

    assert result["remediations"][0].incident_id == "inc-001"
    assert result["remediations"][0].source == "runbook"


def test_remediation_overrides_source_to_llm_for_unknown_category():
    """Mirror case: no runbook entry, but the LLM claims source="runbook"."""

    class HallucinatingClient:
        def recommend(self, incident, runbook_entry):
            return Remediation(
                incident_id="inc-999-hallucinated",
                fix_steps=["Investigate"],
                rationale="r",
                risk="unknown",
                effort="unknown",
                source="runbook",
            )

    state = IncidentState(raw_log="{}", incidents=[_incident("mystery_category")])

    node = remediation.run(HallucinatingClient())
    result = node(state)

    assert result["remediations"][0].incident_id == "inc-001"
    assert result["remediations"][0].source == "llm"


def test_load_runbook_returns_empty_dict_on_malformed_json(monkeypatch):
    monkeypatch.setattr(
        remediation._RUNBOOK_PATH.__class__, "read_text", lambda self, *a, **k: "{not valid json"
    )

    assert remediation._load_runbook() == {}


def test_load_runbook_returns_empty_dict_when_json_is_not_an_object(monkeypatch):
    monkeypatch.setattr(
        remediation._RUNBOOK_PATH.__class__, "read_text", lambda self, *a, **k: json.dumps([1, 2, 3])
    )

    assert remediation._load_runbook() == {}


def test_remediation_node_still_runs_with_corrupt_runbook(monkeypatch):
    """A corrupt runbook must degrade to source="llm", not crash build_graph()."""
    monkeypatch.setattr(
        remediation._RUNBOOK_PATH.__class__, "read_text", lambda self, *a, **k: "{not valid json"
    )

    class RecordingClient:
        def recommend(self, incident, runbook_entry):
            assert runbook_entry is None
            return Remediation(
                incident_id=incident.id,
                fix_steps=["Investigate"],
                rationale="r",
                risk="low",
                effort="low",
                source="runbook",
            )

    node = remediation.run(RecordingClient())
    result = node(IncidentState(raw_log="{}", incidents=[_incident("oom")]))

    assert result["remediations"][0].source == "llm"
