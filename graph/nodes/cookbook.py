from typing import Callable

from graph.state import IncidentState, Severity

_SEVERITY_ORDER = [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM, Severity.LOW]


def run() -> Callable[[IncidentState], dict]:
    def _node(state: IncidentState) -> dict:
        remediation_by_incident = {r.incident_id: r for r in state.remediations}
        ticket_by_incident = {t.incident_id: t for t in state.tickets}

        lines = ["# Incident Cookbook", ""]
        for severity in _SEVERITY_ORDER:
            incidents = [i for i in state.incidents if i.severity == severity]
            if not incidents:
                continue

            lines.append(f"## {severity.value.title()}")
            lines.append("")
            for incident in incidents:
                lines.append(f"### {incident.summary}")
                remediation = remediation_by_incident.get(incident.id)
                if remediation:
                    for step in remediation.fix_steps:
                        lines.append(f"- [ ] {step}")
                    lines.append(f"- Risk: {remediation.risk} · Effort: {remediation.effort}")
                ticket = ticket_by_incident.get(incident.id)
                if ticket:
                    lines.append(f"- Ticket: [{ticket.ticket_id}]({ticket.url})")
                lines.append("")

        return {"cookbook": "\n".join(lines)}

    return _node
