from graph.state import (
    Severity,
    LogEvent,
    Incident,
    Remediation,
    Ticket,
    NotificationResult,
    AgentError,
    IncidentState,
)


def test_incident_state_defaults_are_empty():
    state = IncidentState(raw_log="{}")
    assert state.parsed_events == []
    assert state.incidents == []
    assert state.remediations == []
    assert state.tickets == []
    assert state.cookbook == ""
    assert state.notification_result is None
    assert state.errors == []


def test_incident_state_instances_do_not_share_default_lists():
    a = IncidentState(raw_log="{}")
    b = IncidentState(raw_log="{}")
    a.errors.append(AgentError(node="x", message="y"))
    assert b.errors == []


def test_incident_requires_severity_enum_value():
    incident = Incident(
        id="inc-001",
        category="oom",
        severity=Severity.CRITICAL,
        summary="Out of memory",
        source_events=[LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")],
    )
    assert incident.severity == Severity.CRITICAL
    assert incident.severity.value == "critical"


def test_remediation_optional_fields_default_none():
    remediation = Remediation(
        incident_id="inc-001",
        fix_steps=["Restart pod"],
        rationale="Known fix",
        risk="low",
        effort="low",
        source="runbook",
    )
    assert remediation.confidence is None


def test_ticket_holds_mock_reference_fields():
    ticket = Ticket(
        incident_id="inc-001",
        ticket_id="MOCK-1001",
        url="https://example-jira.mock/browse/MOCK-1001",
        summary="Out of memory",
        description="...",
        labels=["auto-detected", "oom"],
    )
    assert ticket.ticket_id == "MOCK-1001"


def test_notification_result_defaults():
    result = NotificationResult()
    assert result.summary_message_id is None
    assert result.thread_reply_ids == {}
    assert result.error is None
