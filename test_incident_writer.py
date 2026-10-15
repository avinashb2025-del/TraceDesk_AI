from unittest.mock import Mock, call

import pytest

import incident_writer as writer


def test_create_incident_writes_node_and_affects_relationship(monkeypatch):
    graph = Mock()
    monkeypatch.setattr(writer.q, "get_service", lambda name: {"name": name})
    monkeypatch.setattr(
        writer.q, "get_incident",
        Mock(side_effect=[None, {"id": "INC-106", "title": "API timeout"}]),
    )
    monkeypatch.setattr(writer, "get_graph", lambda: graph)

    created = writer.create_incident(
        "inc-106", "  API timeout  ", "high", "investigating",
        "Payments API", " Requests are timing out ",
    )

    assert created["id"] == "INC-106"
    assert created["title"] == "API timeout"
    assert created["severity"] == "High"
    assert created["status"] == "Investigating"
    assert created["service"] == "Payments API"
    query, params = graph.query.call_args.args
    assert "CREATE (i:Incident" in query
    assert "CREATE (i)-[:AFFECTS]->(s)" in query
    assert params["id"] == "INC-106"
    assert params["service_name"] == "Payments API"
    assert params["description"] == "Requests are timing out"
    assert created["timestamp"].endswith("Z")


def test_duplicate_incident_id_is_rejected_before_write(monkeypatch):
    graph = Mock()
    monkeypatch.setattr(writer.q, "get_service", lambda name: {"name": name})
    monkeypatch.setattr(writer.q, "get_incident", lambda incident_id: {"id": incident_id})
    monkeypatch.setattr(writer, "get_graph", lambda: graph)

    with pytest.raises(writer.IncidentWriteError, match="already exists"):
        writer.create_incident(
            "INC-106", "API timeout", "High", "Investigating",
            "Payments API", "Requests are timing out",
        )
    graph.query.assert_not_called()


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"incident_id": "bad-id"}, "Incident ID"),
        ({"title": ""}, "Title is required"),
        ({"severity": "Urgent"}, "valid severity"),
        ({"status": "Open"}, "valid incident status"),
        ({"service_name": ""}, "Choose an affected service"),
        ({"description": ""}, "Description is required"),
    ],
)
def test_invalid_input_is_rejected(monkeypatch, kwargs, message):
    monkeypatch.setattr(writer.q, "get_service", lambda name: {"name": name})
    monkeypatch.setattr(writer.q, "get_incident", lambda incident_id: None)
    payload = {
        "incident_id": "INC-106",
        "title": "API timeout",
        "severity": "High",
        "status": "Investigating",
        "service_name": "Payments API",
        "description": "Requests are timing out",
    }
    payload.update(kwargs)
    with pytest.raises(writer.IncidentWriteError, match=message):
        writer.create_incident(**payload)


def test_unknown_service_is_rejected(monkeypatch):
    graph = Mock()
    monkeypatch.setattr(writer.q, "get_service", lambda name: None)
    monkeypatch.setattr(writer, "get_graph", lambda: graph)
    with pytest.raises(writer.IncidentWriteError, match="was not found"):
        writer.create_incident(
            "INC-106", "API timeout", "High", "Investigating",
            "Missing service", "Requests are timing out",
        )
    graph.query.assert_not_called()


def test_incident_not_visible_after_write_is_reported(monkeypatch):
    graph = Mock()
    monkeypatch.setattr(writer.q, "get_service", lambda name: {"name": name})
    monkeypatch.setattr(writer.q, "get_incident", lambda incident_id: None)
    monkeypatch.setattr(writer, "get_graph", lambda: graph)
    with pytest.raises(writer.IncidentWriteError, match="did not return the new incident"):
        writer.create_incident(
            "INC-106", "API timeout", "High", "Investigating",
            "Payments API", "Requests are timing out",
        )
    graph.query.assert_called_once()
