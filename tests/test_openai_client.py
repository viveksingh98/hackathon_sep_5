from graph.state import Incident, LogEvent, Remediation, Severity
from llm import openai_client as mod
from llm.openai_client import OpenAIClient
from llm.client import ClassifyResult


class _FakeStructuredModel:
    def __init__(self, result):
        self._result = result

    def invoke(self, messages):
        return self._result


def _patch_chat_openai(monkeypatch, classify_result, recommend_result):
    monkeypatch.setattr(mod.ChatOpenAI, "__init__", lambda self, **kwargs: None)

    def fake_with_structured_output(self, schema):
        if schema is ClassifyResult:
            return _FakeStructuredModel(classify_result)
        return _FakeStructuredModel(recommend_result)

    monkeypatch.setattr(mod.ChatOpenAI, "with_structured_output", fake_with_structured_output)


def test_classify_returns_incidents_list(monkeypatch):
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    canned = ClassifyResult(incidents=[incident])
    _patch_chat_openai(monkeypatch, classify_result=canned, recommend_result=None)

    client = OpenAIClient(api_key="fake-key")
    result = client.classify([LogEvent(timestamp="t", service="s", level="ERROR", message="OOM")])

    assert result == [incident]


def test_recommend_returns_remediation_directly(monkeypatch):
    remediation = Remediation(incident_id="inc-001", fix_steps=["Restart pod"], rationale="r", risk="low", effort="low", source="llm")
    _patch_chat_openai(monkeypatch, classify_result=None, recommend_result=remediation)

    client = OpenAIClient(api_key="fake-key")
    incident = Incident(id="inc-001", category="oom", severity=Severity.CRITICAL, summary="OOM", source_events=[])
    result = client.recommend(incident, None)

    assert result == remediation
