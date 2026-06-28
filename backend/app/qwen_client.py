from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import request


class QwenNotConfiguredError(RuntimeError):
    """Raised when Qwen configuration is missing."""


@dataclass
class QwenClient:
    api_key: str
    base_url: str
    model: str

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def chat(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not self.enabled:
            raise QwenNotConfiguredError("Qwen client is not configured.")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        req = request.Request(
            url=f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        # Ignore host proxy env vars so local broken proxy settings do not block Bailian.
        opener = request.build_opener(request.ProxyHandler({}))
        with opener.open(req, timeout=60) as response:
            body = json.loads(response.read().decode("utf-8"))
        return body

    def chat_json(self, system_prompt: str, user_prompt: str) -> Any:
        response = self.chat(system_prompt=system_prompt, user_prompt=user_prompt)
        content = self._extract_content(response)
        json_fragment = self._extract_json_fragment(content)
        return json.loads(json_fragment)

    @staticmethod
    def _extract_content(response: dict[str, Any]) -> str:
        choices = response.get("choices") or []
        if not choices:
            raise ValueError("Qwen response does not contain choices.")

        message = choices[0].get("message") or {}
        content = message.get("content", "")

        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text_parts.append(str(item.get("text", "")))
            return "\n".join(text_parts).strip()
        raise ValueError("Qwen response content has unsupported type.")

    @staticmethod
    def _extract_json_fragment(text: str) -> str:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fenced:
            return fenced.group(1).strip()

        for start_char, end_char in (("[", "]"), ("{", "}")):
            start = text.find(start_char)
            end = text.rfind(end_char)
            if start != -1 and end != -1 and end > start:
                return text[start : end + 1].strip()

        raise ValueError("Unable to extract JSON payload from Qwen response.")
