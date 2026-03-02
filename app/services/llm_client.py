from __future__ import annotations

from typing import List, Optional

from openai import AsyncOpenAI, APIError


class LLMClientError(RuntimeError):
    pass


class LLMClient:
    def __init__(
        self,
        provider: str,
        base_url: str,
        chat_path: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 15.0,
        referer: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        self._provider = provider
        self._base_url = base_url.rstrip("/")
        self._chat_path = chat_path
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds
        self._referer = referer
        self._title = title
        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=timeout_seconds
        )

    def _headers(self) -> dict:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        if self._title:
            headers["X-Title"] = self._title
        return headers

    async def generate(self, prompt: str, history: List[dict]) -> str:
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=history + [{"role": "user", "content": prompt}],
                temperature=0.4,
                top_p=0.9,
                max_tokens=200,
            )
        except APIError as exc:
            raise LLMClientError("LLM request failed") from exc

        try:
            return response.choices[0].message.content.strip()
        except (AttributeError, IndexError) as exc:
            raise LLMClientError("Unexpected LLM response format") from exc
