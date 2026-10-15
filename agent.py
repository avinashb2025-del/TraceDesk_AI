"""Graph-grounded question answering for TraceDesk AI.

The agent classifies a question, identifies the entities it mentions, selects a
read-only graph query, and builds an answer strictly from what FalkorDB returns.
It never invents root causes, metrics or historical incidents: when the graph
does not contain supporting evidence it says so explicitly.
"""

import re

import query_graph as q
from db import GraphUnavailableError


INCIDENT_ID_RE = re.compile(r"INC-\d+", re.IGNORECASE)

NO_GRAPH = (
    "I could not reach the FalkorDB graph, so I cannot provide a grounded "
    "answer right now. Check that the database is running and try again."
)


# --------------------------------------------------------------------------
# Entity extraction
# --------------------------------------------------------------------------
def find_services(question):
    """Return service dicts mentioned in the question (case-insensitive)."""
    q_lower = question.lower()
    services = q.list_services()
    direct = [s for s in services if s["name"] and s["name"].lower() in q_lower]
    if direct:
        return direct

    # Fallback: match on the distinctive words of a service name (e.g. "payments").
    tokens = set(re.findall(r"[a-z]+", q_lower))
    scored = []
    for service in services:
        words = set(re.findall(r"[a-z]+", (service["name"] or "").lower()))
        words -= {"service", "api", "db", "cache", "web"}
        if words and words <= tokens:
            scored.append((len(words), service))
    if len({s["id"] for _, s in scored}) == 1:
        return [scored[0][1]]
    return []


def find_incident_ids(question):
    return sorted({m.group(0).upper() for m in INCIDENT_ID_RE.finditer(question)})


def _detect_project(question):
    q_lower = question.lower()
    for project in q.list_projects():
        if project["name"] and project["name"].lower() in q_lower:
            return project
    return None


# --------------------------------------------------------------------------
# Intent classification
# --------------------------------------------------------------------------
def classify_intent(question, services, incident_ids):
    q_lower = question.lower()

    if incident_ids or any(
        kw in q_lower
        for kw in ("investigate", "root cause", "what caused", "why did", "triage", "what should i check")
    ):
        return "investigate"

    if any(kw in q_lower for kw in ("blast radius", "what else is affected", "what else", "impact of", "downstream impact")):
        return "blast_radius"

    if any(kw in q_lower for kw in ("who owns", "owner", "owns", "on-call", "on call", "oncall", "maintained by", "who maintains")):
        return "owner"

    if any(kw in q_lower for kw in ("solution", "runbook", "how do", "how to fix", "remedy", "remediate", "what fixed", "resolution")):
        return "solution"

    if any(kw in q_lower for kw in ("depend", "dependency", "dependencies", "downstream", "upstream", "rely", "relies")):
        return "dependencies"

    if any(kw in q_lower for kw in ("incident", "outage", "what happened", "affected by", "problem", "issue", "failure", "failed")):
        return "incidents"

    if any(kw in q_lower for kw in ("list all", "list services", "what services", "all services", "which services",
                                    "list incidents", "all incidents", "which incidents", "overview", "topology")):
        return "list"

    if services:
        return "investigate"

    return "unknown"


# --------------------------------------------------------------------------
# Evidence helpers
# --------------------------------------------------------------------------
def _evidence(title, template_key, params, rows, columns, run_time_ms=None):
    template = q.QUERY_TEMPLATES.get(template_key, {})
    return {
        "title": title,
        "template": template_key,
        "cypher": template.get("cypher", ""),
        "params": params,
        "columns": columns,
        "rows": rows,
        "run_time_ms": run_time_ms,
    }


def _response(intent, answer, **extra):
    response = {
        "answer": answer,
        "intent": intent,
        "entities": extra.get("entities", {}),
        "relationships": extra.get("relationships", []),
        "evidence": extra.get("evidence", []),
        "suggested_actions": extra.get("suggested_actions", []),
        "limitations": extra.get("limitations", []),
        "status": extra.get("status", "ok"),
    }
    return response


def _no_result(intent, message, entities=None):
    return _response(
        intent,
        message,
        entities=entities or {},
        status="no_result",
        suggested_actions=[
            "Try naming a service such as 'Payments API' or an incident such as 'INC-101'.",
            "Open the Graph Explorer to browse what exists in the graph.",
        ],
    )


# --------------------------------------------------------------------------
# Intent handlers
# --------------------------------------------------------------------------
def _handle_owner(services, question):
    if not services:
        return _no_result("owner", "I couldn't identify which service you mean. Which service should I check the owner for?")
    service = services[0]
    owners = q.get_owner(service["name"])
    evidence = [
        _evidence(
            f"Owners of {service['name']}",
            "owner_of_service",
            {"name": service["name"]},
            owners,
            ["name", "role", "team"],
        )
    ]
    if not owners:
        return _response(
            "owner",
            f"The graph has no owner recorded for **{service['name']}**.",
            entities={"service": service["name"]},
            evidence=evidence,
            status="no_result",
            limitations=["No OWNS relationship exists for this service."],
        )
    lines = [f"**{service['name']}** is owned by:"]
    relationships = []
    for owner in owners:
        team = f" ({owner['team']})" if owner.get("team") else ""
        role = f", {owner['role']}" if owner.get("role") else ""
        lines.append(f"- **{owner['name']}**{role}{team}")
        relationships.append({"from": owner["name"], "type": "OWNS", "to": service["name"]})
    return _response(
        "owner",
        "\n".join(lines),
        entities={"service": service["name"]},
        relationships=relationships,
        evidence=evidence,
        suggested_actions=[
            f"Ask which incidents affected {service['name']}.",
            f"Ask what depends on {service['name']}.",
        ],
    )


def _handle_incidents(services):
    if not services:
        return _no_result("incidents", "I couldn't identify which service you mean. Which service should I look up incidents for?")
    service = services[0]
    incidents = q.get_incidents_for_service(service["name"])
    evidence = [
        _evidence(
            f"Incidents affecting {service['name']}",
            "incidents_for_service",
            {"name": service["name"]},
            incidents,
            ["id", "title", "severity", "status", "timestamp"],
        )
    ]
    if not incidents:
        return _response(
            "incidents",
            f"No incidents are recorded for **{service['name']}** in the graph.",
            entities={"service": service["name"]},
            evidence=evidence,
            status="no_result",
        )
    lines = [f"Incidents connected to **{service['name']}** via `AFFECTS`:"]
    relationships = []
    for inc in incidents:
        lines.append(
            f"- `{inc['id']}` — {inc['title']} · severity **{inc['severity']}** · status {inc['status']} · {inc['timestamp']}"
        )
        relationships.append({"from": inc["id"], "type": "AFFECTS", "to": service["name"]})
    return _response(
        "incidents",
        "\n".join(lines),
        entities={"service": service["name"]},
        relationships=relationships,
        evidence=evidence,
        suggested_actions=[f"Ask to investigate {incidents[0]['id']}."],
    )


def _handle_solution(services, question):
    if not services:
        return _no_result("solution", "I couldn't identify which service you mean. Which service should I look up solutions for?")
    service = services[0]
    solutions = q.get_solutions_for_service(service["name"])
    evidence = [
        _evidence(
            f"Solutions linked to {service['name']}",
            "solution_for_service",
            {"name": service["name"]},
            solutions,
            ["incident_id", "solution_id", "summary", "steps", "reference"],
        )
    ]
    if not solutions:
        return _response(
            "solution",
            f"No recorded solution is connected to **{service['name']}** in the graph.",
            entities={"service": service["name"]},
            evidence=evidence,
            status="no_result",
            limitations=["No incident affecting this service has a FIXED_BY relationship."],
        )
    lines = [f"Recorded solutions for **{service['name']}**:"]
    relationships = []
    for sol in solutions:
        lines.append(f"\n**{sol['solution_id']}** (from `{sol['incident_id']}`): {sol['summary']}")
        if sol.get("steps"):
            for step in str(sol["steps"]).splitlines():
                if step.strip():
                    lines.append(f"  1. {step.strip()}")
        if sol.get("reference"):
            lines.append(f"  Reference: `{sol['reference']}`")
        relationships.append({"from": sol["incident_id"], "type": "FIXED_BY", "to": sol["solution_id"]})
    return _response(
        "solution",
        "\n".join(lines),
        entities={"service": service["name"]},
        relationships=relationships,
        evidence=evidence,
        suggested_actions=[f"Ask for the blast radius of {service['name']}."],
        limitations=["These are recorded historical remediations, not a validated fix for a new incident."],
    )


def _handle_dependencies(services):
    if not services:
        return _no_result("dependencies", "I couldn't identify which service you mean. Which service's dependencies should I trace?")
    service = services[0]
    deps = q.get_dependencies(service["name"])
    evidence = [
        _evidence(
            f"Dependencies of {service['name']}",
            "dependencies",
            {"name": service["name"]},
            deps,
            ["id", "name", "status"],
        )
    ]
    if not deps:
        return _response(
            "dependencies",
            f"**{service['name']}** has no recorded `DEPENDS_ON` relationships.",
            entities={"service": service["name"]},
            evidence=evidence,
            status="no_result",
        )
    lines = [f"**{service['name']}** depends on (bounded traversal):"]
    relationships = []
    for dep in deps:
        status = f" · {dep['status']}" if dep.get("status") else ""
        lines.append(f"- {dep['name']}{status}")
        relationships.append({"from": service["name"], "type": "DEPENDS_ON", "to": dep["name"]})
    return _response(
        "dependencies",
        "\n".join(lines),
        entities={"service": service["name"]},
        relationships=relationships,
        evidence=evidence,
        suggested_actions=[f"Ask for the blast radius of {service['name']}."],
    )


def _handle_blast_radius(services):
    if not services:
        return _no_result("blast_radius", "I couldn't identify which service you mean. Which service's blast radius should I compute?")
    service = services[0]
    radius = q.get_blast_radius(service["name"])
    if radius is None:
        return _no_result("blast_radius", f"**{service['name']}** is not present in the graph.")
    affected = radius["affected"]
    evidence = [
        _evidence(
            f"Blast radius from {service['name']}",
            "blast_radius",
            {"name": service["name"]},
            affected,
            ["id", "name", "status"],
        )
    ]
    lines = [f"If **{service['name']}** degrades, the graph shows these consumers in the impact path:"]
    relationships = []
    if affected:
        for svc in affected:
            status = f" · {svc['status']}" if svc.get("status") else ""
            lines.append(f"- {svc['name']}{status}")
            relationships.append({"from": svc["name"], "type": "DEPENDS_ON", "to": service["name"]})
    else:
        lines.append("- No services depend on it in the recorded graph.")
    return _response(
        "blast_radius",
        "\n".join(lines),
        entities={"service": service["name"]},
        relationships=relationships,
        evidence=evidence,
        limitations=["Blast radius is limited to recorded `DEPENDS_ON` edges within the traversal depth."],
    )


def _handle_list():
    services = q.list_services()
    incidents = q.list_incidents()
    evidence = [
        _evidence("All services", "list", {}, services, ["id", "name", "env", "status"]),
    ]
    lines = ["**Services in the graph:**"]
    for svc in services:
        lines.append(f"- {svc['name']} ({svc['env']}, {svc['status']})")
    lines.append("\n**Incidents in the graph:**")
    for inc in incidents:
        target = ", ".join(inc["services"]) if inc["services"] else "unlinked"
        lines.append(f"- `{inc['id']}` {inc['title']} — {inc['severity']} · affects {target}")
    return _response(
        "list",
        "\n".join(lines),
        evidence=evidence,
        suggested_actions=["Ask to investigate INC-101.", "Ask who owns the Payments API."],
    )


def build_investigation(incident_id):
    """Return a full, evidence-backed investigation for one incident.

    Used by both the agent's ``investigate`` intent and the Incident Triage view.
    """
    incident = q.get_incident(incident_id)
    if incident is None:
        return None

    evidence = [
        _evidence(
            f"Incident {incident_id} details",
            "incident_investigation",
            {"id": incident_id},
            [
                {
                    "id": incident["id"],
                    "title": incident["title"],
                    "severity": incident["severity"],
                    "status": incident["status"],
                    "timestamp": incident["timestamp"],
                    "services": ", ".join(incident["services"]),
                }
            ],
            ["id", "title", "severity", "status", "timestamp", "services"],
        )
    ]

    owners, dependencies, blast, solutions = [], [], [], []
    for service_name in incident["services"]:
        for owner in q.get_owner(service_name):
            owners.append({"service": service_name, **owner})
        dependencies.append(
            {"service": service_name, "deps": q.get_dependencies(service_name)}
        )
        radius = q.get_blast_radius(service_name)
        if radius:
            blast.append(radius)
        for sol in q.get_solutions_for_service(service_name):
            solutions.append(sol)

    if incident["solution"]:
        solutions.append(
            {
                "incident_id": incident["id"],
                "solution_id": incident["solution"]["id"],
                "summary": incident["solution"]["summary"],
                "steps": incident["solution"]["steps"],
                "reference": incident["solution"]["reference"],
            }
        )

    # De-duplicate solutions that are reachable through both paths.
    deduped_solutions, seen_solutions = [], set()
    for sol in solutions:
        key = (sol.get("incident_id"), sol.get("solution_id"))
        if key not in seen_solutions:
            seen_solutions.add(key)
            deduped_solutions.append(sol)
    solutions = deduped_solutions

    if owners:
        evidence.append(
            _evidence(
                "Owners of affected services",
                "owner_of_service",
                {"services": incident["services"]},
                owners,
                ["service", "name", "role", "team"],
            )
        )
    if dependencies:
        dependency_rows = [
            {"service": d["service"], "dependency": dep["name"]}
            for d in dependencies
            for dep in d["deps"]
        ]
        if dependency_rows:
            evidence.append(
                _evidence(
                    "Dependencies of affected services",
                    "dependencies",
                    {"services": incident["services"]},
                    dependency_rows,
                    ["service", "dependency"],
                )
            )

    relationships = []
    for service_name in incident["services"]:
        relationships.append({"from": incident_id, "type": "AFFECTS", "to": service_name})
    for owner in owners:
        relationships.append({"from": owner["name"], "type": "OWNS", "to": owner["service"]})
    if incident["solution"]:
        relationships.append({"from": incident_id, "type": "FIXED_BY", "to": incident["solution"]["id"]})

    # Recommended steps come from recorded solutions, never invented.
    recommended_steps = []
    for sol in solutions:
        if sol.get("steps"):
            for step in str(sol["steps"]).splitlines():
                step = step.strip()
                if step and step not in recommended_steps:
                    recommended_steps.append(step)

    # A hypothesis is only offered as a hypothesis, grounded in the recorded fix.
    hypothesis = None
    if incident["solution"]:
        hypothesis = {
            "statement": incident["solution"]["summary"],
            "basis": (
                "This is the remediation recorded against this incident in the graph; "
                "it is a hypothesis about the cause, not a confirmed root cause."
            ),
        }
    else:
        hypothesis = {
            "statement": "No recorded remediation exists, so no evidence-based hypothesis can be formed.",
            "basis": "The incident has no FIXED_BY relationship in the graph.",
        }

    timeline = []
    if incident.get("timestamp"):
        timeline.append({"time": incident["timestamp"], "event": f"{incident['id']} raised: {incident['title']}"})

    limitations = [
        "Root-cause statements are hypotheses derived from recorded remediations, not confirmed findings.",
        "No telemetry, logs or live metrics are available in this graph; only recorded relationships are used.",
    ]
    if not owners:
        limitations.append("No owner is recorded for the affected services.")
    if not solutions:
        limitations.append("No solution is recorded for this incident.")

    return {
        "incident": incident,
        "owners": owners,
        "dependencies": dependencies,
        "blast_radius": blast,
        "solutions": solutions,
        "recommended_steps": recommended_steps,
        "hypothesis": hypothesis,
        "timeline": timeline,
        "relationships": relationships,
        "evidence": evidence,
        "limitations": limitations,
    }


def _handle_investigate(services, incident_ids):
    if incident_ids:
        investigation = build_investigation(incident_ids[0])
        if investigation is None:
            return _no_result(
                "investigate",
                f"I could not find incident `{incident_ids[0]}` in the graph.",
                entities={"incident": incident_ids[0]},
            )
        incident = investigation["incident"]
        lines = [
            f"### `{incident['id']}` — {incident['title']}",
            f"**Severity:** {incident['severity']} · **Status:** {incident['status']} · **Raised:** {incident['timestamp']}",
        ]
        if incident["services"]:
            lines.append(f"**Affected services:** {', '.join(incident['services'])}")
        if investigation["owners"]:
            owner_bits = [f"{o['name']} ({o['service']})" for o in investigation["owners"]]
            lines.append(f"**Owners:** {', '.join(owner_bits)}")
        if incident["solution"]:
            lines.append(f"**Recorded solution:** {incident['solution']['summary']}")
        if investigation["recommended_steps"]:
            lines.append("\n**Recommended next steps (from recorded runbooks):**")
            for step in investigation["recommended_steps"]:
                lines.append(f"- {step}")
        if investigation["hypothesis"]:
            lines.append(f"\n**Hypothesis:** {investigation['hypothesis']['statement']}")
            lines.append(f"_{investigation['hypothesis']['basis']}_")
        return _response(
            "investigate",
            "\n".join(lines),
            entities={"incident": incident["id"]},
            relationships=investigation["relationships"],
            evidence=investigation["evidence"],
            suggested_actions=[
                f"Open Incident Triage for {incident['id']}.",
                "Ask for the blast radius of the affected service.",
            ],
            limitations=investigation["limitations"],
        )

    if services:
        service = services[0]
        incidents = q.get_incidents_for_service(service["name"])
        if incidents:
            return _handle_investigate([], [incidents[0]["id"]])
        owners = q.get_owner(service["name"])
        deps = q.get_dependencies(service["name"])
        radius = q.get_blast_radius(service["name"]) or {"affected": []}
        lines = [f"### {service['name']} ({service['env']}, {service['status']})"]
        if owners:
            lines.append("**Owner:** " + ", ".join(o["name"] for o in owners))
        lines.append("**Incidents:** none recorded")
        if deps:
            lines.append("**Depends on:** " + ", ".join(d["name"] for d in deps))
        if radius["affected"]:
            lines.append("**Impact (consumers):** " + ", ".join(d["name"] for d in radius["affected"]))
        return _response(
            "investigate",
            "\n".join(lines),
            entities={"service": service["name"]},
            limitations=["No incident is recorded for this service, so no investigation path exists."],
        )

    return _no_result("investigate", "Tell me which incident or service to investigate, for example `INC-101` or `Payments API`.")


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------
def ask_agent(question):
    """Answer a question using the graph. Always returns a structured dict."""
    if not question or not question.strip():
        return _response(
            "unknown",
            "Ask a question about a service, incident, owner or solution.",
            status="no_result",
            suggested_actions=["Who owns the Payments API?", "Investigate INC-101."],
        )

    try:
        services = find_services(question)
        incident_ids = find_incident_ids(question)
    except GraphUnavailableError:
        return _response("error", NO_GRAPH, status="error")

    entities = {}
    if services:
        entities["services"] = [s["name"] for s in services]
    if incident_ids:
        entities["incidents"] = incident_ids
    project = _detect_project(question)
    if project:
        entities["project"] = project["name"]

    intent = classify_intent(question, services, incident_ids)

    try:
        if intent == "owner":
            return _handle_owner(services, question)
        if intent == "incidents":
            return _handle_incidents(services)
        if intent == "solution":
            return _handle_solution(services, question)
        if intent == "dependencies":
            return _handle_dependencies(services)
        if intent == "blast_radius":
            return _handle_blast_radius(services)
        if intent == "list":
            return _handle_list()
        if intent == "investigate":
            return _handle_investigate(services, incident_ids)
    except GraphUnavailableError:
        return _response("error", NO_GRAPH, status="error", entities=entities)

    return _no_result(
        "unknown",
        "I couldn't map that to a graph query. I can help with service owners, "
        "incidents, solutions, dependencies and blast radius.",
        entities=entities,
    )


def ask_agent_text(question):
    """Convenience wrapper returning the answer as plain markdown text."""
    return ask_agent(question)["answer"]


if __name__ == "__main__":
    print("TraceDesk AI is ready! Ask about an incident, service, owner or solution.")
    print("Type 'exit' to quit.")
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if question.lower() in ("exit", "quit"):
            print("TraceDesk AI: Goodbye!")
            break
        if not question:
            continue
        print("\nTraceDesk AI:\n" + ask_agent_text(question))
