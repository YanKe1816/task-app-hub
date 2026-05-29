import os
import re
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_file


APP_SLUG = "customer-refund-request-extractor"
TOOL_NAME = "customer_refund_request_extractor"
DELIVERY_APP_SLUG = "delivery-address-extractor"
DELIVERY_TOOL_NAME = "delivery_address_extractor"
SUPPORT_APP_SLUG = "support-message-classifier"
SUPPORT_TOOL_NAME = "support_message_classifier"
RETURN_APP_SLUG = "return-reason-normalizer"
RETURN_TOOL_NAME = "return_reason_normalizer"

app = Flask(__name__)


INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_text": {
            "type": "string",
            "description": "Raw customer refund request message provided by the user.",
        }
    },
    "required": ["source_text"],
    "additionalProperties": False,
}

OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "order_id": {"type": ["string", "null"]},
        "product_name": {"type": ["string", "null"]},
        "refund_reason": {"type": ["string", "null"]},
        "customer_request": {"type": ["string", "null"]},
        "urgency_label": {"type": "string", "enum": ["low", "normal", "high", "unknown"]},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "source_text": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "order_id",
        "product_name",
        "refund_reason",
        "customer_request",
        "urgency_label",
        "missing_fields",
        "source_text",
        "errors",
    ],
    "additionalProperties": False,
}

TOOL_DESCRIPTION = (
    "Use this tool only for deterministic extraction from an existing customer refund "
    "message. The tool returns order ID, product name, refund reason, customer request, "
    "urgency label, missing fields, source text, and errors. Do not use this tool for "
    "refund approval decisions. Do not use this tool for writing customer replies. Do "
    "not use this tool for order updates or refund processing. Do not use this tool for "
    "customer service advice, internal notes, or next-step recommendations. If the user "
    "asks for any action, judgment, reply writing, or order modification, the tool is "
    "out of scope."
)

TOOL_DEFINITION: Dict[str, Any] = {
    "name": TOOL_NAME,
    "title": "Refund Request Extractor",
    "description": TOOL_DESCRIPTION,
    "inputSchema": INPUT_SCHEMA,
    "outputSchema": OUTPUT_SCHEMA,
    "annotations": {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    },
}

DELIVERY_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_text": {
            "type": "string",
            "description": "Raw customer delivery message provided by the user.",
        }
    },
    "required": ["source_text"],
    "additionalProperties": False,
}

DELIVERY_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "recipient_name": {"type": ["string", "null"]},
        "phone_number": {"type": ["string", "null"]},
        "delivery_address": {"type": ["string", "null"]},
        "delivery_note": {"type": ["string", "null"]},
        "preferred_delivery_time": {"type": ["string", "null"]},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "source_text": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "recipient_name",
        "phone_number",
        "delivery_address",
        "delivery_note",
        "preferred_delivery_time",
        "missing_fields",
        "source_text",
        "errors",
    ],
    "additionalProperties": False,
}

DELIVERY_TOOL_DESCRIPTION = (
    "Use this tool only when the user provides a customer delivery message and asks to "
    "extract structured delivery fields. The tool returns recipient name, phone number, "
    "delivery address, delivery note, preferred delivery time, missing fields, source "
    "text, and errors. Do not use or present this tool for writing replies, drafting "
    "emails, customer communication, delivery advice, courier actions, order updates, "
    "external system calls, or deliverability decisions. If the user asks to write a "
    "reply, draft a message, contact a courier, change an address, modify an order, or "
    "decide whether delivery is possible, this tool is out of scope. The correct "
    "behavior for out-of-scope requests is to avoid using this app for that task and "
    "state that this app only extracts structured delivery fields from provided "
    "delivery messages."
)

DELIVERY_TOOL_DEFINITION: Dict[str, Any] = {
    "name": DELIVERY_TOOL_NAME,
    "title": "Delivery Address Extractor",
    "description": DELIVERY_TOOL_DESCRIPTION,
    "inputSchema": DELIVERY_INPUT_SCHEMA,
    "outputSchema": DELIVERY_OUTPUT_SCHEMA,
    "annotations": {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    },
}

SUPPORT_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_text": {
            "type": "string",
            "description": "Raw customer support message to classify and extract structured fields from.",
        }
    },
    "required": ["source_text"],
    "additionalProperties": False,
}

SUPPORT_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "issue_type": {
            "type": ["string", "null"],
            "description": "The classified support issue type.",
        },
        "user_request": {
            "type": ["string", "null"],
            "description": "The user's explicit request extracted from the message.",
        },
        "urgency_label": {"type": "string", "enum": ["low", "normal", "high", "unknown"]},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "source_text": {"type": "string"},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "issue_type",
        "user_request",
        "urgency_label",
        "missing_fields",
        "source_text",
        "errors",
    ],
    "additionalProperties": False,
}

SUPPORT_TOOL_DESCRIPTION = (
    "Use this tool when the user provides a customer support message and needs "
    "structured classification fields. The tool returns issue type, user request, "
    "urgency label, missing fields, source text, and errors. Do not use this tool to "
    "reply to the customer, promise a solution, update a ticket system, contact the "
    "customer, call external systems, or provide customer service advice. This tool is "
    "useful when deterministic structured support-message classification is needed "
    "before ticket routing or human review."
)

SUPPORT_TOOL_DEFINITION: Dict[str, Any] = {
    "name": SUPPORT_TOOL_NAME,
    "title": "Support Message Classifier",
    "description": SUPPORT_TOOL_DESCRIPTION,
    "inputSchema": SUPPORT_INPUT_SCHEMA,
    "outputSchema": SUPPORT_OUTPUT_SCHEMA,
    "annotations": {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    },
}

RETURN_INPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason_text": {
            "type": "string",
            "description": "Raw customer return reason text to normalize.",
        }
    },
    "required": ["reason_text"],
    "additionalProperties": False,
}

RETURN_OUTPUT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "normalized_reason": {
            "type": "string",
            "enum": [
                "damaged_item",
                "wrong_item",
                "not_as_described",
                "size_or_fit_issue",
                "changed_mind",
                "late_delivery",
                "missing_parts",
                "quality_issue",
                "duplicate_order",
                "other",
                "unknown",
            ],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason_text": {"type": "string"},
        "matched_keywords": {"type": "array", "items": {"type": "string"}},
        "errors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "enum": ["missing_field", "invalid_value", "out_of_scope", "internal_error"],
                    },
                    "message": {"type": "string"},
                },
                "required": ["code", "message"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["normalized_reason", "confidence", "reason_text", "matched_keywords", "errors"],
    "additionalProperties": False,
}

RETURN_TOOL_DESCRIPTION = (
    "Use this tool when the user provides a raw customer return reason and needs it "
    "normalized into one fixed return reason enum. The tool returns normalized_reason, "
    "confidence, original reason_text, matched_keywords, and errors. Do not use this "
    "tool to decide whether a return should be accepted, assign responsibility, reply "
    "to the customer, modify an order, contact anyone, or provide customer service "
    "advice. This tool is useful when deterministic reason normalization is needed "
    "before routing, reporting, or human review."
)

RETURN_TOOL_DEFINITION: Dict[str, Any] = {
    "name": RETURN_TOOL_NAME,
    "title": "Return Reason Normalizer",
    "description": RETURN_TOOL_DESCRIPTION,
    "inputSchema": RETURN_INPUT_SCHEMA,
    "outputSchema": RETURN_OUTPUT_SCHEMA,
    "annotations": {
        "readOnlyHint": True,
        "openWorldHint": False,
        "destructiveHint": False,
    },
}


def make_output(
    source_text: str,
    order_id: Optional[str] = None,
    product_name: Optional[str] = None,
    refund_reason: Optional[str] = None,
    customer_request: Optional[str] = None,
    urgency_label: str = "unknown",
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    missing_fields = [
        field
        for field, value in [
            ("order_id", order_id),
            ("product_name", product_name),
            ("refund_reason", refund_reason),
            ("customer_request", customer_request),
        ]
        if value is None
    ]
    return {
        "order_id": order_id,
        "product_name": product_name,
        "refund_reason": refund_reason,
        "customer_request": customer_request,
        "urgency_label": urgency_label,
        "missing_fields": missing_fields,
        "source_text": source_text,
        "errors": errors or [],
    }


def make_delivery_output(
    source_text: str,
    recipient_name: Optional[str] = None,
    phone_number: Optional[str] = None,
    delivery_address: Optional[str] = None,
    delivery_note: Optional[str] = None,
    preferred_delivery_time: Optional[str] = None,
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    missing_fields = [
        field
        for field, value in [
            ("recipient_name", recipient_name),
            ("phone_number", phone_number),
            ("delivery_address", delivery_address),
            ("delivery_note", delivery_note),
            ("preferred_delivery_time", preferred_delivery_time),
        ]
        if value is None
    ]
    return {
        "recipient_name": recipient_name,
        "phone_number": phone_number,
        "delivery_address": delivery_address,
        "delivery_note": delivery_note,
        "preferred_delivery_time": preferred_delivery_time,
        "missing_fields": missing_fields,
        "source_text": source_text,
        "errors": errors or [],
    }


def make_support_output(
    source_text: str,
    issue_type: Optional[str] = None,
    user_request: Optional[str] = None,
    urgency_label: str = "unknown",
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    missing_fields = [
        field
        for field, value in [
            ("issue_type", issue_type),
            ("user_request", user_request),
        ]
        if value is None
    ]
    return {
        "issue_type": issue_type,
        "user_request": user_request,
        "urgency_label": urgency_label,
        "missing_fields": missing_fields,
        "source_text": source_text,
        "errors": errors or [],
    }


def make_return_output(
    reason_text: str,
    normalized_reason: str = "unknown",
    confidence: float = 0,
    matched_keywords: Optional[List[str]] = None,
    errors: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    return {
        "normalized_reason": normalized_reason,
        "confidence": confidence,
        "reason_text": reason_text,
        "matched_keywords": matched_keywords or [],
        "errors": errors or [],
    }


def extract_after_label(text: str, labels: List[str]) -> Optional[str]:
    ordered_labels = sorted(labels, key=len, reverse=True)
    label_pattern = "|".join(re.escape(label) for label in ordered_labels)
    pattern = rf"\b(?:{label_pattern})\s*(?:is|:|#)?\s*([^\n.;,]+)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip(" -#:\t")
    value = re.sub(r"^(?:a|an|the)\s+", "", value, flags=re.IGNORECASE)
    return value or None


def clean_product_name(value: str) -> Optional[str]:
    cleaned = value.strip(" -#:\t.,")
    cleaned = re.sub(r"^(?:a|an|the)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned or cleaned.lower() in {"item", "product", "order"}:
        return None
    return cleaned


def extract_order_id(text: str) -> Optional[str]:
    patterns = [
        r"\border\s*(?:id|number|no\.?|#)\s*(?:is|:)?\s*([A-Z0-9][A-Z0-9_-]{2,})",
        r"\border\s+([A-Z]{1,6}[0-9][A-Z0-9_-]*)\b",
        r"\b(order-[A-Z0-9_-]+)\b",
        r"\b(ord-[A-Z0-9_-]+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_product_name(text: str) -> Optional[str]:
    patterns = [
        r"\border\s+[A-Z]{1,6}[0-9][A-Z0-9_-]*\s+for\s+(?:product\s+)?((?:a|an|the)\s+)?(.+?)\s+arrived\b",
        r"\border\s+[A-Z]{1,6}[0-9][A-Z0-9_-]*\s+for\s+(?:product\s+)?((?:a|an|the)\s+)?(.+?)(?:[.;,]|$)",
        r"\bi\s+bought\s+((?:a|an|the)\s+)?(.+?)\s+and\s+it\s+arrived\b",
        r"\bthe\s+([^.;,]+?)\s+arrived\s+(?:cracked|damaged|broken|defective)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            product = clean_product_name(match.group(2) if match.lastindex and match.lastindex >= 2 else match.group(1))
            if product:
                return product

    return extract_after_label(text, ["product", "item", "product name", "item name"])


def extract_refund_reason(text: str) -> Optional[str]:
    labeled = extract_after_label(text, ["reason", "refund reason", "because", "due to"])
    if labeled:
        return labeled
    arrival_condition = re.search(
        r"\b(?:it|the item|the product|order\s+[A-Z]{1,6}[0-9][A-Z0-9_-]*|.+?)\s+arrived\s+(cracked|damaged|broken|defective)\b",
        text,
        re.IGNORECASE,
    )
    if arrival_condition:
        return f"arrived {arrival_condition.group(1).lower()}"
    fixed_reason_patterns = [
        r"\b(item was broken)\b",
        r"\b(product does not work)\b",
        r"\b(wrong item was delivered)\b",
    ]
    for pattern in fixed_reason_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).lower()
    match = re.search(r"\b(?:refund|return)\b.*?\b(?:because|as|since|due to)\s+([^\n.;]+)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def extract_customer_request(text: str) -> Optional[str]:
    if re.search(r"\b(?:request|want|would like|need|please)\b.*\brefund\b", text, re.IGNORECASE):
        return "refund"
    if re.search(r"\brefund\b", text, re.IGNORECASE):
        return "refund"
    if re.search(r"\breturn\b", text, re.IGNORECASE):
        return "return"
    return None


def classify_urgency(text: str) -> str:
    lowered = text.lower()
    high_terms = [
        "urgent",
        "immediately",
        "right now",
        "asap",
        "escalate",
        "escalation",
        "chargeback",
        "legal",
        "lawyer",
        "attorney",
        "last chance",
        "angry",
        "furious",
        "third time",
        "again and again",
        "no one has responded",
    ]
    low_terms = ["maybe", "wondering", "when possible", "no rush", "not urgent"]
    if any(term in lowered for term in high_terms):
        return "high"
    if any(term in lowered for term in low_terms):
        return "low"
    if re.search(r"\brefund\b|\breturn\b", lowered):
        return "normal"
    return "unknown"


def is_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(?:approve|deny|decide|determine|judge)\b.*\brefund\b",
        r"\brefund\b.*\b(?:approval|denial|eligibility|eligible|ineligible)\b",
        r"\b(?:should i|should we|do they deserve|are they eligible|is this eligible)\b.*\brefund\b",
        r"\b(?:write|draft|compose|create|generate)\b.*\b(?:reply|response|message|email)\b",
        r"\b(?:reply|respond)\b.*\b(?:customer|message|email|refund)\b",
        r"\bcustomer service message\b",
        r"\b(?:modify|change|update|cancel|edit|mark)\b.*\border\b",
        r"\border\b.*\b(?:refunded|refund processed|changed|updated|modified)\b",
        r"\b(?:contact|call|email|reach out)\b.*\bcustomer\b",
        r"\b(?:advice|advise|recommendation|next steps|what should)\b",
        r"\b(?:issue|process|send|promise|grant)\b.*\brefund\b",
        r"\binternal note\b",
        r"\b(?:note|memo)\b.*\b(?:was refunded|refund was processed|marked as refunded)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def extract_refund_request(arguments: Dict[str, Any]) -> Dict[str, Any]:
    if "source_text" not in arguments:
        return make_output(
            "",
            errors=[{"code": "missing_field", "message": "source_text is required."}],
        )

    source_text = arguments["source_text"]
    if not isinstance(source_text, str) or not source_text.strip():
        return make_output(
            source_text if isinstance(source_text, str) else "",
            errors=[{"code": "invalid_value", "message": "source_text must be a non-empty string."}],
        )

    if is_out_of_scope(source_text):
        return make_output(
            source_text,
            errors=[{"code": "out_of_scope", "message": "The request asks for an action or judgment outside deterministic extraction."}],
        )

    order_id = extract_order_id(source_text)
    product_name = extract_product_name(source_text)
    refund_reason = extract_refund_reason(source_text)
    customer_request = extract_customer_request(source_text)
    urgency_label = classify_urgency(source_text)

    return make_output(
        source_text,
        order_id=order_id,
        product_name=product_name,
        refund_reason=refund_reason,
        customer_request=customer_request,
        urgency_label=urgency_label,
    )


def clean_delivery_value(value: str) -> Optional[str]:
    cleaned = value.strip(" \t\r\n\"'")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None


def extract_delivery_recipient(text: str) -> Optional[str]:
    patterns = [
        r"\bName:\s*([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})\b",
        r"\bShip to\s+([A-Z][A-Za-z'-]+(?:\s+[A-Z][A-Za-z'-]+){0,3})\s*,",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_delivery_value(match.group(1).rstrip("."))
    return None


def extract_delivery_phone(text: str) -> Optional[str]:
    match = re.search(r"\b(?:Phone:\s*)?(\d{3}[-.]\d{3}[-.]\d{4})\b", text, re.IGNORECASE)
    return match.group(1) if match else None


def extract_delivery_address(text: str) -> Optional[str]:
    patterns = [
        r"\bAddress:\s*([^.\n]+)",
        r"\b\d{3}[-.]\d{3}[-.]\d{4}\s*,\s*([^.\n]+)",
        r"\bsend it to\s+([^.\n]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return clean_delivery_value(match.group(1).rstrip(","))
    return None


def extract_delivery_note(text: str) -> Optional[str]:
    patterns = [
        r"\b(Leave\s+[^.]+\.)",
        r"\b(Ring\s+[^.]+\.)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            note = clean_delivery_value(match.group(1))
            if note:
                return note[0].upper() + note[1:]
    return None


def extract_preferred_delivery_time(text: str) -> Optional[str]:
    match = re.search(r"\bDeliver\s+([^.\n]+)\.", text, re.IGNORECASE)
    if match:
        return clean_delivery_value(match.group(1).lower())
    return None


def is_delivery_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\bcan\b.*\b(?:deliver|delivered|delivery possible)\b",
        r"\b(?:judge|decide|determine)\b.*\bdeliver",
        r"\bcontact\b.*\bcourier\b",
        r"\b(?:modify|change|update|edit)\b.*\b(?:order|delivery address|address)\b",
        r"\b(?:write|draft|compose|reply|respond)\b.*\b(?:customer|message|email|reply|response|delivery)\b",
        r"\b(?:call|send to)\b.*\b(?:external system|api|courier)\b",
        r"\b(?:advice|advise|recommendation|next steps|what should)\b.*\bdeliver",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def extract_delivery_request(arguments: Dict[str, Any]) -> Dict[str, Any]:
    if "source_text" not in arguments:
        return make_delivery_output(
            "",
            errors=[{"code": "missing_field", "message": "source_text is required."}],
        )

    source_text = arguments["source_text"]
    if not isinstance(source_text, str) or not source_text.strip():
        return make_delivery_output(
            source_text if isinstance(source_text, str) else "",
            errors=[{"code": "invalid_value", "message": "source_text must be a non-empty string."}],
        )

    if is_delivery_out_of_scope(source_text):
        return make_delivery_output(
            source_text,
            errors=[{"code": "out_of_scope", "message": "The request asks for an action or judgment outside deterministic extraction."}],
        )

    return make_delivery_output(
        source_text,
        recipient_name=extract_delivery_recipient(source_text),
        phone_number=extract_delivery_phone(source_text),
        delivery_address=extract_delivery_address(source_text),
        delivery_note=extract_delivery_note(source_text),
        preferred_delivery_time=extract_preferred_delivery_time(source_text),
    )


def classify_support_issue_type(text: str) -> Optional[str]:
    lowered = text.lower()
    if re.search(r"\brefund\b|\breturn\b", lowered):
        return "refund"
    if re.search(r"\bshipping\b|\bdelivery\b|\btracking\b|\btrack\b|\baddress\b|\bshipment\b", lowered):
        return "delivery"
    if re.search(r"\blogin\b|\bpassword\b|\baccount\b|\bsign in\b|\blocked out\b|\blocked account\b", lowered):
        return "account"
    if re.search(r"\bcharge\b|\binvoice\b|\bpayment\b|\bsubscription\b|\bbilling\b|\bcard\b", lowered):
        return "billing"
    if re.search(r"\berror\b|\bbug\b|\bbroken\b|\bcrash\b|\bnot working\b|\bapp problem\b|\bfeature\b", lowered):
        return "technical"
    if re.search(r"\bhelp\b|\bsupport\b|\bquestion\b|\bissue\b|\bproblem\b", lowered):
        return "general"
    return None


def extract_support_user_request(text: str, issue_type: Optional[str]) -> Optional[str]:
    lowered = text.lower()
    if re.search(r"\brefund\b|\breturn\b", lowered):
        return "refund"
    if re.search(r"\btrack\b|\btracking\b", lowered):
        return "tracking help"
    if re.search(r"\bchange\b.*\baddress\b|\bupdate\b.*\baddress\b", lowered):
        return "address update help"
    if re.search(r"\breset\b.*\bpassword\b|\bpassword reset\b", lowered):
        return "password reset help"
    if re.search(r"\blogin\b|\bsign in\b|\blocked out\b|\baccount access\b", lowered):
        return "account access help"
    if re.search(r"\binvoice\b|\bcharge\b|\bpayment\b|\bbilling\b|\bsubscription\b", lowered):
        return "billing help"
    if re.search(r"\berror\b|\bbug\b|\bbroken\b|\bcrash\b|\bnot working\b", lowered):
        return "technical help"
    if issue_type == "general":
        return "support help"
    return None


def classify_support_urgency(text: str, issue_type: Optional[str]) -> str:
    lowered = text.lower()
    high_terms = [
        "urgent",
        "asap",
        "immediately",
        "right now",
        "deadline",
        "locked out",
        "payment failed",
        "business is down",
        "business interruption",
        "cannot access",
        "third time",
        "again and again",
        "repeated",
    ]
    low_terms = ["no rush", "not urgent", "whenever possible", "just wondering", "question"]
    if any(term in lowered for term in high_terms):
        return "high"
    if any(term in lowered for term in low_terms):
        return "low"
    if issue_type is not None:
        return "normal"
    return "unknown"


def is_support_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(?:write|draft|compose|reply|respond)\b.*\b(?:customer|message|email|reply|response)\b",
        r"\bpromise\b.*\b(?:solution|resolution|fix|refund)\b",
        r"\b(?:update|modify|close|escalate|assign)\b.*\b(?:ticket|case|support ticket)\b",
        r"\b(?:contact|call|email|reach out)\b.*\bcustomer\b",
        r"\b(?:call|send to)\b.*\b(?:external system|api|crm|ticket system)\b",
        r"\b(?:advice|advise|recommendation|next steps|what should)\b",
        r"\bdecide\b.*\b(?:resolve|resolution|solution)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def extract_support_request(arguments: Dict[str, Any]) -> Dict[str, Any]:
    if "source_text" not in arguments:
        return make_support_output(
            "",
            errors=[{"code": "missing_field", "message": "source_text is required."}],
        )

    source_text = arguments["source_text"]
    if not isinstance(source_text, str) or not source_text.strip():
        return make_support_output(
            source_text if isinstance(source_text, str) else "",
            errors=[{"code": "invalid_value", "message": "source_text must be a non-empty string."}],
        )

    if is_support_out_of_scope(source_text):
        return make_support_output(
            source_text,
            errors=[{"code": "out_of_scope", "message": "The request asks for an action or advice outside deterministic classification."}],
        )

    issue_type = classify_support_issue_type(source_text)
    user_request = extract_support_user_request(source_text, issue_type)
    urgency_label = classify_support_urgency(source_text, issue_type)
    return make_support_output(
        source_text,
        issue_type=issue_type,
        user_request=user_request,
        urgency_label=urgency_label,
    )


RETURN_REASON_KEYWORDS = [
    ("damaged_item", ["arrived damaged", "item arrived broken", "defective on arrival", "damaged", "broken", "cracked", "shattered", "smashed"]),
    ("wrong_item", ["wrong item", "incorrect item", "different product", "not what i ordered", "received another item"]),
    ("not_as_described", ["not as described", "different from description", "misleading description", "not like the picture", "does not match listing", "product does not match listing"]),
    ("size_or_fit_issue", ["too small", "too large", "does not fit", "wrong size", "sizing issue", "fit issue"]),
    ("changed_mind", ["changed my mind", "no longer want it", "do not need it anymore", "bought by mistake", "unwanted item"]),
    ("late_delivery", ["arrived late", "delivered late", "missed delivery date", "too late", "arrived late"]),
    ("missing_parts", ["missing parts", "missing pieces", "incomplete package", "parts missing", "parts are missing", "accessory missing"]),
    ("quality_issue", ["poor quality", "bad quality", "cheaply made", "quality problem", "material issue", "does not work well"]),
    ("duplicate_order", ["ordered twice", "duplicate order", "bought twice", "bought this twice", "accidental duplicate", "duplicate purchase"]),
]


def is_return_out_of_scope(text: str) -> bool:
    lowered = text.lower()
    patterns = [
        r"\b(?:should we|should i|decide|approve|accept|reject|deny|valid)\b.*\breturn\b",
        r"\brefund\b.*\b(?:customer|order|now|decision|approve|approval)\b",
        r"\bwho\b.*\bresponsible\b",
        r"\b(?:blame|responsibility|responsible)\b",
        r"\b(?:write|draft|compose|reply|respond)\b.*\b(?:customer|message|email|reply|response)\b",
        r"\b(?:modify|change|update|mark)\b.*\border\b",
        r"\b(?:contact|call|email|reach out)\b.*\b(?:customer|anyone)\b",
        r"\b(?:advice|advise|policy|recommendation|next steps|what should)\b",
    ]
    return any(re.search(pattern, lowered) for pattern in patterns)


def normalize_return_reason(arguments: Dict[str, Any]) -> Dict[str, Any]:
    if "reason_text" not in arguments:
        return make_return_output(
            "",
            errors=[{"code": "missing_field", "message": "reason_text is required."}],
        )

    reason_text = arguments["reason_text"]
    if not isinstance(reason_text, str):
        return make_return_output(
            "",
            errors=[{"code": "invalid_value", "message": "reason_text must contain a usable return reason."}],
        )

    if not reason_text.strip() or not re.search(r"[A-Za-z0-9]", reason_text):
        return make_return_output(
            reason_text,
            errors=[{"code": "invalid_value", "message": "reason_text must contain a usable return reason."}],
        )

    if is_return_out_of_scope(reason_text):
        return make_return_output(
            reason_text,
            errors=[
                {
                    "code": "out_of_scope",
                    "message": "This tool only normalizes return reasons and does not make decisions or take actions.",
                }
            ],
        )

    lowered = reason_text.lower()
    for normalized_reason, keywords in RETURN_REASON_KEYWORDS:
        matched = [keyword for keyword in keywords if keyword in lowered]
        if matched:
            return make_return_output(reason_text, normalized_reason, 0.95, matched)

    indirect_patterns = [
        ("damaged_item", r"\b(?:does not work|won't work|stopped working)\b"),
        ("late_delivery", r"\b(?:came after|after the date|past the date)\b"),
        ("not_as_described", r"\b(?:not what was shown|looks different)\b"),
    ]
    for normalized_reason, pattern in indirect_patterns:
        match = re.search(pattern, lowered)
        if match:
            return make_return_output(reason_text, normalized_reason, 0.75, [match.group(0)])

    if re.search(r"\b(?:return|returned|send it back|exchange)\b", lowered):
        return make_return_output(reason_text, "other", 0.5, [])

    return make_return_output(reason_text, "unknown", 0, [])


def json_rpc_result(request_id: Any, result: Dict[str, Any]):
    return jsonify({"jsonrpc": "2.0", "id": request_id, "result": result})


def json_rpc_error(request_id: Any, code: int, message: str):
    return jsonify({"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}})


def requested_protocol_version(payload: Dict[str, Any]) -> str:
    params = payload.get("params")
    if isinstance(params, dict) and isinstance(params.get("protocolVersion"), str):
        return params["protocolVersion"]
    return "2025-11-25"


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/.well-known/openai-apps-challenge")
def openai_apps_challenge():
    return os.environ.get("OPENAI_APPS_CHALLENGE", "openai-apps-challenge-not-configured"), 200, {
        "Content-Type": "text/plain; charset=utf-8"
    }


@app.get(f"/{APP_SLUG}")
def app_page():
    return send_file("index.html")


@app.get(f"/{APP_SLUG}/privacy")
def privacy_page():
    return send_file("privacy.html")


@app.get(f"/{APP_SLUG}/terms")
def terms_page():
    return send_file("terms.html")


@app.get(f"/{APP_SLUG}/support")
def support_page():
    return send_file("support.html")


@app.get(f"/{DELIVERY_APP_SLUG}")
def delivery_app_page():
    return send_file("delivery_index.html")


@app.get(f"/{DELIVERY_APP_SLUG}/privacy")
def delivery_privacy_page():
    return send_file("delivery_privacy.html")


@app.get(f"/{DELIVERY_APP_SLUG}/terms")
def delivery_terms_page():
    return send_file("delivery_terms.html")


@app.get(f"/{DELIVERY_APP_SLUG}/support")
def delivery_support_page():
    return send_file("delivery_support.html")


@app.get(f"/{SUPPORT_APP_SLUG}")
def support_classifier_app_page():
    return send_file("support_classifier_index.html")


@app.get(f"/{SUPPORT_APP_SLUG}/privacy")
def support_classifier_privacy_page():
    return send_file("support_classifier_privacy.html")


@app.get(f"/{SUPPORT_APP_SLUG}/terms")
def support_classifier_terms_page():
    return send_file("support_classifier_terms.html")


@app.get(f"/{SUPPORT_APP_SLUG}/support")
def support_classifier_support_page():
    return send_file("support_classifier_support.html")


@app.get(f"/{RETURN_APP_SLUG}")
def return_reason_app_page():
    return send_file("return_reason_index.html")


@app.get(f"/{RETURN_APP_SLUG}/privacy")
def return_reason_privacy_page():
    return send_file("return_reason_privacy.html")


@app.get(f"/{RETURN_APP_SLUG}/terms")
def return_reason_terms_page():
    return send_file("return_reason_terms.html")


@app.get(f"/{RETURN_APP_SLUG}/support")
def return_reason_support_page():
    return send_file("return_reason_support.html")


@app.post(f"/{APP_SLUG}/mcp")
def app_mcp():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    request_id = payload.get("id")

    if method == "initialize":
        return json_rpc_result(
            request_id,
            {
                "protocolVersion": requested_protocol_version(payload),
                "serverInfo": {"name": APP_SLUG, "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return json_rpc_result(request_id, {"tools": [TOOL_DEFINITION]})

    if method == "tools/call":
        params = payload.get("params") or {}
        if params.get("name") != TOOL_NAME:
            return json_rpc_error(request_id, -32602, "Unknown tool.")
        arguments = params.get("arguments") or {}
        try:
            structured_content = extract_refund_request(arguments)
        except Exception:
            structured_content = make_output(
                str(arguments.get("source_text", "")) if isinstance(arguments, dict) else "",
                errors=[{"code": "internal_error", "message": "An unexpected internal error occurred."}],
            )
        has_errors = bool(structured_content["errors"])
        return json_rpc_result(
            request_id,
            {
                "structuredContent": structured_content,
                "content": [{"type": "text", "text": "error" if has_errors else "success"}],
                "isError": has_errors,
            },
        )

    return json_rpc_error(request_id, -32601, "Method not found.")


@app.post(f"/{RETURN_APP_SLUG}/mcp")
def return_reason_app_mcp():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    request_id = payload.get("id")

    if method == "initialize":
        return json_rpc_result(
            request_id,
            {
                "protocolVersion": requested_protocol_version(payload),
                "serverInfo": {"name": RETURN_APP_SLUG, "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return json_rpc_result(request_id, {"tools": [RETURN_TOOL_DEFINITION]})

    if method == "tools/call":
        params = payload.get("params") or {}
        if params.get("name") != RETURN_TOOL_NAME:
            return json_rpc_error(request_id, -32602, "Unknown tool.")
        arguments = params.get("arguments") or {}
        try:
            structured_content = normalize_return_reason(arguments)
        except Exception:
            structured_content = make_return_output(
                str(arguments.get("reason_text", "")) if isinstance(arguments, dict) else "",
                errors=[{"code": "internal_error", "message": "An unexpected internal error occurred."}],
            )
        has_errors = bool(structured_content["errors"])
        return json_rpc_result(
            request_id,
            {
                "structuredContent": structured_content,
                "content": [{"type": "text", "text": "error" if has_errors else "success"}],
                "isError": has_errors,
            },
        )

    return json_rpc_error(request_id, -32601, "Method not found.")


@app.post(f"/{SUPPORT_APP_SLUG}/mcp")
def support_classifier_app_mcp():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    request_id = payload.get("id")

    if method == "initialize":
        return json_rpc_result(
            request_id,
            {
                "protocolVersion": requested_protocol_version(payload),
                "serverInfo": {"name": SUPPORT_APP_SLUG, "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return json_rpc_result(request_id, {"tools": [SUPPORT_TOOL_DEFINITION]})

    if method == "tools/call":
        params = payload.get("params") or {}
        if params.get("name") != SUPPORT_TOOL_NAME:
            return json_rpc_error(request_id, -32602, "Unknown tool.")
        arguments = params.get("arguments") or {}
        try:
            structured_content = extract_support_request(arguments)
        except Exception:
            structured_content = make_support_output(
                str(arguments.get("source_text", "")) if isinstance(arguments, dict) else "",
                errors=[{"code": "internal_error", "message": "An unexpected internal error occurred."}],
            )
        has_errors = bool(structured_content["errors"])
        return json_rpc_result(
            request_id,
            {
                "structuredContent": structured_content,
                "content": [{"type": "text", "text": "error" if has_errors else "success"}],
                "isError": has_errors,
            },
        )

    return json_rpc_error(request_id, -32601, "Method not found.")


@app.post(f"/{DELIVERY_APP_SLUG}/mcp")
def delivery_app_mcp():
    payload = request.get_json(silent=True) or {}
    method = payload.get("method")
    request_id = payload.get("id")

    if method == "initialize":
        return json_rpc_result(
            request_id,
            {
                "protocolVersion": requested_protocol_version(payload),
                "serverInfo": {"name": DELIVERY_APP_SLUG, "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        )

    if method == "tools/list":
        return json_rpc_result(request_id, {"tools": [DELIVERY_TOOL_DEFINITION]})

    if method == "tools/call":
        params = payload.get("params") or {}
        if params.get("name") != DELIVERY_TOOL_NAME:
            return json_rpc_error(request_id, -32602, "Unknown tool.")
        arguments = params.get("arguments") or {}
        try:
            structured_content = extract_delivery_request(arguments)
        except Exception:
            structured_content = make_delivery_output(
                str(arguments.get("source_text", "")) if isinstance(arguments, dict) else "",
                errors=[{"code": "internal_error", "message": "An unexpected internal error occurred."}],
            )
        has_errors = bool(structured_content["errors"])
        return json_rpc_result(
            request_id,
            {
                "structuredContent": structured_content,
                "content": [{"type": "text", "text": "error" if has_errors else "success"}],
                "isError": has_errors,
            },
        )

    return json_rpc_error(request_id, -32601, "Method not found.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
