from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class LogEvent(BaseModel):
    timestamp: str
    service: str
    level: str
    message: str
    context: Optional[str] = None


class Incident(BaseModel):
    id: str
    category: str
    severity: Severity
    summary: str
    source_events: list[LogEvent] = Field(default_factory=list)


class Remediation(BaseModel):
    incident_id: str
    fix_steps: list[str]
    rationale: str
    risk: str
    effort: str
    source: str
    confidence: Optional[float] = None


class Ticket(BaseModel):
    incident_id: str
    ticket_id: str
    url: str
    summary: str
    description: str
    labels: list[str] = Field(default_factory=list)


class NotificationResult(BaseModel):
    summary_message_id: Optional[str] = None
    thread_reply_ids: dict[str, str] = Field(default_factory=dict)
    error: Optional[str] = None


class AgentError(BaseModel):
    node: str
    message: str


class IncidentState(BaseModel):
    raw_log: str
    parsed_events: list[LogEvent] = Field(default_factory=list)
    incidents: list[Incident] = Field(default_factory=list)
    remediations: list[Remediation] = Field(default_factory=list)
    tickets: list[Ticket] = Field(default_factory=list)
    cookbook: str = ""
    notification_result: Optional[NotificationResult] = None
    errors: list[AgentError] = Field(default_factory=list)
