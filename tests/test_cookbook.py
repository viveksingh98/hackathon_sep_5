from graph.nodes import cookbook
from graph.state import Incident, IncidentState, Remediation, Severity, Ticket


def test_cookbook_orders_incidents_by_severity_and_includes_fix_steps():
    incidents = [
        Incident(id="inc-med", category="latency_spike", severity=Severity.MEDIUM, summary="Latency spike", source_events=[]),
        Incident(id="inc-crit", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[]),
    ]
    remediations = [
        Remediation(incident_id="inc-crit", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="runbook"),
    ]
    tickets = [
        Ticket(incident_id="inc-crit", ticket_id="MOCK-1001", url="https://example-jira.mock/browse/MOCK-1001", summary="OOM crash", description="d", labels=["oom"]),
    ]
    state = IncidentState(raw_log="{}", incidents=incidents, remediations=remediations, tickets=tickets)

    node = cookbook.run()
    result = node(state)
    text = result["cookbook"]

    assert text.index("OOM crash") < text.index("Latency spike")
    assert "Restart pod" in text
    assert "MOCK-1001" in text


def test_cookbook_handles_no_incidents():
    state = IncidentState(raw_log="{}")

    node = cookbook.run()
    result = node(state)

    assert "# Incident Cookbook" in result["cookbook"]
