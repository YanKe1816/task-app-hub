import json
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from server import APP_SLUG, OUTPUT_SCHEMA, TOOL_NAME, app


EXPECTED_OUTPUT_KEYS = set(OUTPUT_SCHEMA["required"])


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def mcp(client, method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = client.post(f"/{APP_SLUG}/mcp", json=payload)
    assert response.status_code == 200
    return response.get_json()


def assert_structured_output(value):
    assert set(value.keys()) == EXPECTED_OUTPUT_KEYS
    assert value["status"] in {"success", "error"}
    assert value["urgency_label"] in {"low", "medium", "high", "unknown"}
    assert isinstance(value["missing_fields"], list)
    assert isinstance(value["source_text"], str)
    assert isinstance(value["errors"], list)
    for error in value["errors"]:
        assert set(error.keys()) == {"code", "message"}


def test_server_starts():
    process = subprocess.Popen(
        [sys.executable, "server.py"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 5
        last_error = None
        while time.time() < deadline:
            try:
                with urlopen("http://127.0.0.1:8000/health", timeout=0.5) as response:
                    assert response.status == 200
                    assert json.loads(response.read().decode("utf-8"))["status"] == "ok"
                    return
            except Exception as exc:
                last_error = exc
                time.sleep(0.1)
        pytest.fail(f"server did not start: {last_error}")
    finally:
        process.terminate()
        process.wait(timeout=5)


def test_health_works(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_landing_page_review_shell(client):
    response = client.get(f"/{APP_SLUG}")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "Customer Refund Request Extractor" in body
    assert "This app does not approve refunds." in body
    assert "sidcraigau@gmail.com" in body


def test_privacy_page_review_shell(client):
    response = client.get(f"/{APP_SLUG}/privacy")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "applies only to Customer Refund Request Extractor" in body
    assert "No login required." in body
    assert "No long-term storage" in body
    assert "No external API access." in body


def test_terms_page_review_shell(client):
    response = client.get(f"/{APP_SLUG}/terms")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "does not decide refund eligibility" in body
    assert "does not modify order records" in body


def test_support_page_review_shell(client):
    response = client.get(f"/{APP_SLUG}/support")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "Support page for Customer Refund Request Extractor" in body
    assert "sidcraigau@gmail.com" in body


def test_openai_apps_challenge_uses_env_value_exactly(client, monkeypatch):
    monkeypatch.setenv("OPENAI_APPS_CHALLENGE", "challenge-token-123")
    response = client.get("/.well-known/openai-apps-challenge")
    assert response.status_code == 200
    assert response.content_type == "text/plain; charset=utf-8"
    assert response.get_data(as_text=True) == "challenge-token-123"


def test_openai_apps_challenge_fallback(client, monkeypatch):
    monkeypatch.delenv("OPENAI_APPS_CHALLENGE", raising=False)
    response = client.get("/.well-known/openai-apps-challenge")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "openai-apps-challenge-not-configured"


def test_initialize_contract(client):
    data = mcp(client, "initialize")
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == APP_SLUG
    assert result["serverInfo"]["version"] == "0.1.0"
    assert "tools" in result["capabilities"]


def test_tools_list_single_tool_contract(client):
    data = mcp(client, "tools/list")
    tools = data["result"]["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == TOOL_NAME
    assert tool["title"] == "Customer Refund Request Extractor"
    assert tool["description"]
    assert tool["inputSchema"]["required"] == ["source_text"]
    assert tool["outputSchema"] == OUTPUT_SCHEMA
    assert tool["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }


def test_generic_mcp_absent(client):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/support"])
def test_generic_review_shell_routes_absent(client, path):
    response = client.get(path)
    assert response.status_code == 404


def test_tools_call_complete_refund_message(client):
    source_text = (
        "Customer requests a refund. Order ID: RF12345. Product name: Travel Mug. "
        "Refund reason: arrived cracked. Please refund this order ASAP."
    )
    data = mcp(
        client,
        "tools/call",
        {"name": TOOL_NAME, "arguments": {"source_text": source_text}},
    )
    result = data["result"]
    assert "structuredContent" in result
    structured = result["structuredContent"]
    assert_structured_output(structured)
    assert structured["status"] == "success"
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] == "Travel Mug"
    assert structured["refund_reason"] == "arrived cracked"
    assert structured["customer_request"] == "refund"
    assert structured["urgency_label"] == "high"
    assert structured["missing_fields"] == []
    assert structured["source_text"] == source_text
    assert structured["errors"] == []


def test_tools_call_extracts_order_and_arrival_condition_reason(client):
    source_text = (
        "I want a refund for order RF12345. The product is a Travel Mug. "
        "It arrived cracked, and I need this handled ASAP."
    )
    data = mcp(
        client,
        "tools/call",
        {"name": TOOL_NAME, "arguments": {"source_text": source_text}},
    )
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["status"] == "success"
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] == "Travel Mug"
    assert structured["refund_reason"] == "arrived cracked"
    assert structured["customer_request"] == "refund"
    assert structured["urgency_label"] == "high"
    assert structured["missing_fields"] == []
    assert structured["source_text"] == source_text
    assert structured["errors"] == []


def test_missing_source_text_error(client):
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["status"] == "error"
    assert structured["errors"] == [{"code": "missing_field", "message": "source_text is required."}]


def test_empty_source_text_error(client):
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": "  "}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["status"] == "error"
    assert structured["errors"][0]["code"] == "invalid_value"


@pytest.mark.parametrize(
    "text",
    [
        "Should I approve this refund for order RF12345?",
        "Should we approve a refund for order RF12345?",
        "Write a reply to this angry refund customer.",
        "Please modify the order before processing the refund.",
        "Change order A1023 to refunded.",
        "Mark order A1023 as refunded.",
        "Create an internal note saying order A1023 was refunded.",
    ],
)
def test_out_of_scope_errors(client, text):
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["status"] == "error"
    assert structured["errors"][0]["code"] == "out_of_scope"


def test_repeated_calls_are_stable(client):
    params = {
        "name": TOOL_NAME,
        "arguments": {
            "source_text": "Order ID: ABC999. Product: Headphones. Reason: battery failed. I want a refund."
        },
    }
    first = mcp(client, "tools/call", params, request_id=1)["result"]["structuredContent"]
    second = mcp(client, "tools/call", params, request_id=2)["result"]["structuredContent"]
    assert first == second


def test_missing_fields_are_null_and_listed(client):
    source_text = "I want a refund when possible."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["order_id"] is None
    assert structured["product_name"] is None
    assert structured["refund_reason"] is None
    assert structured["customer_request"] == "refund"
    assert structured["missing_fields"] == ["order_id", "product_name", "refund_reason"]
    assert structured["urgency_label"] == "low"
