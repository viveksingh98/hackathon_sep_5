from graph.state import Incident, LogEvent, Remediation


class FakeLLMClient:
    def __init__(self, classify_result=None, recommend_result=None):
        self._classify_result = classify_result if classify_result is not None else []
        self._recommend_result = recommend_result

    def classify(self, events: list[LogEvent]) -> list[Incident]:
        return self._classify_result

    def recommend(self, incident: Incident, runbook_entry) -> Remediation:
        if self._recommend_result is None:
            raise AssertionError("FakeLLMClient.recommend called without a configured recommend_result")
        return self._recommend_result


class FakeSlackClient:
    def __init__(self, ts_sequence=None, raise_on_call=None):
        self._ts_sequence = list(ts_sequence) if ts_sequence is not None else []
        self._raise_on_call = raise_on_call or set()
        self.calls = []

    def post_message(self, text, blocks=None, thread_ts=None):
        self.calls.append({"text": text, "blocks": blocks, "thread_ts": thread_ts})
        call_index = len(self.calls) - 1
        if call_index in self._raise_on_call:
            from integrations.slack import SlackError

            raise SlackError("mock_slack_failure")
        if self._ts_sequence:
            return self._ts_sequence.pop(0)
        return f"ts-{call_index}"
