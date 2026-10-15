
"""
LLM tool planner for TraceDesk AI.

Step 1:
- Sends a question to an LLM.
- Lets the model choose from an allowlisted set of
  read-only investigation tools.
- Validates the returned tool names and arguments.
- Does NOT execute any graph query.

Existing agent.py and app.py remain unchanged.
"""

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

DEFAULT_MODEL = "gpt-4.1-mini"

MAX_QUESTION_LENGTH = 4000
MAX_DEPTH = 5

INCIDENT_ID_PATTERN = re.compile(r"^INC-\d{3,}$", re.IGNORECASE)


class LLMPlannerError(RuntimeError):
    """Raised when LLM planning cannot safely complete."""


# Only expose capabilities backed by existing read-only
# query functions in query_graph.py.
#
# The executor will be added in Step 2.
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "name": "get_incident_details",
        "description": (
            "Retrieve a specific incident, its affected services, "
            "and any recorded solution. Use when an incident ID "
            "such as INC-101 is known."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "incident_id": {
                    "type": "string",
                    "description": "Incident ID, e.g. INC-101."
                }
            },
            "required": ["incident_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_service_owner",
        "description": (
            "Find the recorded person and team responsible "
            "for a service."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Exact service name."
                }
            },
            "required": ["service_name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_service_incidents",
        "description": (
            "Find recorded incidents affecting a service."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Exact service name."
                }
            },
            "required": ["service_name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_service_dependencies",
        "description": (
            "Traverse outgoing DEPENDS_ON relationships to find "
            "the services that a service relies on. Use for "
            "upstream dependencies and multi-hop analysis."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Exact starting service name."
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth, from 1 to 5."
                },
            },
            "required": ["service_name", "depth"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_service_blast_radius",
        "description": (
            "Find downstream services that depend on a service "
            "and could be affected if it fails."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Exact service name."
                },
                "depth": {
                    "type": "integer",
                    "description": "Traversal depth, from 1 to 5."
                },
            },
            "required": ["service_name", "depth"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_service_solutions",
        "description": (
            "Retrieve recorded solutions and remediation steps "
            "associated with incidents affecting a service."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "service_name": {
                    "type": "string",
                    "description": "Exact service name."
                }
            },
            "required": ["service_name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


ALLOWED_TOOL_NAMES = {
    tool["name"] for tool in TOOL_DEFINITIONS
}


SYSTEM_PROMPT = """
You are TraceDesk AI, an incident-investigation planner.

Your task is to select the existing read-only tools needed
to investigate a user's question about incidents, services,
ownership, dependencies, impact, and recorded solutions.

Rules:
1. Select tools based on the user's actual question.
2. You may request multiple tools when the investigation
   requires independent evidence.
3. Use the exact service or incident identifiers stated
   by the user. Do not invent identifiers.
4. For dependency traversal, choose a depth between 1 and 5.
5. Never invent graph results or claim a query has run.
6. Do not create arbitrary Cypher queries.
7. Do not propose database writes or destructive actions
   as tool calls.
8. If the question is outside TraceDesk's supported domain,
   respond with a concise explanation instead of calling
   an irrelevant tool.
9. Tool selection is only a plan. The application must
   execute tools and verify their actual results separately.
"""


def _validate_arguments(
    tool_name: str,
    arguments: Any,
) -> dict[str, Any]:
    """Validate arguments before any future tool execution."""

    if tool_name not in ALLOWED_TOOL_NAMES:
        raise LLMPlannerError(
            f"Unsupported tool requested: {tool_name}"
        )

    if not isinstance(arguments, dict):
        raise LLMPlannerError(
            "Tool arguments must be a JSON object."
        )

    if tool_name == "get_incident_details":
        if set(arguments) != {"incident_id"}:
            raise LLMPlannerError(
                "Invalid incident tool arguments."
            )

        incident_id = arguments["incident_id"]

        if not isinstance(incident_id, str):
            raise LLMPlannerError("Incident ID must be text.")

        incident_id = incident_id.strip().upper()

        if not INCIDENT_ID_PATTERN.fullmatch(incident_id):
            raise LLMPlannerError("Invalid incident ID format.")

        return {"incident_id": incident_id}

    if tool_name in {
        "get_service_owner",
        "get_service_incidents",
        "get_service_solutions",
    }:
        if set(arguments) != {"service_name"}:
            raise LLMPlannerError(
                "Invalid service tool arguments."
            )

        service_name = arguments["service_name"]

        if not isinstance(service_name, str):
            raise LLMPlannerError(
                "Service name must be text."
            )

        service_name = service_name.strip()

        if not service_name or len(service_name) > 120:
            raise LLMPlannerError(
                "Service name must contain 1–120 characters."
            )

        return {"service_name": service_name}

    if tool_name in {
        "get_service_dependencies",
        "get_service_blast_radius",
    }:
        if set(arguments) != {"service_name", "depth"}:
            raise LLMPlannerError(
                "Invalid traversal tool arguments."
            )

        service_name = arguments["service_name"]
        depth = arguments["depth"]

        if not isinstance(service_name, str):
            raise LLMPlannerError(
                "Service name must be text."
            )

        service_name = service_name.strip()

        if not service_name or len(service_name) > 120:
            raise LLMPlannerError(
                "Service name must contain 1–120 characters."
            )

        # bool is a subclass of int in Python, so reject it.
        if isinstance(depth, bool) or not isinstance(depth, int):
            raise LLMPlannerError(
                "Traversal depth must be an integer."
            )

        if not 1 <= depth <= MAX_DEPTH:
            raise LLMPlannerError(
                "Traversal depth must be between 1 and 5."
            )

        return {
            "service_name": service_name,
            "depth": depth,
        }

    raise LLMPlannerError("No validator exists for this tool.")


def plan_tools(
    question: str,
    model: str | None = None,
) -> dict[str, Any]:
    """
    Ask the LLM which tools should be used.

    Returns one of these structures:

    {
        "status": "tool_calls",
        "tool_calls": [
            {
                "call_id": "...",
                "name": "get_service_owner",
                "arguments": {"service_name": "Payments API"}
            }
        ]
    }

    or:

    {
        "status": "final",
        "answer": "..."
    }

    This function never executes a tool or accesses FalkorDB.
    """

    if not isinstance(question, str):
        raise LLMPlannerError("Question must be text.")

    question = question.strip()

    if not question:
        raise LLMPlannerError("Question cannot be empty.")

    if len(question) > MAX_QUESTION_LENGTH:
        raise LLMPlannerError(
            f"Question exceeds {MAX_QUESTION_LENGTH} characters."
        )

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise LLMPlannerError(
            "OPENAI_API_KEY is missing. Add it to your local .env file."
        )

    selected_model = (
        model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL
    ).strip()

    if not selected_model:
        raise LLMPlannerError("OPENAI_MODEL cannot be empty.")

    try:
        client = OpenAI(
            api_key=api_key,
            timeout=30.0,
            max_retries=1,
        )

        response = client.responses.create(
            model=selected_model,
            instructions=SYSTEM_PROMPT,
            input=question,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
            parallel_tool_calls=False,
        )

    except Exception as exc:
        # Avoid exposing credentials or provider internals
        # to the Streamlit UI.
        raise LLMPlannerError(
            "The LLM planning request failed. Check API access, "
            "model availability, and network connectivity."
        ) from exc

    tool_calls = []

    for item in response.output:
        if getattr(item, "type", None) != "function_call":
            continue

        name = item.name

        if name not in ALLOWED_TOOL_NAMES:
            raise LLMPlannerError(
                f"The model returned an unsupported tool: {name}"
            )

        try:
            raw_arguments = json.loads(item.arguments)
        except (TypeError, json.JSONDecodeError) as exc:
            raise LLMPlannerError(
                "The model returned invalid tool arguments."
            ) from exc

        validated_arguments = _validate_arguments(
            name,
            raw_arguments,
        )

        tool_calls.append({
            "call_id": item.call_id,
            "name": name,
            "arguments": validated_arguments,
        })

    if tool_calls:
        return {
            "status": "tool_calls",
            "model": selected_model,
            "tool_calls": tool_calls,
        }

    return {
        "status": "final",
        "model": selected_model,
        "answer": response.output_text or (
            "I could not determine a suitable investigation tool."
        ),
    }
