"""Reusable, read-only graph queries for TraceDesk AI.

All traversal is bounded (depth and row limits) and every query is read-only.
Service names are matched case-insensitively. Any database failure is surfaced
as :class:`GraphUnavailableError` so callers can show an honest error state.
"""

from db import get_graph, GraphUnavailableError


MAX_DEPTH = 5
DEFAULT_DEPTH = 3
ROW_LIMIT = 200


def _clamp_depth(depth):
    try:
        depth = int(depth)
    except (TypeError, ValueError):
        depth = DEFAULT_DEPTH
    return max(1, min(depth, MAX_DEPTH))


def _query(cypher, params=None):
    """Execute a read-only query. Returns ``(rows, run_time_ms)``."""
    try:
        graph = get_graph()
        result = graph.ro_query(cypher, params or {})
    except Exception as error:  # noqa: BLE001 - translated for the caller
        raise GraphUnavailableError(str(error)) from error
    try:
        run_time_ms = result.run_time_ms
    except AttributeError:
        run_time_ms = None
    return result.result_set, run_time_ms


def _rows_to_dicts(rows, columns):
    return [dict(zip(columns, row)) for row in rows]


# --------------------------------------------------------------------------
# Inventory-style queries
# --------------------------------------------------------------------------
def list_services():
    rows, _ = _query(
        f"MATCH (s:Service) RETURN s.id, s.name, s.env, s.status ORDER BY s.name LIMIT {ROW_LIMIT}"
    )
    return _rows_to_dicts(rows, ["id", "name", "env", "status"])


def list_incidents():
    rows, _ = _query(
        "MATCH (i:Incident) "
        "OPTIONAL MATCH (i)-[:AFFECTS]->(s:Service) "
        "RETURN i.id, i.title, i.severity, i.status, i.timestamp, s.name "
        f"ORDER BY i.timestamp DESC LIMIT {ROW_LIMIT}"
    )
    incidents = {}
    for iid, title, sev, status, ts, service in rows:
        if iid not in incidents:
            incidents[iid] = {
                "id": iid,
                "title": title,
                "severity": sev,
                "status": status,
                "timestamp": ts,
                "services": [],
            }
        if service:
            incidents[iid]["services"].append(service)
    return list(incidents.values())


def list_people():
    rows, _ = _query(
        "MATCH (p:Person) RETURN p.id, p.name, p.role, p.team ORDER BY p.name"
    )
    return _rows_to_dicts(rows, ["id", "name", "role", "team"])


def list_projects():
    rows, _ = _query(
        "MATCH (p:Project) RETURN p.id, p.name, p.status, p.description ORDER BY p.name"
    )
    return _rows_to_dicts(rows, ["id", "name", "status", "description"])


def list_solutions():
    """All recorded solutions with their related incident and affected service."""
    rows, _ = _query(
        "MATCH (sol:Solution) "
        "OPTIONAL MATCH (i:Incident)-[:FIXED_BY]->(sol) "
        "OPTIONAL MATCH (i)-[:AFFECTS]->(s:Service) "
        "RETURN sol.id, sol.summary, sol.steps, sol.reference, i.id, i.title, s.name "
        "ORDER BY sol.id",
        {},
    )
    return _rows_to_dicts(
        rows,
        ["id", "summary", "steps", "reference", "incident_id", "incident_title", "service"],
    )


def get_service(service_name):
    """Return a single service (case-insensitive) or ``None``."""
    rows, _ = _query(
        "MATCH (s:Service) "
        "WHERE toLower(s.name) = toLower($name) "
        "RETURN s.id, s.name, s.env, s.status",
        {"name": service_name},
    )
    dicts = _rows_to_dicts(rows, ["id", "name", "env", "status"])
    return dicts[0] if dicts else None


def get_incident(incident_id):
    """Return incident details with affected services and recorded solution."""
    rows, _ = _query(
        "MATCH (i:Incident {id: $id}) "
        "OPTIONAL MATCH (i)-[:AFFECTS]->(s:Service) "
        "OPTIONAL MATCH (i)-[:FIXED_BY]->(sol:Solution) "
        "RETURN i.id, i.title, i.severity, i.status, i.timestamp, i.description, "
        "s.id, s.name, sol.id, sol.summary, sol.steps, sol.reference",
        {"id": incident_id},
    )
    if not rows:
        return None
    columns = [
        "id", "title", "severity", "status", "timestamp", "description",
        "service_id", "service_name", "solution_id", "solution_summary",
        "solution_steps", "solution_reference",
    ]
    services, solution = [], None
    first = None
    for row in rows:
        record = dict(zip(columns, row))
        first = first or record
        if record["service_name"] and record["service_name"] not in services:
            services.append(record["service_name"])
        if record["solution_id"] and solution is None:
            solution = {
                "id": record["solution_id"],
                "summary": record["solution_summary"],
                "steps": record["solution_steps"],
                "reference": record["solution_reference"],
            }
    return {
        "id": first["id"],
        "title": first["title"],
        "severity": first["severity"],
        "status": first["status"],
        "timestamp": first["timestamp"],
        "description": first["description"],
        "services": services,
        "solution": solution,
    }


def get_owner(service_name):
    rows, _ = _query(
        "MATCH (s:Service) WHERE toLower(s.name) = toLower($name) "
        "OPTIONAL MATCH (p:Person)-[:OWNS]->(s) "
        "OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team) "
        "RETURN DISTINCT p.name, p.role, t.name",
        {"name": service_name},
    )
    return _rows_to_dicts(rows, ["name", "role", "team"])


def get_incidents_for_service(service_name):
    rows, _ = _query(
        "MATCH (i:Incident)-[:AFFECTS]->(s:Service) "
        "WHERE toLower(s.name) = toLower($name) "
        "RETURN i.id, i.title, i.severity, i.status, i.timestamp "
        "ORDER BY i.timestamp DESC",
        {"name": service_name},
    )
    return _rows_to_dicts(rows, ["id", "title", "severity", "status", "timestamp"])


def get_solutions_for_service(service_name):
    rows, _ = _query(
        "MATCH (i:Incident)-[:AFFECTS]->(s:Service) "
        "MATCH (i)-[:FIXED_BY]->(sol:Solution) "
        "WHERE toLower(s.name) = toLower($name) "
        "RETURN i.id, sol.id, sol.summary, sol.steps, sol.reference",
        {"name": service_name},
    )
    return _rows_to_dicts(
        rows, ["incident_id", "solution_id", "summary", "steps", "reference"]
    )


def get_dependencies(service_name, depth=DEFAULT_DEPTH):
    """Services that ``service_name`` transitively depends on."""
    depth = _clamp_depth(depth)
    rows, _ = _query(
        "MATCH (origin:Service) WHERE toLower(origin.name) = toLower($name) "
        f"MATCH (origin)-[:DEPENDS_ON*1..{depth}]->(dep:Service) "
        "RETURN DISTINCT dep.id, dep.name, dep.status",
        {"name": service_name},
    )
    return _rows_to_dicts(rows, ["id", "name", "status"])


def get_dependents(service_name, depth=DEFAULT_DEPTH):
    """Services that transitively depend on ``service_name`` (impact side)."""
    depth = _clamp_depth(depth)
    rows, _ = _query(
        "MATCH (origin:Service) WHERE toLower(origin.name) = toLower($name) "
        f"MATCH (dependent:Service)-[:DEPENDS_ON*1..{depth}]->(origin) "
        "RETURN DISTINCT dependent.id, dependent.name, dependent.status",
        {"name": service_name},
    )
    return _rows_to_dicts(rows, ["id", "name", "status"])


def get_blast_radius(service_name, depth=DEFAULT_DEPTH):
    """Origin service plus all consumers that could be affected by its failure."""
    origin = get_service(service_name)
    if not origin:
        return None
    dependents = get_dependents(service_name, depth)
    return {"origin": origin, "affected": dependents}


def get_incident_path(incident_id):
    """Return affected service and its direct dependency edges (for highlighting)."""
    rows, _ = _query(
        "MATCH (i:Incident {id: $id})-[:AFFECTS]->(s:Service) "
        "OPTIONAL MATCH (s)-[d:DEPENDS_ON]->(t:Service) "
        "RETURN s.id, s.name, t.id, t.name",
        {"id": incident_id},
    )
    if not rows:
        return None
    service_ids, edges = set(), []
    first = rows[0]
    service_ids.add(first[0])
    for s_id, s_name, t_id, t_name in rows:
        service_ids.add(s_id)
        if t_id:
            service_ids.add(t_id)
            edges.append({"from": s_id, "to": t_id})
    return {"service_ids": sorted(service_ids), "edges": edges}


def get_topology(entity_types=None):
    """Return nodes and edges for the topology view.

    ``entity_types`` is an optional set of labels to include
    (Service, Incident, Person, Project, Solution, Team).
    """
    allowed = {"Service", "Incident", "Person", "Project", "Solution", "Team"}
    selected = allowed if not entity_types else (allowed & set(entity_types))
    if not selected:
        selected = allowed

    node_rows, _ = _query(
        "MATCH (n) WHERE any(l IN labels(n) WHERE l IN $types) "
        "RETURN n.id, head([l IN labels(n) WHERE l IN $types]), "
        "coalesce(n.name, n.title, n.summary, n.id), "
        "coalesce(n.status, n.severity, n.role, '') "
        f"LIMIT {ROW_LIMIT}",
        {"types": sorted(selected)},
    )
    nodes = [
        {"id": r[0], "label": r[1], "title": r[2], "detail": r[3]}
        for r in node_rows if r[0]
    ]
    node_ids = {n["id"] for n in nodes}

    edge_rows, _ = _query(
        "MATCH (a)-[r]->(b) RETURN a.id, type(r), b.id "
        f"LIMIT {ROW_LIMIT}",
    )
    edges = [
        {"from": a, "type": rel, "to": b}
        for a, rel, b in edge_rows
        if a in node_ids and b in node_ids
    ]
    return {"nodes": nodes, "edges": edges}


def get_node_details(node_id):
    """Return a single node's label, display title and all properties."""
    rows, _ = _query(
        "MATCH (n {id: $id}) "
        "RETURN head(labels(n)), coalesce(n.name, n.title, n.summary, n.id), properties(n) "
        "LIMIT 1",
        {"id": node_id},
    )
    if not rows:
        return None
    label, title, props = rows[0]
    return {"id": node_id, "label": label, "title": title, "properties": props or {}}


def summary_counts():
    rows, _ = _query("MATCH (n) RETURN count(n)")
    node_count = rows[0][0] if rows else 0
    rows, _ = _query("MATCH ()-[r]->() RETURN count(r)")
    rel_count = rows[0][0] if rows else 0
    return {"nodes": node_count, "relationships": rel_count}


# --------------------------------------------------------------------------
# Cypher templates surfaced in the Cypher Lab view.
# --------------------------------------------------------------------------
QUERY_TEMPLATES = {
    "owner_of_service": {
        "title": "Who owns a service",
        "description": "Find the person and team that own a service.",
        "param": "service",
        "columns": ["name", "role", "team"],
        "cypher": (
            "MATCH (s:Service) WHERE toLower(s.name) = toLower($name)\n"
            "OPTIONAL MATCH (p:Person)-[:OWNS]->(s)\n"
            "OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team)\n"
            "RETURN DISTINCT p.name, p.role, t.name"
        ),
    },
    "incidents_for_service": {
        "title": "Incidents affecting a service",
        "description": "List incidents connected to a service via AFFECTS.",
        "param": "service",
        "columns": ["id", "title", "severity", "status", "timestamp"],
        "cypher": (
            "MATCH (i:Incident)-[:AFFECTS]->(s:Service)\n"
            "WHERE toLower(s.name) = toLower($name)\n"
            "RETURN i.id, i.title, i.severity, i.status, i.timestamp\n"
            "ORDER BY i.timestamp DESC"
        ),
    },
    "solution_for_service": {
        "title": "Recorded solutions",
        "description": "Solutions linked to incidents that affected a service.",
        "param": "service",
        "columns": ["incident_id", "solution_id", "summary", "steps", "reference"],
        "cypher": (
            "MATCH (i:Incident)-[:AFFECTS]->(s:Service)\n"
            "MATCH (i)-[:FIXED_BY]->(sol:Solution)\n"
            "WHERE toLower(s.name) = toLower($name)\n"
            "RETURN i.id, sol.id, sol.summary, sol.steps, sol.reference"
        ),
    },
    "dependencies": {
        "title": "Service dependencies (bounded)",
        "description": "Transitive DEPENDS_ON relationships up to a depth limit.",
        "param": "service",
        "columns": ["id", "name", "status"],
        "cypher": (
            "MATCH (origin:Service) WHERE toLower(origin.name) = toLower($name)\n"
            "MATCH (origin)-[:DEPENDS_ON*1..N]->(dep:Service)\n"
            "RETURN DISTINCT dep.id, dep.name, dep.status"
        ),
    },
    "blast_radius": {
        "title": "Blast radius",
        "description": "Services that transitively depend on an origin service.",
        "param": "service",
        "columns": ["id", "name", "status"],
        "cypher": (
            "MATCH (origin:Service) WHERE toLower(origin.name) = toLower($name)\n"
            "MATCH (dependent:Service)-[:DEPENDS_ON*1..N]->(origin)\n"
            "RETURN DISTINCT dependent.id, dependent.name, dependent.status"
        ),
    },
    "incident_investigation": {
        "title": "Incident investigation",
        "description": "Incident, affected service, owner and recorded solution.",
        "param": "incident",
        "columns": ["id", "title", "severity", "service", "owner", "solution"],
        "cypher": (
            "MATCH (i:Incident {id: $id})-[:AFFECTS]->(s:Service)\n"
            "OPTIONAL MATCH (p:Person)-[:OWNS]->(s)\n"
            "OPTIONAL MATCH (i)-[:FIXED_BY]->(sol:Solution)\n"
            "RETURN i.id, i.title, i.severity, s.name, p.name, sol.summary"
        ),
    },
}


def run_template(template_key, params, depth=DEFAULT_DEPTH):
    """Execute a named read-only template and return rows with timing.

    Used by the Cypher Lab view so the user sees the exact Cypher,
    parameters, retrieved entities and measured duration.
    """
    template = QUERY_TEMPLATES[template_key]
    cypher = template["cypher"]
    if "..N" in cypher:
        cypher = cypher.replace("..N", f"..{_clamp_depth(depth)}")
    rows, run_time_ms = _query(cypher, params)
    columns = template["columns"]
    return {
        "title": template["title"],
        "cypher": cypher,
        "params": params,
        "columns": columns,
        "rows": _rows_to_dicts(rows, columns),
        "run_time_ms": run_time_ms,
    }
