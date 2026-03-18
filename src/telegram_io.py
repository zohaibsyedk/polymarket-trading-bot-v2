import json
import urllib.parse
import urllib.request
from typing import List, Tuple


class TelegramIO:
    def __init__(self, token: str, default_chat_id: str = "", poll_timeout_s: int = 0):
        self.token = token
        self.default_chat_id = default_chat_id
        self.poll_timeout_s = poll_timeout_s
        self.offset = 0

    @property
    def enabled(self) -> bool:
        return bool(self.token)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self.token}/{method}"

    def send(self, text: str, chat_id: str | None = None) -> bool:
        if not self.enabled:
            return False
        target = chat_id or self.default_chat_id
        if not target:
            return False
        payload = urllib.parse.urlencode({"chat_id": target, "text": text})
        req = urllib.request.Request(self._url("sendMessage"), data=payload.encode("utf-8"))
        try:
            with urllib.request.urlopen(req, timeout=10) as _:
                return True
        except Exception:
            return False

    def poll_commands(self) -> List[Tuple[str, str]]:
        """Returns list of (chat_id, text)."""
        if not self.enabled:
            return []
        params = {
            "offset": self.offset,
            "timeout": self.poll_timeout_s,
            "allowed_updates": json.dumps(["message"]),
        }
        url = self._url("getUpdates") + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=max(10, self.poll_timeout_s + 2)) as r:
                body = json.loads(r.read().decode("utf-8"))
        except Exception:
            return []
        out: List[Tuple[str, str]] = []
        for upd in body.get("result", []):
            self.offset = max(self.offset, int(upd.get("update_id", 0)) + 1)
            msg = upd.get("message") or {}
            text = (msg.get("text") or "").strip()
            chat = msg.get("chat") or {}
            chat_id = str(chat.get("id", ""))
            if text:
                out.append((chat_id, text))
        return out
