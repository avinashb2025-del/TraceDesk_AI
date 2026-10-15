"""Unit tests for the safe TraceDesk tool executor (no live DB/API required)."""

import pytest

import tool_executor as executor
from db import GraphUnavailableError


def test_unknown_tool_is_rejected():
    with pytest.raises(executor.ToolExecutionError, match="Unsupported tool"):
        executor.execute_tool("run_arbitrary_cypher", {})


def test_invalid_arguments_are_rejected():
    with pytest.raises(executor.ToolExecutionError, match="between 1 and 5"):
        executor.execute_tool(
            "get_service_dependencies",
            {"service_name": "Payments API", "depth": 99},
        )


def test_service_owner_uses_canonical_service_name(monkeypatch):
    calls = []
    monkeypatch.setattr(
        executor.q, "get_service",
        lambda name: {"id": "S-PAYMENTS-API", "name": "Payments API", "status": "degraded"},
    )
    monkeypatch.setattr(
        executor.q, "get_owner",
        lambda name: calls.append(name) or [{"name": "Maya", "role": "Backend Engineer", "team": "Payments Team"}],
    )

    result = executor.execute_tool(
        "get_service_owner", {"service_name": " payments api "}
    )

    assert calls == ["Payments API"]
    assert result["status"] == "ok"
    assert result["data"][0]["name"] == "Maya"
    assert result["result_count"] == 1


def test_unknown_service_returns_no_result(monkeypatch):
    monkeypatch.setattr(executor.q, "get_service", lambda name: None)

    result = executor.execute_tool(
        "get_service_incidents", {"service_name": "Missing Service"}
    )

    assert result["status"] == "no_result"
    assert result["data"] is None
    assert "No service named" in result["message"]


def test_unknown_incident_returns_no_result(monkeypatch):
    monkeypatch.setattr(executor.q, "get_incident", lambda incident_id: None)

    result = executor.execute_tool(
        "get_incident_details", {"incident_id": "INC-999"}
    )

    assert result["status"] == "no_result"
    assert "INC-999" in result["message"]


def test_empty_list_is_a_successful_query_result(monkeypatch):
    monkeypatch.setattr(
        executor.q, "get_service",
        lambda name: {"id": "S-PAYMENTS-API", "name": "Payments API", "status": "degraded"},
    )
    monkeypatch.setattr(executor.q, "get_incidents_for_service", lambda name: [])

    result = executor.execute_tool(
        "get_service_incidents", {"service_name": "Payments API"}
    )

    assert result["status"] == "ok"
    assert result["data"] == []
    assert result["result_count"] == 0


def test_graph_failure_is_reported_without_leaking_details(monkeypatch):
    monkeypatch.setattr(
        executor.q, "get_incident",
        lambda incident_id: (_ for _ in ()).throw(GraphUnavailableError("private connection detail")),
    )

    with pytest.raises(executor.ToolExecutionError, match="FalkorDB is unavailable"):
        executor.execute_tool(
            "get_incident_details", {"incident_id": "INC-101"}
        )


def test_blast_radius_returns_json_safe_data(monkeypatch):
    monkeypatch.setattr(
        executor.q, "get_service",
        lambda name: {"id": "S-PAYMENTS-API", "name": "Payments API", "status": "degraded"},
    )
    monkeypatch.setattr(
        executor.q, "get_blast_radius",
        lambda name, depth: {
            "origin": {"name": name, "status": "degraded"},
            "affected": [{"name": "Checkout Web", "status": "healthy"}],
        },
    )

    result = executor.execute_tool(
        "get_service_blast_radius",
        {"service_name": "Payments API", "depth": 2},
    )

    assert result["status"] == "ok"
    assert result["data"]["origin"]["name"] == "Payments API"
    assert result["data"]["affected"][0]["name"] == "Checkout Web"
