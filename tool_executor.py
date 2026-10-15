"""Safe execution layer for TraceDesk AI's allowlisted investigation tools.

This module executes only the read-only functions already implemented in
query_graph.py. It never accepts raw Cypher from the model.
"""

from __future__ import annotations

import json
from typing import Any, Callable

import query_graph as q
from db import GraphUnavailableError
from llm_planner import LLMPlannerError, _validate_arguments


class ToolExecutionError(RuntimeError):
    """Raised when a requested investigation tool cannot execute safely."""


def _json_safe(value: Any) -> Any:
    """Round-trip data through JSON so results are safe to return to an LLM/MCP."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        raise ToolExecutionError("Tool returned data that could not be serialized.") from exc


def _require_service(service_name: str) -> dict[str, Any]:
    """Resolve a service first, so unknown names are not mistaken for empty results."""
    service = q.get_service(service_name)
    if service is None:
        raise _UnknownEntityError(
            f"No service named '{service_name}' is recorded in the TraceDesk graph."
        )
    return service


class _UnknownEntityError(ToolExecutionError):
    """Raised when a requested graph entity does not exist."""


def _get_incident_details(incident_id: str) -> dict[str, Any]:
    incident = q.get_incident(incident_id)
    if incident is None:
        raise _UnknownEntityError(
            f"No incident with ID '{incident_id}' is recorded in the TraceDesk graph."
        )
    return incident


def _get_service_owner(service_name: str) -> list[dict[str, Any]]:
    service = _require_service(service_name)
    return q.get_owner(service["name"])


def _get_service_incidents(service_name: str) -> list[dict[str, Any]]:
    service = _require_service(service_name)
    return q.get_incidents_for_service(service["name"])


def _get_service_dependencies(
    service_name: str, depth: int
) -> list[dict[str, Any]]:
    service = _require_service(service_name)
    return q.get_dependencies(service["name"], depth=depth)


def _get_service_blast_radius(
    service_name: str, depth: int
) -> dict[str, Any]:
    service = _require_service(service_name)
    result = q.get_blast_radius(service["name"], depth=depth)
    # A service was verified immediately above; None here would be unexpected.
    if result is None:
        raise ToolExecutionError("Blast-radius query returned no origin service.")
    return result


def _get_service_solutions(service_name: str) -> list[dict[str, Any]]:
    service = _require_service(service_name)
    return q.get_solutions_for_service(service["name"])


_TOOL_HANDLERS: dict[str, Callable[..., Any]] = {
    "get_incident_details": _get_incident_details,
    "get_service_owner": _get_service_owner,
    "get_service_incidents": _get_service_incidents,
    "get_service_dependencies": _get_service_dependencies,
    "get_service_blast_radius": _get_service_blast_radius,
    "get_service_solutions": _get_service_solutions,
}


def execute_tool(name: str, arguments: Any) -> dict[str, Any]:
    """Validate and execute one approved tool, returning structured graph data.

    Result statuses:
      - ``ok``: query ran successfully, even if the result list is empty.
      - ``no_result``: the requested service/incident does not exist.
      - errors raise ``ToolExecutionError`` so callers can handle failures
        without confusing them with valid empty results.
    """
    if not isinstance(name, str) or name not in _TOOL_HANDLERS:
        raise ToolExecutionError(f"Unsupported tool: {name!r}")

    try:
        safe_arguments = _validate_arguments(name, arguments)
    except LLMPlannerError as exc:
        raise ToolExecutionError(str(exc)) from exc

    handler = _TOOL_HANDLERS[name]

    try:
        data = handler(**safe_arguments)
    except _UnknownEntityError as exc:
        return {
            "status": "no_result",
            "tool": name,
            "arguments": safe_arguments,
            "message": str(exc),
            "data": None,
            "source": "FalkorDB via query_graph.py",
        }
    except GraphUnavailableError as exc:
        raise ToolExecutionError(
            "FalkorDB is unavailable or the read-only graph query failed."
        ) from exc
    except ToolExecutionError:
        raise
    except Exception as exc:
        # Avoid passing raw exceptions, connection strings, or internal details
        # into the model/UI. Keep the original exception available as the cause.
        raise ToolExecutionError(
            f"Execution failed for approved tool '{name}'."
        ) from exc

    safe_data = _json_safe(data)
    return {
        "status": "ok",
        "tool": name,
        "arguments": safe_arguments,
        "data": safe_data,
        "result_count": len(safe_data) if isinstance(safe_data, list) else None,
        "source": "FalkorDB via query_graph.py",
    }
