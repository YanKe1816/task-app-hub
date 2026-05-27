import json
import subprocess
import sys
import time
from urllib.request import urlopen

import pytest

from server import APP_SLUG, DELIVERY_APP_SLUG, DELIVERY_OUTPUT_SCHEMA, DELIVERY_TOOL_NAME, OUTPUT_SCHEMA, TOOL_NAME, app


EXPECTED_OUTPUT_KEYS = set(OUTPUT_SCHEMA["required"])
EXPECTED_DELIVERY_OUTPUT_KEYS = set(DELIVERY_OUTPUT_SCHEMA["required"])


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def mcp(client, method, params=None, request_id=1):
    return mcp_for(client, APP_SLUG, method, params=params, request_id=request_id)


def mcp_for(client, slug, method, params=None, request_id=1):
    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params
    response = client.post(f"/{slug}/mcp", json=payload)
    assert response.status_code == 200
    return response.get_json()


def assert_structured_output(value):
    assert set(value.keys()) == EXPECTED_OUTPUT_KEYS
    assert "status" not in value
    assert value["urgency_label"] in {"low", "normal", "high", "unknown"}
    assert isinstance(value["missing_fields"], list)
    assert isinstance(value["source_text"], str)
    assert isinstance(value["errors"], list)
    for error in value["errors"]:
        assert set(error.keys()) == {"code", "message"}


def assert_delivery_structured_output(value):
    assert set(value.keys()) == EXPECTED_DELIVERY_OUTPUT_KEYS
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
    assert "Refund Request Extractor" in body
    assert "This app does not approve refunds." in body
    assert "sidcraigau@gmail.com" in body


def test_privacy_page_review_shell(client):
    response = client.get(f"/{APP_SLUG}/privacy")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "applies only to Refund Request Extractor" in body
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
    assert "Support page for Refund Request Extractor" in body
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
    assert tool["title"] == "Refund Request Extractor"
    assert tool["description"]
    assert tool["inputSchema"]["required"] == ["source_text"]
    assert tool["outputSchema"] == OUTPUT_SCHEMA
    assert tool["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }
    assert DELIVERY_TOOL_NAME not in [tool["name"] for tool in tools]


def test_delivery_initialize_contract(client):
    data = mcp_for(client, DELIVERY_APP_SLUG, "initialize")
    result = data["result"]
    assert result["protocolVersion"] == "2024-11-05"
    assert result["serverInfo"]["name"] == DELIVERY_APP_SLUG
    assert result["serverInfo"]["version"] == "0.1.0"
    assert "tools" in result["capabilities"]


def test_delivery_tools_list_single_tool_contract(client):
    data = mcp_for(client, DELIVERY_APP_SLUG, "tools/list")
    tools = data["result"]["tools"]
    assert len(tools) == 1
    tool = tools[0]
    assert tool["name"] == DELIVERY_TOOL_NAME
    assert tool["title"] == "Delivery Address Extractor"
    assert tool["description"]
    assert "Do not use or present this tool for writing replies" in tool["description"]
    assert "only extracts structured delivery fields" in tool["description"]
    assert tool["inputSchema"]["required"] == ["source_text"]
    assert tool["outputSchema"] == DELIVERY_OUTPUT_SCHEMA
    assert tool["annotations"] == {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    }
    assert TOOL_NAME not in [tool["name"] for tool in tools]


def test_generic_mcp_absent(client):
    response = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert response.status_code == 404


@pytest.mark.parametrize("path", ["/privacy", "/terms", "/support"])
def test_generic_review_shell_routes_absent(client, path):
    response = client.get(path)
    assert response.status_code == 404


@pytest.mark.parametrize(
    "path, required_text",
    [
        (f"/{DELIVERY_APP_SLUG}", "Extract structured delivery fields from customer-provided delivery messages."),
        (f"/{DELIVERY_APP_SLUG}/privacy", "No long-term storage of submitted input by this app."),
        (f"/{DELIVERY_APP_SLUG}/terms", "The app does not contact couriers."),
        (f"/{DELIVERY_APP_SLUG}/support", "It only extracts explicitly stated delivery fields."),
    ],
)
def test_delivery_review_shell_routes_are_app_specific_html(client, path, required_text):
    response = client.get(path)
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "text/html" in response.content_type
    assert "<!doctype html>" in body.lower()
    assert "Delivery Address Extractor" in body
    assert "sidcraigau@gmail.com" in body
    assert required_text in body
    assert "contact couriers" in body
    assert "modify orders" in body
    assert "Customer Refund Request Extractor" not in body
    assert "Refund Request Extractor" not in body
    assert "customer_refund_request_extractor" not in body
    assert "refund approval" not in body.lower()
    assert "refund rejection" not in body.lower()


def test_cross_endpoint_isolation_and_no_generic_mcp(client):
    refund_tools = mcp_for(client, APP_SLUG, "tools/list")["result"]["tools"]
    delivery_tools = mcp_for(client, DELIVERY_APP_SLUG, "tools/list")["result"]["tools"]
    assert [tool["name"] for tool in refund_tools] == [TOOL_NAME]
    assert [tool["name"] for tool in delivery_tools] == [DELIVERY_TOOL_NAME]
    assert client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code == 404


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
    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": "success"}]
    structured = result["structuredContent"]
    assert_structured_output(structured)
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
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] == "Travel Mug"
    assert structured["refund_reason"] == "arrived cracked"
    assert structured["customer_request"] == "refund"
    assert structured["urgency_label"] == "high"
    assert structured["missing_fields"] == []
    assert structured["source_text"] == source_text
    assert structured["errors"] == []


def test_tools_call_extracts_product_from_order_for_pattern(client):
    source_text = "Order RF12345 for a Travel Mug arrived cracked. I want a refund today or I will file a chargeback."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] == "Travel Mug"
    assert structured["refund_reason"] == "arrived cracked"
    assert structured["customer_request"] == "refund"
    assert structured["urgency_label"] == "high"
    assert "product_name" not in structured["missing_fields"]
    assert "refund_reason" not in structured["missing_fields"]


def test_tools_call_extracts_product_from_for_product_pattern(client):
    source_text = "Order RF98765 for product Wireless Mouse arrived damaged. Please refund me."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["order_id"] == "RF98765"
    assert structured["product_name"] == "Wireless Mouse"
    assert structured["refund_reason"] == "arrived damaged"
    assert structured["customer_request"] == "refund"
    assert structured["urgency_label"] == "normal"


def test_tools_call_extracts_product_from_bought_pattern(client):
    source_text = "I bought a Desk Lamp and it arrived broken. I want a refund."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["product_name"] == "Desk Lamp"
    assert structured["refund_reason"] == "arrived broken"
    assert structured["customer_request"] == "refund"


def test_tools_call_keeps_missing_product_when_not_explicit(client):
    source_text = "Order RF12345 arrived damaged. I want a refund."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] is None
    assert structured["refund_reason"] == "arrived damaged"
    assert "product_name" in structured["missing_fields"]
    assert "refund_reason" not in structured["missing_fields"]


def test_tools_call_keeps_missing_reason_when_not_explicit(client):
    source_text = "Order RF12345 for a Travel Mug. I want a refund."
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": source_text}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
    assert structured["order_id"] == "RF12345"
    assert structured["product_name"] == "Travel Mug"
    assert structured["refund_reason"] is None
    assert "refund_reason" in structured["missing_fields"]
    assert "product_name" not in structured["missing_fields"]


def test_missing_source_text_error(client):
    result = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {}})["result"]
    assert result["isError"] is True
    assert result["content"] == [{"type": "text", "text": "error"}]
    structured = result["structuredContent"]
    assert_structured_output(structured)
    assert structured["errors"] == [{"code": "missing_field", "message": "source_text is required."}]


def test_empty_source_text_error(client):
    data = mcp(client, "tools/call", {"name": TOOL_NAME, "arguments": {"source_text": "  "}})
    structured = data["result"]["structuredContent"]
    assert_structured_output(structured)
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


def test_delivery_tools_call_complete_message(client):
    source_text = (
        'Please extract delivery address fields from this message: "Ship to Emily Carter, '
        '415-555-0198, 221B Baker Street, Apt 5, San Francisco, CA 94107. '
        'Leave at the front desk. Deliver tomorrow afternoon."'
    )
    result = mcp_for(
        client,
        DELIVERY_APP_SLUG,
        "tools/call",
        {"name": DELIVERY_TOOL_NAME, "arguments": {"source_text": source_text}},
    )["result"]
    assert "structuredContent" in result
    assert result["isError"] is False
    assert result["content"] == [{"type": "text", "text": "success"}]
    structured = result["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["recipient_name"] == "Emily Carter"
    assert structured["phone_number"] == "415-555-0198"
    assert structured["delivery_address"] == "221B Baker Street, Apt 5, San Francisco, CA 94107"
    assert structured["delivery_note"] == "Leave at the front desk."
    assert structured["preferred_delivery_time"] == "tomorrow afternoon"
    assert structured["missing_fields"] == []
    assert structured["source_text"] == source_text
    assert structured["errors"] == []


def test_delivery_tools_call_labeled_details(client):
    source_text = (
        'Extract delivery details: "Name: Mark Lee. Phone: 212-555-0144. '
        'Address: 88 Pine Street, New York, NY 10005."'
    )
    structured = mcp_for(
        client,
        DELIVERY_APP_SLUG,
        "tools/call",
        {"name": DELIVERY_TOOL_NAME, "arguments": {"source_text": source_text}},
    )["result"]["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["recipient_name"] == "Mark Lee"
    assert structured["phone_number"] == "212-555-0144"
    assert structured["delivery_address"] == "88 Pine Street, New York, NY 10005"
    assert structured["delivery_note"] is None
    assert structured["preferred_delivery_time"] is None
    assert "delivery_note" in structured["missing_fields"]
    assert "preferred_delivery_time" in structured["missing_fields"]
    assert structured["errors"] == []


def test_delivery_tools_call_partial_message(client):
    source_text = 'Extract delivery fields from: "Please send it to 742 Evergreen Terrace. Ring the doorbell twice."'
    structured = mcp_for(
        client,
        DELIVERY_APP_SLUG,
        "tools/call",
        {"name": DELIVERY_TOOL_NAME, "arguments": {"source_text": source_text}},
    )["result"]["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["recipient_name"] is None
    assert structured["phone_number"] is None
    assert structured["delivery_address"] == "742 Evergreen Terrace"
    assert structured["delivery_note"] == "Ring the doorbell twice."
    assert structured["preferred_delivery_time"] is None
    assert "recipient_name" in structured["missing_fields"]
    assert "phone_number" in structured["missing_fields"]
    assert "preferred_delivery_time" in structured["missing_fields"]
    assert structured["errors"] == []


def test_delivery_repeated_calls_are_stable(client):
    params = {
        "name": DELIVERY_TOOL_NAME,
        "arguments": {
            "source_text": 'Extract delivery details: "Name: Mark Lee. Phone: 212-555-0144. Address: 88 Pine Street, New York, NY 10005."'
        },
    }
    first = mcp_for(client, DELIVERY_APP_SLUG, "tools/call", params, request_id=1)["result"]["structuredContent"]
    second = mcp_for(client, DELIVERY_APP_SLUG, "tools/call", params, request_id=2)["result"]["structuredContent"]
    third = mcp_for(client, DELIVERY_APP_SLUG, "tools/call", params, request_id=3)["result"]["structuredContent"]
    assert first == second == third


def test_delivery_missing_source_text_error(client):
    result = mcp_for(client, DELIVERY_APP_SLUG, "tools/call", {"name": DELIVERY_TOOL_NAME, "arguments": {}})["result"]
    assert result["isError"] is True
    assert result["content"] == [{"type": "text", "text": "error"}]
    structured = result["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["errors"] == [{"code": "missing_field", "message": "source_text is required."}]


def test_delivery_empty_source_text_error(client):
    structured = mcp_for(
        client,
        DELIVERY_APP_SLUG,
        "tools/call",
        {"name": DELIVERY_TOOL_NAME, "arguments": {"source_text": "  "}},
    )["result"]["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["errors"][0]["code"] == "invalid_value"


@pytest.mark.parametrize(
    "text",
    [
        "Can this address be delivered today?",
        "Contact the courier and change this delivery address.",
        "Write a reply to this customer about their delivery.",
    ],
)
def test_delivery_out_of_scope_errors(client, text):
    structured = mcp_for(
        client,
        DELIVERY_APP_SLUG,
        "tools/call",
        {"name": DELIVERY_TOOL_NAME, "arguments": {"source_text": text}},
    )["result"]["structuredContent"]
    assert_delivery_structured_output(structured)
    assert structured["errors"][0]["code"] == "out_of_scope"
