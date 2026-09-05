from graph.state import Incident, LogEvent, Remediation, Severity
from llm import anthropic_client as mod
from llm.anthropic_client import AnthropicClient
from llm.client import ClassifyResult


class _FakeStructuredModel:
    def __init__(self, result):
        self._result = result
        self.captured_messages = None

    def invoke(self, messages):
        self.captured_messages = messages
        return self._result


def _patch_chat_anthropic(monkeypatch, classify_result, recommend_result):
    """Patch ChatAnthropic and return the two fake structured models, so tests can
    assert on the prompt that was actually sent (not just the canned return)."""
    monkeypatch.setattr(mod.ChatAnthropic, "__init__", lambda self, **kwargs: None)

    fakes = {"classify": _FakeStructuredModel(classify_result), "recommend": _FakeStructuredModel(recommend_result)}

    def fake_with_structured_output(self, schema):
        if schema is ClassifyResult:
            return fakes["classify"]
        return fakes["recommend"]

    monkeypatch.setattr(mod.ChatAnthropic, "with_structured_output", fake_with_structured_output)
    return fakes


def _prompt_text(messages) -> str:
    return "\n".join(content for _role, content in messages)


def test_classify_returns_incidents_list(monkeypatch):
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    canned = ClassifyResult(incidents=[incident])
    _patch_chat_anthropic(monkeypatch, classify_result=canned, recommend_result=None)

    client = AnthropicClient(api_key="fake-key")
    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_classify_prompt_contains_every_event_message(monkeypatch):
    canned = ClassifyResult(incidents=[])
    fakes = _patch_chat_anthropic(monkeypatch, classify_result=canned, recommend_result=None)

    events = [
        LogEvent(timestamp="t1", service="checkout-api", level="ERROR", message="OutOfMemoryError: heap"),
        LogEvent(timestamp="t2", service="db-proxy", level="WARN", message="connection pool exhausted", context="trace-123"),
    ]

    AnthropicClient(api_key="fake-key").classify(events)

    prompt = _prompt_text(fakes["classify"].captured_messages)
    for event in events:
        assert event.message in prompt
        assert event.service in prompt
        assert event.timestamp in prompt
    assert "trace-123" in prompt


def test_recommend_returns_remediation_directly(monkeypatch):
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    _patch_chat_anthropic(monkeypatch, classify_result=None, recommend_result=remediation)

    client = AnthropicClient(api_key="fake-key")
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    result = client.recommend(incident, None)

    assert result == remediation


def test_recommend_prompt_contains_incident_summary_category_and_severity(monkeypatch):
    """Pins the CURRENT contents of _incident_to_prompt.

    Note: the prompt deliberately does NOT carry incident.id — the remediation
    node overrides incident_id after the call instead (see graph/nodes/remediation.py).
    """
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    fakes = _patch_chat_anthropic(monkeypatch, classify_result=None, recommend_result=remediation)

    incident = Incident(
        id="inc-042", category="db_timeout", severity=Severity.HIGH, summary="Postgres connections timing out", source_events=[]
    )
    AnthropicClient(api_key="fake-key").recommend(incident, {"fix_steps": ["Raise pool size"], "risk": "low"})

    prompt = _prompt_text(fakes["recommend"].captured_messages)
    assert incident.summary in prompt
    assert incident.category in prompt
    assert incident.severity.value in prompt
    assert "Raise pool size" in prompt


def test_recommend_prompt_omits_runbook_section_when_no_entry(monkeypatch):
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    fakes = _patch_chat_anthropic(monkeypatch, classify_result=None, recommend_result=remediation)

    incident = Incident(id="inc-001", category="other", severity=Severity.LOW, summary="Odd log", source_events=[])
    AnthropicClient(api_key="fake-key").recommend(incident, None)

    prompt = _prompt_text(fakes["recommend"].captured_messages)
    assert "Known runbook entry" not in prompt
