"""Unit tests for the graph query layer (FalkorDB mocked)."""

import pytest

import query_graph as q
from db import GraphUnavailableError


def test_clamp_depth_bounds():
    assert q._clamp_depth(0) == 1
    assert q._clamp_depth(99) == q.MAX_DEPTH
    assert q._clamp_depth("bad") == q.DEFAULT_DEPTH
    assert q._clamp_depth(2) == 2


def test_rows_to_dicts():
    rows = [["S-PAYMENTS-API", "Payments API", "prod", "degraded"]]
    result = q._rows_to_dicts(rows, ["id", "name", "env", "status"])
    assert result == [
        {"id": "S-PAYMENTS-API", "name": "Payments API", "env": "prod", "status": "degraded"}
    ]


def test_get_owner_maps_rows(patch_query):
    patch_query({"OWNS": [["Maya", "Backend Engineer", "Payments Team"]]})
    owners = q.get_owner("Payments API")
    assert owners == [{"name": "Maya", "role": "Backend Engineer", "team": "Payments Team"}]


def test_get_service_none_when_empty(patch_query):
    patch_query({"MATCH (s:Service)": []})
    assert q.get_service("Nonexistent") is None


def test_get_incidents_for_service_mapping(patch_query):
    patch_query({"AFFECTS": [["INC-101", "Payment requests timing out", "High", "Investigating", "2026-10-14T09:12:00Z"]]})
    incidents = q.get_incidents_for_service("Payments API")
    assert incidents[0]["id"] == "INC-101"
    assert incidents[0]["severity"] == "High"


def test_graph_unavailable_is_wrapped(fake_graph, monkeypatch):
    def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(q, "get_graph", boom)
    with pytest.raises(GraphUnavailableError):
        q.list_services()


def test_run_template_injects_depth(patch_query, monkeypatch):
    captured = {}

    def fake_query(cypher, params=None):
        captured["cypher"] = cypher
        return [["S-AUTH", "Auth Service", "healthy"]], 2.5

    monkeypatch.setattr(q, "_query", fake_query)
    result = q.run_template("dependencies", {"name": "Payments API"}, depth=2)
    assert "..2]" in captured["cypher"]
    assert "..N" not in captured["cypher"]
    assert result["run_time_ms"] == 2.5
    assert result["rows"][0]["name"] == "Auth Service"


def test_blast_radius_reports_origin_and_consumers(patch_query, monkeypatch):
    def fake_query(cypher, params=None):
        if "origin:Service) WHERE" in cypher and "RETURN DISTINCT origin" in cypher:
            return [], 1.0
        if "coalesce" in cypher or "RETURN s.id, s.name, s.env" in cypher:
            return [["S-PAYMENTS-API", "Payments API", "prod", "degraded"]], 1.0
        if "dependent:Service" in cypher:
            return [["S-CHECKOUT-WEB", "Checkout Web", "healthy"]], 1.0
        return [], 1.0

    monkeypatch.setattr(q, "_query", fake_query)
    radius = q.get_blast_radius("Payments API")
    assert radius["origin"]["name"] == "Payments API"
    assert radius["affected"][0]["name"] == "Checkout Web"


def test_get_node_details_mapping(patch_query):
    patch_query({"properties(n)": [["Service", "Payments API", {"id": "S-PAYMENTS-API", "status": "degraded"}]]})
    details = q.get_node_details("S-PAYMENTS-API")
    assert details["label"] == "Service"
    assert details["properties"]["status"] == "degraded"


def test_list_solutions_maps_rows(patch_query):
    patch_query(
        {
            "FIXED_BY": [
                ["SOL-101", "Review connection pool limits.", "Check pool.", "runbooks/x.md",
                 "INC-101", "Payment requests timing out", "Payments API"]
            ]
        }
    )
    solutions = q.list_solutions()
    assert solutions[0]["id"] == "SOL-101"
    assert solutions[0]["incident_id"] == "INC-101"
    assert solutions[0]["service"] == "Payments API"
