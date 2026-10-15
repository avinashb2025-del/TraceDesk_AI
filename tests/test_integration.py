"""Integration tests that run against a live local FalkorDB.

These are skipped automatically when FalkorDB is not reachable, and reported as
skipped rather than falsely passing.
"""

import pytest

import db
import query_graph as q
import seed_data


@pytest.fixture(scope="module", autouse=True)
def require_database():
    status = db.health_check()
    if not status["connected"]:
        pytest.skip(f"FalkorDB not available at {status['host']}:{status['port']}")
    seed_data.seed()


def test_owner_of_payments_api():
    owners = q.get_owner("Payments API")
    assert owners and owners[0]["name"] == "Maya"


def test_incident_101_is_linked_to_payments_api():
    incidents = q.get_incidents_for_service("Payments API")
    assert any(i["id"] == "INC-101" for i in incidents)


def test_solution_recorded_for_payments_api():
    solutions = q.get_solutions_for_service("Payments API")
    assert any(s["solution_id"] == "SOL-101" for s in solutions)


def test_unknown_service_returns_none():
    assert q.get_service("WooCommerce") is None


def test_other_service_does_not_leak_payments_data():
    owners = q.get_owner("Orders Service")
    assert owners and owners[0]["name"] == "Leo"
    assert all(o["name"] != "Maya" for o in owners)


def test_special_characters_are_handled():
    assert q.get_service("Payments' API -- DROP") is None


def test_multi_hop_dependencies_are_bounded():
    direct = {d["name"] for d in q.get_dependencies("Checkout Web", depth=1)}
    deep = {d["name"] for d in q.get_dependencies("Checkout Web", depth=3)}
    assert direct <= deep
    assert "Payments API" in direct
    assert deep  # deeper traversal returns something


def test_blast_radius_includes_consumers():
    radius = q.get_blast_radius("Payments API")
    assert radius["origin"]["name"] == "Payments API"
    assert any(a["name"] == "Checkout Web" for a in radius["affected"])


def test_topology_returns_nodes_and_edges():
    topo = q.get_topology()
    assert len(topo["nodes"]) > 0
    assert len(topo["edges"]) > 0


def test_list_solutions_returns_recorded_solutions():
    solutions = q.list_solutions()
    assert any(s["id"] == "SOL-101" and s["service"] == "Payments API" for s in solutions)


def test_repeated_seeding_does_not_duplicate():
    before = q.summary_counts()
    seed_data.seed()
    seed_data.seed()
    after = q.summary_counts()
    assert before["nodes"] == after["nodes"]
    assert before["relationships"] == after["relationships"]
