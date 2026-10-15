"""Shared test fixtures.

Tests run against mocked graph data by default. Integration tests that need a
live FalkorDB are skipped automatically when the database is unavailable.
"""

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import query_graph as q  # noqa: E402


class FakeResult:
    def __init__(self, result_set, run_time_ms=0.5):
        self.result_set = result_set
        self.run_time_ms = run_time_ms


class FakeGraph:
    """Minimal FalkorDB stand-in backed by a dict of canned responses."""

    def __init__(self, responses=None):
        self.responses = responses or {}

    def ro_query(self, cypher, params=None):
        for token, result in self.responses.items():
            if token in cypher:
                if callable(result):
                    return FakeResult(result(params or {}))
                return FakeResult(result)
        return FakeResult([])


@pytest.fixture
def patch_query(monkeypatch):
    """Patch query_graph._query to return canned rows, keyed by a token."""

    def _patch(responses):
        def fake_query(cypher, params=None):
            for token, rows in responses.items():
                if token in cypher:
                    return rows, 1.0
            return [], 1.0

        monkeypatch.setattr(q, "_query", fake_query)

    return _patch


@pytest.fixture
def fake_graph(monkeypatch):
    """Patch query_graph.get_graph with a FakeGraph instance."""

    def _patch(responses=None):
        graph = FakeGraph(responses)
        monkeypatch.setattr(q, "get_graph", lambda: graph)
        return graph

    return _patch
