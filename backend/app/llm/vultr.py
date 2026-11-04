"""Vultr Serverless Inference through its OpenAI-compatible API."""

import logging
import time

import httpx2
import openai

from app.config import LLM_MAX_TOKENS
from app.llm.base import LLMError, LLMOutputError, T, json_instructions, parse_json_output

logger = logging.getLogger(__name__)


class VultrLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        http_client: httpx2.Client | None = None,  # tests pass a mock transport
    ) -> None:
        self.model = model
        # Retries are done by the agent runner, so they show up in the task log.
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key, max_retries=0, http_client=http_client
        )

    def complete_json(self, schema: type[T], system: str, user: str, *, timeout_s: float) -> T:
        started = time.monotonic()
        log: dict[str, object] = {"model": self.model, "schema": schema.__name__}
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": f"{system}\n\n{json_instructions(schema)}"},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                max_tokens=LLM_MAX_TOKENS,
                response_format={"type": "json_object"},
                timeout=timeout_s,
            )
        except openai.APITimeoutError as exc:
            self._log(started, log, ok=False, error="timeout")
            raise LLMError(f"model timed out after {timeout_s:g} s") from exc
        except openai.APIStatusError as exc:
            self._log(started, log, ok=False, error=f"http_{exc.status_code}")
            retryable = exc.status_code == 429 or exc.status_code >= 500
            raise LLMError(f"model API returned {exc.status_code}", retryable=retryable) from exc
        except openai.APIError as exc:
            self._log(started, log, ok=False, error=type(exc).__name__)
            raise LLMError("could not reach the model API") from exc

        if response.usage:
            log |= {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
        choice = response.choices[0]
        if choice.finish_reason == "length":
            self._log(started, log, ok=False, error="cut_off")
            raise LLMOutputError(f"reply was cut off at {LLM_MAX_TOKENS} tokens")
        try:
            result = parse_json_output(schema, choice.message.content)
        except LLMError:
            self._log(started, log, ok=False, error="invalid_output")
            raise
        self._log(started, log, ok=True)
        return result

    @staticmethod
    def _log(started: float, fields: dict[str, object], *, ok: bool, error: str = "") -> None:
        latency_ms = int((time.monotonic() - started) * 1000)
        extra = fields | {"latency_ms": latency_ms, "ok": ok} | ({"error": error} if error else {})
        logger.info("llm_call", extra=extra)
