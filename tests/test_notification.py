from graph.nodes import notification
from graph.state import Incident, IncidentState, Severity, Ticket
from tests.fakes import FakeSlackClient


def _state_with_one_critical():
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM crash", source_events=[])
    ticket = Ticket(
        incident_id="inc-001",
        ticket_id="MOCK-1001",
        url="https://example-jira.mock/browse/MOCK-1001",
        summary="OOM crash",
        description="d",
        labels=["oom"],
    )
    return IncidentState(raw_log="{}", incidents=[incident], tickets=[ticket], cookbook="# Incident Cookbook")


def test_notification_posts_summary_then_one_thread_reply_per_ticket():
    slack_client = FakeSlackClient(ts_sequence=["1000.0001", "1000.0002"])
    state = _state_with_one_critical()

    node = notification.run(slack_client)
    result = node(state)

    notif = result["notification_result"]
    assert notif.summary_message_id == "1000.0001"
    assert notif.thread_reply_ids == {"inc-001": "1000.0002"}
    assert slack_client.calls[1]["thread_ts"] == "1000.0001"


def test_notification_records_error_when_summary_post_fails():
    slack_client = FakeSlackClient(raise_on_call={0})
    state = _state_with_one_critical()

    node = notification.run(slack_client)
    result = node(state)

    notif = result["notification_result"]
    assert notif.summary_message_id is None
    assert notif.error is not None
