from graph.nodes import ticket
from graph.state import AgentError, Incident, IncidentState, Remediation, Severity


def _incident(id_, severity):
    return Incident(id=id_, category="oom", severity=severity, summary=f"Issue {id_}", source_events=[])


def test_ticket_creates_mock_ticket_only_for_critical_incidents():
    state = IncidentState(
        raw_log="{}",
        incidents=[
            _incident("inc-001", Severity.CRITICAL),
            _incident("inc-002", Severity.HIGH),
            _incident("inc-003", Severity.MEDIUM),
        ],
    )

    node = ticket.run()
    result = node(state)

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].incident_id == "inc-001"
    assert result["tickets"][0].ticket_id.startswith("MOCK-")
    assert "example-jira.mock" in result["tickets"][0].url


def test_ticket_includes_remediation_fix_steps_in_description_when_available():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod", "Add alert"],
        rationale="known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    state = IncidentState(
        raw_log="{}",
        incidents=[_incident("inc-001", Severity.CRITICAL)],
        remediations=[remediation],
    )

    node = ticket.run()
    result = node(state)

    description = result["tickets"][0].description
    assert "Restart pod" in description
    assert "Add alert" in description


def test_ticket_handles_critical_incident_with_no_remediation():
    state = IncidentState(raw_log="{}", incidents=[_incident("inc-001", Severity.CRITICAL)])

    node = ticket.run()
    result = node(state)

    assert len(result["tickets"]) == 1
    assert result["tickets"][0].description


def test_ticket_preserves_upstream_errors():
    state = IncidentState(
        raw_log="{}",
        incidents=[_incident("inc-001", Severity.CRITICAL)],
        errors=[AgentError(node="log_reader", message="earlier failure")],
    )

    result = ticket.run()(state)

    assert [e.node for e in result["errors"]] == ["log_reader"]


def test_ticket_records_error_instead_of_raising(monkeypatch):
    def _boom(**kwargs):
        raise RuntimeError("ticket construction exploded")

    monkeypatch.setattr(ticket, "Ticket", _boom)

    state = IncidentState(raw_log="{}", incidents=[_incident("inc-001", Severity.CRITICAL)])

    result = ticket.run()(state)

    assert result["tickets"] == []
    assert result["errors"][0].node == "ticket"
    assert "ticket construction exploded" in result["errors"][0].message
