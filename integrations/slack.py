from typing import Optional

import requests

_SLACK_API_URL = "https://slack.com/api/chat.postMessage"


class SlackError(Exception):
    pass


class SlackClient:
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id

    def post_message(self, text: str, blocks: Optional[list] = None, thread_ts: Optional[str] = None) -> str:
        payload = {"channel": self.channel_id, "text": text}
        if blocks is not None:
            payload["blocks"] = blocks
        if thread_ts is not None:
            payload["thread_ts"] = thread_ts

        response = requests.post(
            _SLACK_API_URL,
            headers={"Authorization": f"Bearer {self.bot_token}"},
            json=payload,
            timeout=10,
        )
        data = response.json()
        if not data.get("ok"):
            raise SlackError(data.get("error", "unknown_slack_error"))
        return data["ts"]


class NoOpSlackClient:
    """Used when Slack credentials are omitted so the rest of the pipeline can still run."""

    def post_message(self, text: str, blocks: Optional[list] = None, thread_ts: Optional[str] = None) -> str:
        return "slack-skipped"
