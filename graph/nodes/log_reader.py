import json
from typing import Callable

from graph.state import AgentError, IncidentState, LogEvent


def run(llm_client) -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        errors = list(state.errors)

        try:
            events, dropped = _parse_log(state.raw_log)
            if dropped:
                errors.append(AgentError(node="log_reader", message=f"Dropped {dropped} unparseable log line(s)"))
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            errors.append(AgentError(node="log_reader", message=str(exc)))
            return {"parsed_events": [], "incidents": [], "errors": errors}

        try:
            incidents = llm_client.classify(events)
        except Exception as exc:  # noqa: BLE001 - node boundary must not raise
            errors.append(AgentError(node="log_reader", message=str(exc)))
            return {"parsed_events": events, "incidents": [], "errors": errors}

        return {"parsed_events": events, "incidents": incidents, "errors": errors}

    return _node


def _parse_log(raw_log: str) -> tuple[list[LogEvent], int]:
    raw_log = raw_log.strip()
    dropped = 0
    records: list[dict] = []

    try:
        parsed = json.loads(raw_log)
        if isinstance(parsed, list):
            records = parsed
        elif isinstance(parsed, dict):
            records = [parsed]
        else:
            raise ValueError("log content is not a JSON object or array")
    except (json.JSONDecodeError, ValueError):
        for line in raw_log.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                dropped += 1

    events: list[LogEvent] = []
    for record in records:
        try:
            raw_context = record.get("context")
            events.append(
                LogEvent(
                    timestamp=str(record.get("timestamp", "")),
                    service=str(record.get("service", "unknown")),
                    level=str(record.get("level", "info")),
                    message=str(record.get("message", "")),
                    # Coerced like its siblings so a structured context (dict/list)
                    # doesn't fail validation and silently drop the whole event.
                    context=str(raw_context) if raw_context is not None else None,
                )
            )
        except Exception:  # noqa: BLE001 - malformed record, count and skip
            dropped += 1

    return events, dropped
