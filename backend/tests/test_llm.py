import json
from decimal import Decimal

import httpx2 as httpx  # the HTTP library the OpenAI SDK uses
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.llm import LLMError, LLMOutputError
from app.llm.base import parse_json_output
from app.llm.fake import FakeLLMClient
from app.llm.vultr import VultrLLMClient
from app.money import to_minor


class Answer(BaseModel):
    label: str
    score: int


def _vultr(handler) -> tuple[VultrLLMClient, list[httpx.Request]]:  # type: ignore[no-untyped-def]
    seen: list[httpx.Request] = []

    def _record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = VultrLLMClient(
        base_url="https://llm.test/v1",
        api_key="test-key",
        model="test-model",
        http_client=httpx.Client(transport=httpx.MockTransport(_record)),
    )
    return client, seen


def _chat(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    )


def test_vultr_client_sends_json_mode_and_validates() -> None:
    client, seen = _vultr(lambda _r: _chat('{"label": "hot", "score": 3}'))

    result = client.complete_json(Answer, "system text", "user text", timeout_s=5)

    assert result == Answer(label="hot", score=3)
    body = json.loads(seen[0].content)
    assert body["model"] == "test-model"
    assert body["response_format"] == {"type": "json_object"}
    assert body["temperature"] == 0
    assert "JSON Schema" in body["messages"][0]["content"]
    assert body["messages"][1] == {"role": "user", "content": "user text"}
    assert seen[0].headers["Authorization"] == "Bearer test-key"


def test_vultr_client_rejects_output_that_breaks_the_schema() -> None:
    client, _ = _vultr(lambda _r: _chat('{"label": "hot"}'))

    with pytest.raises(LLMOutputError, match="score"):
        client.complete_json(Answer, "s", "u", timeout_s=5)


@pytest.mark.parametrize(("status", "retryable"), [(500, True), (429, True), (401, False)])
def test_vultr_client_http_errors(status: int, retryable: bool) -> None:
    client, _ = _vultr(lambda _r: httpx.Response(status, json={"error": {"message": "x"}}))

    with pytest.raises(LLMError) as exc:
        client.complete_json(Answer, "s", "u", timeout_s=5)
    assert exc.value.retryable is retryable
    assert "test-key" not in str(exc.value)


def test_vultr_client_timeout_is_retryable() -> None:
    def _timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    client, _ = _vultr(_timeout)

    with pytest.raises(LLMError, match="timed out") as exc:
        client.complete_json(Answer, "s", "u", timeout_s=5)
    assert exc.value.retryable


def test_fenced_json_is_accepted() -> None:
    assert parse_json_output(Answer, '```json\n{"label": "a", "score": 1}\n```').score == 1


def test_fake_client_replays_and_records() -> None:
    fake = FakeLLMClient(replies=[{"label": "a", "score": 1}, "not json"])

    assert fake.complete_json(Answer, "s", "u", timeout_s=1).label == "a"
    with pytest.raises(LLMOutputError):
        fake.complete_json(Answer, "s", "u", timeout_s=1)
    assert [c.schema for c in fake.calls] == ["Answer", "Answer"]


def test_missing_api_key_gives_503(client: TestClient, make_user, auth_header) -> None:  # type: ignore[no-untyped-def]
    from app.models.enums import Department, Role
    from tests.pdf import make_pdf

    user = make_user(Role.employee, Department.finance)
    res = client.post(
        "/api/finance/invoices/upload",
        headers=auth_header(user),
        files={"file": ("inv.pdf", make_pdf(["Invoice"]), "application/pdf")},
    )

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "llm_unavailable"


@pytest.mark.parametrize(
    ("amount", "currency", "minor"),
    [("4250.00", "USD", 425000), ("12.5", "EUR", 1250), ("1000", "JPY", 1000)],
)
def test_to_minor(amount: str, currency: str, minor: int) -> None:
    assert to_minor(Decimal(amount), currency) == minor


def test_to_minor_refuses_extra_decimals() -> None:
    with pytest.raises(ValueError):
        to_minor(Decimal("1.005"), "USD")


def test_cut_off_reply_is_reported_as_invalid_output() -> None:
    def _cut(_r: httpx.Request) -> httpx.Response:
        res = _chat('{"label": "ho')
        body = res.json()
        body["choices"][0]["finish_reason"] = "length"
        return httpx.Response(200, json=body)

    client, _ = _vultr(_cut)

    with pytest.raises(LLMOutputError, match="cut off"):
        client.complete_json(Answer, "s", "u", timeout_s=5)
