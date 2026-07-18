import json
import re

import requests


class WooCommerceApiClient:
    def __init__(self, *, auth: tuple[str, str], timeout_seconds: int) -> None:
        self.auth = auth
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def sanitize_error_text(value: str) -> str:
        text = str(value or "")
        if not text:
            return text
        text = re.sub(r"([?&]consumer_key=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"([?&]consumer_secret=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"(consumer_key=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        text = re.sub(r"(consumer_secret=)[^&\s]+", r"\1***", text, flags=re.IGNORECASE)
        return text

    @staticmethod
    def build_readable_error_detail(response: requests.Response | None) -> str:
        if response is None:
            return ""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                code = str(payload.get("code", "")).strip()
                message = str(payload.get("message", "")).strip()
                data = payload.get("data")
                data_text = json.dumps(data, ensure_ascii=False) if data is not None else ""
                parts = [part for part in [code, message, data_text] if part]
                return WooCommerceApiClient.sanitize_error_text(" | ".join(parts))
            return WooCommerceApiClient.sanitize_error_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            return WooCommerceApiClient.sanitize_error_text((response.text or "").strip())

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        params = kwargs.pop("params", {}) or {}
        response = requests.request(
            method=method,
            url=url,
            params=params,
            auth=self.auth,
            timeout=self.timeout_seconds,
            **kwargs,
        )
        response.raise_for_status()
        return response