"""Unit tests for the graph-grounded agent (graph layer mocked)."""

import pytest

import agent
from db import GraphUnavailableError


class FakeQuery:
    """In-memory stand-in for the query_graph module used by the agent."""

    QUERY_TEMPLATES = {
        "owner_of_service": {"cypher": "MATCH (p)-[:OWNS]->(s)", "columns": ["name", "role", "team"]},
        "incidents_for_service": {"cypher": "MATCH (i)-[:AFFECTS]->(s)", "columns": ["id"]},
        "solution_for_service": {"cypher": "MATCH (i)-[:FIXED_BY]->(sol)", "columns": ["summary"]},
        "dependencies": {"cypher": "MATCH (s)-[:DEPENDS_ON*1..N]->(d)", "columns": ["name"]},
        "blast_radius": {"cypher": "MATCH (d)-[:DEPENDS_ON*1..N]->(s)", "columns": ["name"]},
        "incident_investigation": {"cypher": "MATCH (i {id:$id})", "columns": ["id"]},
    }

    def __init__(self):
        self.services = [
            {"id": "S-PAYMENTS-API", "name": "Payments API", "env": "prod", "status": "degraded"},
            {"id": "S-ORDERS", "name": "Orders Service", "env": "prod", "status": "healthy"},
        ]
        self.projects = [{"id": "PR-CHECKOUT", "name": "Checkout Platform", "status": "active", "description": ""}]
        self.owners = {
            "Payments API": [{"name": "Maya", "role": "Backend Engineer", "team": "Payments Team"}],
            "Orders Service": [{"name": "Leo", "role": "Platform Engineer", "team": "Platform Team"}],
        }
        self.incidents_for = {
            "Payments API": [
                {"id": "INC-101", "title": "Payment requests timing out", "severity": "High",
                 "status": "Investigating", "timestamp": "2026-10-14T09:12:00Z"}
            ],
            "Orders Service": [],
        }
        self.solutions_for = {
            "Payments API": [
                {"incident_id": "INC-101", "solution_id": "SOL-101",
                 "summary": "Review connection pool limits.", "steps": "Check pool max.\nRelease connections.",
                 "reference": "runbooks/payments.md"}
            ],
            "Orders Service": [],
        }
        self.deps = {
            "Payments API": [{"id": "S-AUTH", "name": "Auth Service", "status": "healthy"}],
            "Orders Service": [{"id": "S-INVENTORY", "name": "Inventory Service", "status": "healthy"}],
        }
        self.dependents = {
            "Payments API": [{"id": "S-CHECKOUT-WEB", "name": "Checkout Web", "status": "healthy"}],
            "Orders Service": [],
        }
        self.incidents = {
            "INC-101": {
                "id": "INC-101", "title": "Payment requests timing out", "severity": "High",
                "status": "Investigating", "timestamp": "2026-10-14T09:12:00Z",
                "description": "Elevated 504s.", "services": ["Payments API"],
                "solution": {"id": "SOL-101", "summary": "Review connection pool limits.",
                             "steps": "Check pool max.", "reference": "runbooks/payments.md"},
            }
        }
        self.raise_on_services = False

    def list_services(self):
        if self.raise_on_services:
            raise GraphUnavailableError("db down")
        return self.services

    def list_projects(self):
        return self.projects

    def list_incidents(self):
        return list(self.incidents.values())

    def get_owner(self, name):
        return self.owners.get(name, [])

    def get_incidents_for_service(self, name):
        return self.incidents_for.get(name, [])

    def get_solutions_for_service(self, name):
        return self.solutions_for.get(name, [])

    def get_dependencies(self, name, depth=3):
        return self.deps.get(name, [])

    def get_dependents(self, name, depth=3):
        return self.dependents.get(name, [])

    def get_blast_radius(self, name, depth=3):
        return {"origin": next((s for s in self.services if s["name"] == name), None),
                "affected": self.dependents.get(name, [])}

    def get_incident(self, incident_id):
        return self.incidents.get(incident_id)


@pytest.fixture
def fake_q(monkeypatch):
    fake = FakeQuery()
    monkeypatch.setattr(agent, "q", fake)
    return fake


def test_owner_known_service(fake_q):
    response = agent.ask_agent("Who owns the Payments API?")
    assert response["intent"] == "owner"
    assert "Maya" in response["answer"]
    assert response["status"] == "ok"
    assert response["evidence"]


def test_owner_is_case_insensitive(fake_q):
    response = agent.ask_agent("who owns payments api")
    assert "Maya" in response["answer"]


def test_different_service_has_no_hardcoded_fallback(fake_q):
    response = agent.ask_agent("Who owns the Orders Service?")
    assert "Leo" in response["answer"]
    assert "Maya" not in response["answer"]


def test_unknown_service_returns_no_result(fake_q):
    response = agent.ask_agent("Who owns the WooCommerce Service?")
    assert response["status"] == "no_result"
    assert "couldn't identify" in response["answer"].lower()


def test_incident_lookup(fake_q):
    response = agent.ask_agent("Which incident affected the Payments API?")
    assert response["intent"] == "incidents"
    assert "INC-101" in response["answer"]


def test_solution_lookup(fake_q):
    response = agent.ask_agent("What is the solution for the Payments API?")
    assert response["intent"] == "solution"
    assert "SOL-101" in response["answer"]


def test_missing_solution_is_reported(fake_q):
    response = agent.ask_agent("What is the solution for the Orders Service?")
    assert response["status"] == "no_result"
    assert "no recorded solution" in response["answer"].lower()


def test_dependencies(fake_q):
    response = agent.ask_agent("What does the Payments API depend on?")
    assert response["intent"] == "dependencies"
    assert "Auth Service" in response["answer"]


def test_blast_radius(fake_q):
    response = agent.ask_agent("What is the blast radius of the Payments API?")
    assert response["intent"] == "blast_radius"
    assert "Checkout Web" in response["answer"]


def test_investigate_incident(fake_q):
    response = agent.ask_agent("Investigate INC-101")
    assert response["intent"] == "investigate"
    assert "INC-101" in response["answer"]
    assert response["limitations"]
    steps = response["answer"]
    assert "Check pool max" in steps


def test_investigate_unknown_incident(fake_q):
    response = agent.ask_agent("Investigate INC-999")
    assert response["status"] == "no_result"


def test_empty_question(fake_q):
    response = agent.ask_agent("")
    assert response["status"] == "no_result"


def test_unsupported_request(fake_q):
    response = agent.ask_agent("Tell me a joke")
    assert response["intent"] == "unknown"
    assert response["status"] == "no_result"


def test_database_failure_is_reported(fake_q):
    fake_q.raise_on_services = True
    response = agent.ask_agent("Who owns the Payments API?")
    assert response["status"] == "error"
    assert "cannot" in response["answer"].lower() or "could not" in response["answer"].lower()


def test_hypothesis_is_labelled_as_hypothesis(fake_q):
    investigation = agent.build_investigation("INC-101")
    assert investigation["hypothesis"]["statement"]
    assert "hypothesis" in investigation["hypothesis"]["basis"].lower()
    assert investigation["recommended_steps"] == ["Check pool max.", "Release connections."]
