"""FalkorDB connection management and health checks for TraceDesk AI.

All database access in the application goes through this module so that
connection handling, timeouts and error translation live in one place.
"""

import os

from falkordb import FalkorDB


HOST = os.environ.get("FALKORDB_HOST", "localhost")
PORT = int(os.environ.get("FALKORDB_PORT", "6379"))
GRAPH_NAME = os.environ.get("FALKORDB_GRAPH", "tracedesk")


class GraphUnavailableError(RuntimeError):
    """Raised when FalkorDB cannot be reached or a query cannot be executed."""


def get_graph():
    """Return a handle to the TraceDesk graph.

    A fresh client is created per call so that a database that was
    restarted becomes available again without restarting the app.
    """
    client = FalkorDB(host=HOST, port=PORT)
    return client.select_graph(GRAPH_NAME)


def health_check():
    """Ping FalkorDB and report connectivity.

    Returns a dictionary so the UI can render a real status instead of
    assuming the connection works.
    """
    result = {
        "connected": False,
        "host": HOST,
        "port": PORT,
        "graph": GRAPH_NAME,
        "node_count": None,
        "relationship_count": None,
        "error": None,
    }
    try:
        graph = get_graph()
        graph.ro_query("RETURN 1")
        node_rows = graph.ro_query("MATCH (n) RETURN count(n)").result_set
        rel_rows = graph.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set
        result["connected"] = True
        result["node_count"] = node_rows[0][0] if node_rows else 0
        result["relationship_count"] = rel_rows[0][0] if rel_rows else 0
    except Exception as error:  # noqa: BLE001 - translated to a friendly status
        result["error"] = str(error)
    return result


if __name__ == "__main__":
    status = health_check()
    print("FalkorDB health check:")
    for key, value in status.items():
        print(f"  {key}: {value}")
