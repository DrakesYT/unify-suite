"""Vultr Serverless Inference through its OpenAI-compatible API."""

import logging
import time

import httpx2
import openai
from openai.types.chat import ChatCompletionMessageParam

from app.config import LLM_MAX_TOKENS
from app.llm.base import LLMError, LLMOutputError, T, json_instructions, parse_json_output

logger = logging.getLogger(__name__)

CONNECT_RETRIES = 2  # immediate retries when the connection itself fails (not the reply)
CONNECT_RETRY_MIN_S = 1.0  # don't start a retry with less time than this left


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
        # Retries of timeouts and invalid replies are done by the agent runner, so they show up in
        # the task log; only a failed connection is retried here (see complete_json).
        self._client = openai.OpenAI(
            base_url=base_url, api_key=api_key, max_retries=0, http_client=http_client
        )

    def complete_json(self, schema: type[T], system: str, user: str, *, timeout_s: float) -> T:
        deadline = time.monotonic() + timeout_s
        log: dict[str, object] = {"model": self.model, "schema": schema.__name__}
        messages: list[ChatCompletionMessageParam] = [
            {"role": "system", "content": f"{system}\n\n{json_instructions(schema)}"},
            {"role": "user", "content": user},
        ]
        for connect_try in range(CONNECT_RETRIES + 1):
            started = time.monotonic()
            remaining = deadline - started
            try:
                response = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0,
                    max_tokens=LLM_MAX_TOKENS,
                    response_format={"type": "json_object"},
                    timeout=remaining,
                )
                break
            except openai.APITimeoutError as exc:  # a subclass of APIConnectionError: check first
                self._log(started, log, ok=False, error="timeout")
                raise LLMError(f"model timed out after {timeout_s:g} s") from exc
            except openai.APIConnectionError as exc:
                self._log(started, log, ok=False, error=type(exc).__name__)
                # A pooled keep-alive connection the server already closed fails at once; a fresh
                # connection usually works. Retry right away while the time budget allows, so a
                # stale connection never shows up as a failed agent task.
                out_of_time = deadline - time.monotonic() < CONNECT_RETRY_MIN_S
                if connect_try == CONNECT_RETRIES or out_of_time:
                    raise LLMError("could not reach the model API") from exc
            except openai.APIStatusError as exc:
                self._log(started, log, ok=False, error=f"http_{exc.status_code}")
                retryable = exc.status_code == 429 or exc.status_code >= 500
                raise LLMError(
                    f"model API returned {exc.status_code}", retryable=retryable
                ) from exc
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
