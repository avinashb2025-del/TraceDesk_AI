"""Synthetic demo data for the TraceDesk AI knowledge graph.

The dataset is entirely fictional and safe to commit. It is designed to make
graph traversal meaningful: multiple services with real dependency chains,
owners, teams, projects, incidents and recorded solutions.

Running this script repeatedly is safe. Every entity is created with MERGE on a
stable ``id`` and every relationship is merged, so no duplicate demo records
are produced.
"""

from db import get_graph


PEOPLE = [
    {"id": "P-MAYA", "name": "Maya", "role": "Backend Engineer", "team": "Payments Team"},
    {"id": "P-DEV", "name": "Dev", "role": "Frontend Engineer", "team": "Payments Team"},
    {"id": "P-LEO", "name": "Leo", "role": "Platform Engineer", "team": "Platform Team"},
    {"id": "P-SARA", "name": "Sara", "role": "Data Engineer", "team": "Platform Team"},
    {"id": "P-NINA", "name": "Nina", "role": "Site Reliability Engineer", "team": "SRE Team"},
    {"id": "P-OMAR", "name": "Omar", "role": "Backend Engineer", "team": "Platform Team"},
]

TEAMS = [
    {"id": "T-PAYMENTS", "name": "Payments Team"},
    {"id": "T-PLATFORM", "name": "Platform Team"},
    {"id": "T-SRE", "name": "SRE Team"},
]

SERVICES = [
    {"id": "S-PAYMENTS-API", "name": "Payments API", "env": "prod", "status": "degraded"},
    {"id": "S-CHECKOUT-WEB", "name": "Checkout Web", "env": "prod", "status": "healthy"},
    {"id": "S-ORDERS", "name": "Orders Service", "env": "prod", "status": "healthy"},
    {"id": "S-INVENTORY", "name": "Inventory Service", "env": "prod", "status": "healthy"},
    {"id": "S-NOTIFICATIONS", "name": "Notification Service", "env": "prod", "status": "healthy"},
    {"id": "S-AUTH", "name": "Auth Service", "env": "prod", "status": "healthy"},
    {"id": "S-PAYMENTS-DB", "name": "Payments DB", "env": "prod", "status": "degraded"},
    {"id": "S-REDIS", "name": "Redis Cache", "env": "prod", "status": "healthy"},
    {"id": "S-ORDERS-DB", "name": "Orders DB", "env": "prod", "status": "healthy"},
]

PROJECTS = [
    {"id": "PR-CHECKOUT", "name": "Checkout Platform", "status": "active",
     "description": "Customer-facing checkout and payments experience."},
    {"id": "PR-PAYMENTS-MOD", "name": "Payments Modernization", "status": "active",
     "description": "Migrate payment processing to a resilient connection model."},
    {"id": "PR-RELIABILITY", "name": "Reliability Initiative", "status": "active",
     "description": "Improve availability of shared infrastructure services."},
]

INCIDENTS = [
    {
        "id": "INC-101",
        "title": "Payment requests timing out",
        "severity": "High",
        "status": "Investigating",
        "timestamp": "2026-10-14T09:12:00Z",
        "description": "Elevated 504 responses observed on the Payments API.",
    },
    {
        "id": "INC-102",
        "title": "Checkout page latency above SLO",
        "severity": "Medium",
        "status": "Resolved",
        "timestamp": "2026-10-10T14:05:00Z",
        "description": "Checkout Web p95 latency above the 800ms objective.",
    },
    {
        "id": "INC-103",
        "title": "Inventory sync failures for SKU batches",
        "severity": "Medium",
        "status": "Monitoring",
        "timestamp": "2026-10-12T11:40:00Z",
        "description": "Scheduled inventory sync jobs failing intermittently.",
    },
    {
        "id": "INC-104",
        "title": "Auth token refresh errors spike",
        "severity": "Critical",
        "status": "Resolved",
        "timestamp": "2026-10-08T18:22:00Z",
        "description": "Login sessions dropped after token refresh failures.",
    },
    {
        "id": "INC-105",
        "title": "Redis memory pressure warning",
        "severity": "Low",
        "status": "Resolved",
        "timestamp": "2026-10-05T07:30:00Z",
        "description": "Cache node reported sustained high memory usage.",
    },
]

SOLUTIONS = [
    {
        "id": "SOL-101",
        "summary": "Review connection pool limits and ensure connections are released.",
        "steps": (
            "Check the Payments DB connection pool maximum.\n"
            "Inspect application logs for leaked or unreleased connections.\n"
            "Confirm idle connections are returned to the pool after each request."
        ),
        "reference": "runbooks/payments-connection-pool.md",
    },
    {
        "id": "SOL-102",
        "summary": "Increase checkout cache TTL and warm the product catalog.",
        "steps": (
            "Raise the catalog cache TTL to reduce origin load.\n"
            "Pre-warm the cache after each deployment."
        ),
        "reference": "runbooks/checkout-latency.md",
    },
    {
        "id": "SOL-103",
        "summary": "Reprocess failed inventory sync jobs and backfill SKU batches.",
        "steps": (
            "Identify the failed sync batch window.\n"
            "Replay the failed jobs from the queue.\n"
            "Verify SKU counts reconcile."
        ),
        "reference": "runbooks/inventory-sync.md",
    },
    {
        "id": "SOL-104",
        "summary": "Roll the JWT signing key and restart auth replicas.",
        "steps": (
            "Rotate the JWT signing key.\n"
            "Restart auth replicas one at a time.\n"
            "Confirm refresh success rate recovers."
        ),
        "reference": "runbooks/auth-token-refresh.md",
    },
    {
        "id": "SOL-105",
        "summary": "Tune Redis maxmemory-policy and evict stale keys.",
        "steps": (
            "Set an appropriate maxmemory-policy.\n"
            "Evict stale keys and review key expiry settings."
        ),
        "reference": "runbooks/redis-memory.md",
    },
]

# (from_service_id, to_service_id) meaning FROM depends on TO.
DEPENDENCIES = [
    ("S-CHECKOUT-WEB", "S-PAYMENTS-API"),
    ("S-CHECKOUT-WEB", "S-ORDERS"),
    ("S-CHECKOUT-WEB", "S-AUTH"),
    ("S-PAYMENTS-API", "S-PAYMENTS-DB"),
    ("S-PAYMENTS-API", "S-REDIS"),
    ("S-PAYMENTS-API", "S-AUTH"),
    ("S-ORDERS", "S-INVENTORY"),
    ("S-ORDERS", "S-ORDERS-DB"),
    ("S-ORDERS", "S-AUTH"),
    ("S-INVENTORY", "S-ORDERS-DB"),
    ("S-NOTIFICATIONS", "S-AUTH"),
]

# person_id owns service_id
OWNERSHIP = [
    ("P-MAYA", "S-PAYMENTS-API"),
    ("P-DEV", "S-CHECKOUT-WEB"),
    ("P-LEO", "S-ORDERS"),
    ("P-LEO", "S-INVENTORY"),
    ("P-SARA", "S-PAYMENTS-DB"),
    ("P-SARA", "S-ORDERS-DB"),
    ("P-NINA", "S-REDIS"),
    ("P-NINA", "S-AUTH"),
    ("P-OMAR", "S-NOTIFICATIONS"),
]

# person_id, project_id
WORKED_ON = [
    ("P-MAYA", "PR-CHECKOUT"),
    ("P-MAYA", "PR-PAYMENTS-MOD"),
    ("P-DEV", "PR-CHECKOUT"),
    ("P-LEO", "PR-CHECKOUT"),
    ("P-LEO", "PR-RELIABILITY"),
    ("P-SARA", "PR-PAYMENTS-MOD"),
    ("P-NINA", "PR-RELIABILITY"),
]

# person_id, team_id
MEMBERSHIP = [
    ("P-MAYA", "T-PAYMENTS"),
    ("P-DEV", "T-PAYMENTS"),
    ("P-LEO", "T-PLATFORM"),
    ("P-SARA", "T-PLATFORM"),
    ("P-OMAR", "T-PLATFORM"),
    ("P-NINA", "T-SRE"),
]

# project_id, service_id
PROJECT_USES = [
    ("PR-CHECKOUT", "S-CHECKOUT-WEB"),
    ("PR-CHECKOUT", "S-PAYMENTS-API"),
    ("PR-CHECKOUT", "S-ORDERS"),
    ("PR-PAYMENTS-MOD", "S-PAYMENTS-API"),
    ("PR-PAYMENTS-MOD", "S-PAYMENTS-DB"),
    ("PR-RELIABILITY", "S-REDIS"),
    ("PR-RELIABILITY", "S-AUTH"),
]

# incident_id, service_id
INCIDENT_AFFECTS = [
    ("INC-101", "S-PAYMENTS-API"),
    ("INC-102", "S-CHECKOUT-WEB"),
    ("INC-103", "S-INVENTORY"),
    ("INC-104", "S-AUTH"),
    ("INC-105", "S-REDIS"),
]

# incident_id, solution_id
INCIDENT_FIXED_BY = [
    ("INC-101", "SOL-101"),
    ("INC-102", "SOL-102"),
    ("INC-103", "SOL-103"),
    ("INC-104", "SOL-104"),
    ("INC-105", "SOL-105"),
]


def _merge_nodes(graph, label, records, props):
    query = f"MERGE (n:{label} {{id: $id}}) SET " + ", ".join(
        f"n.{key} = ${key}" for key in props
    )
    for record in records:
        graph.query(query, record)


def _merge_relationship(graph, from_label, from_id, rel_type, to_label, to_id):
    query = (
        f"MATCH (a:{from_label} {{id: $from_id}}) "
        f"MATCH (b:{to_label} {{id: $to_id}}) "
        f"MERGE (a)-[:{rel_type}]->(b)"
    )
    graph.query(query, {"from_id": from_id, "to_id": to_id})


def seed():
    """Load (or refresh) the synthetic TraceDesk graph. Safe to re-run."""
    graph = get_graph()

    _merge_nodes(graph, "Person", PEOPLE, ["name", "role", "team"])
    _merge_nodes(graph, "Team", TEAMS, ["name"])
    _merge_nodes(graph, "Service", SERVICES, ["name", "env", "status"])
    _merge_nodes(graph, "Project", PROJECTS, ["name", "status", "description"])
    _merge_nodes(
        graph,
        "Incident",
        INCIDENTS,
        ["title", "severity", "status", "timestamp", "description"],
    )
    _merge_nodes(graph, "Solution", SOLUTIONS, ["summary", "steps", "reference"])

    for person_id, team_id in MEMBERSHIP:
        _merge_relationship(graph, "Person", person_id, "MEMBER_OF", "Team", team_id)

    for person_id, service_id in OWNERSHIP:
        _merge_relationship(graph, "Person", person_id, "OWNS", "Service", service_id)

    for person_id, project_id in WORKED_ON:
        _merge_relationship(graph, "Person", person_id, "WORKED_ON", "Project", project_id)

    for project_id, service_id in PROJECT_USES:
        _merge_relationship(graph, "Project", project_id, "USES", "Service", service_id)

    for from_id, to_id in DEPENDENCIES:
        _merge_relationship(graph, "Service", from_id, "DEPENDS_ON", "Service", to_id)

    for incident_id, service_id in INCIDENT_AFFECTS:
        _merge_relationship(
            graph, "Incident", incident_id, "AFFECTS", "Service", service_id
        )

    for incident_id, solution_id in INCIDENT_FIXED_BY:
        _merge_relationship(
            graph, "Incident", incident_id, "FIXED_BY", "Solution", solution_id
        )

    return {
        "people": len(PEOPLE),
        "teams": len(TEAMS),
        "services": len(SERVICES),
        "projects": len(PROJECTS),
        "incidents": len(INCIDENTS),
        "solutions": len(SOLUTIONS),
        "dependencies": len(DEPENDENCIES),
    }


if __name__ == "__main__":
    stats = seed()
    print("TraceDesk knowledge graph seeded (idempotent).")
    for key, value in stats.items():
        print(f"  {key}: {value}")
