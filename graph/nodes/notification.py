from typing import Callable

from graph.state import IncidentState, NotificationResult
from integrations.slack import SlackError


def run(slack_client) -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        try:
            summary_ts = slack_client.post_message(text="Incident analysis complete", blocks=_summary_blocks(state))
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            return {"notification_result": NotificationResult(error=str(exc))}

        thread_reply_ids = {}
        failed_incident_ids = []
        for ticket in state.tickets:
            try:
                reply_ts = slack_client.post_message(
                    text=f"Critical incident ticket: {ticket.ticket_id} — {ticket.url}",
                    thread_ts=summary_ts,
                )
                thread_reply_ids[ticket.incident_id] = reply_ts
            except Exception as exc:  # noqa: BLE001 - node boundary must not raise
                thread_reply_ids[ticket.incident_id] = f"error: {exc}"
                failed_incident_ids.append(ticket.incident_id)

        error_msg = None
        if failed_incident_ids:
            error_msg = f"Thread reply failed for: {', '.join(failed_incident_ids)}"

        return {
            "notification_result": NotificationResult(
                summary_message_id=summary_ts,
                thread_reply_ids=thread_reply_ids,
                error=error_msg,
            )
        }

    return _node


def _summary_blocks(state: IncidentState) -> list:
    counts: dict[str, int] = {}
    for incident in state.incidents:
        counts[incident.severity.value] = counts.get(incident.severity.value, 0) + 1
    summary_line = ", ".join(f"{count} {severity}" for severity, count in counts.items()) or "no incidents found"

    return [
        {"type": "header", "text": {"type": "plain_text", "text": "Incident Analysis Complete"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Detected:* {summary_line}"}},
        {"type": "section", "text": {"type": "mrkdwn", "text": state.cookbook[:2900]}},
    ]
