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


def test_notification_records_error_when_per_ticket_reply_fails():
    # Summary post succeeds (call 0), per-ticket reply fails (call 1)
    slack_client = FakeSlackClient(ts_sequence=["1000.0001"], raise_on_call={1})
    state = _state_with_one_critical()

    node = notification.run(slack_client)
    result = node(state)

    notif = result["notification_result"]
    assert notif.summary_message_id == "1000.0001"
    # Per-ticket failure is marked as error in thread_reply_ids
    assert notif.thread_reply_ids["inc-001"].startswith("error:")
    # But NotificationResult.error should now capture the failure
    assert notif.error is not None
    assert "Thread reply failed for: inc-001" in notif.error


def test_notification_catches_non_slack_exceptions():
    # Create a custom fake client that raises a non-SlackError exception
    class FailingSlackClient:
        def post_message(self, text, blocks=None, thread_ts=None):
            raise RuntimeError("connection timeout")

    failing_client = FailingSlackClient()
    state = _state_with_one_critical()

    node = notification.run(failing_client)
    result = node(state)

    # Should not raise; should return with error set
    notif = result["notification_result"]
    assert notif.error is not None
    assert "connection timeout" in notif.error
