# TraceDesk AI

**Graph-native incident reasoning engine** — built for the *Graph Hacks: Context for AI Agents* hackathon.

TraceDesk AI helps engineers answer the questions that matter during an outage:

> "Investigate the Payments API timeout. What caused it, which services are affected, who owns it, and what should I check first?"

Instead of generating plausible-sounding text, TraceDesk answers **only from evidence retrieved out of FalkorDB**. Every answer exposes the exact Cypher query, the parameters, the retrieved entities/relationships, and the query execution time. When the graph has no supporting information, TraceDesk says so.

---

## 1. Project overview

| | |
|---|---|
| **Name** | TraceDesk AI |
| **Purpose** | Graph-powered incident investigation assistant |
| **Graph database** | FalkorDB (Redis-based property graph) |
| **Query language** | Cypher (read-only for investigation) |
| **Frontend** | Streamlit + custom dark "cyber-ops" CSS |
| **Language** | Python 3.10+ |

---

## 2. Problem statement & why a graph

During an incident, the facts needed to reason about it are scattered across incidents, services, dependencies, owners, projects, runbooks and past fixes. Connecting those pieces by hand is slow and error-prone.

Incident knowledge is fundamentally **relational**: an incident *affects* a service, a service *depends on* other services, people *own* services, incidents *were fixed by* solutions. A property graph models these relationships directly, so a single traversal can assemble the full context (impact, ownership, history) that would otherwise require many joins or manual correlation.

TraceDesk uses FalkorDB as the **source of truth** for those relationships — not as decoration.

---

## 3. Features that actually work

All of the following are implemented and covered by tests.

**1. Query Console (chat)**
- Natural-language questions about services, incidents, owners, dependencies and solutions.
- Rule-based intent classification + entity recognition (no LLM API key required).
- Structured answers with supporting graph evidence, relationships used, suggested follow-up questions and explicit limitations.
- Browser-session conversation history; data-driven suggested-investigation cards, a loading indicator, and honest no-result and error states.

**2. Incident Triage**
- Incident ID, title, severity, status, timestamp, description.
- Affected services (`AFFECTS`), owners (`OWNS` + `MEMBER_OF`), recorded solution (`FIXED_BY`).
- Root-cause **hypothesis** derived from the recorded remediation and clearly labelled as a hypothesis, never a confirmed cause.
- Recommended diagnostic steps taken verbatim from recorded runbooks.
- Blast radius computed from dependency relationships.
- Timeline built only from timestamps that exist.

**3. Cypher Lab**
- Predefined, **read-only** Cypher templates only.
- Shows the exact executed Cypher, its parameters, retrieved rows and measured execution time.
- Depth-bounded (`DEPENDS_ON*1..N`) traversals with an adjustable depth slider.

**4. Graph Explorer**
- Interactive graph (pyvis/vis-network) of services, incidents, people, projects, solutions and teams.
- Entity-type filters; a node inspector for reading node properties.
- Highlight an incident's affected-service path; automatic fallback to a table if `pyvis` is unavailable.

**5. Runbooks & Remediation**
- Displays the recorded runbook/steps and the evidence that supports it.
- "Mark as reviewed" (session state) and a **clearly labelled simulated** remediation action.
- No real system is ever changed.

**Reliability**
- Real FalkorDB health check (no fake "connected" badge, no fabricated node/edge counts).
- Distinct UI states for: connected, unavailable, query failed, and no matching records.
- Bounded queries and result limits; parameterised where supported.

---

## 4. Architecture and data flow

```
                 ┌────────────────────────────────────────────┐
                 │                app.py (Streamlit)          │
                 │  Query Console · Triage · Graph · Cypher Lab │
                 └───────────────┬────────────────────────────┘
                                 │  (renders responses, no DB logic)
                 ┌───────────────▼────────────────────────────┐
                 │                 agent.py                   │
                 │  intent classification → entity extraction │
                 │  → query selection → evidence assembly     │
                 └───────────────┬────────────────────────────┘
                                 │
                 ┌───────────────▼────────────────────────────┐
                 │              query_graph.py                │
                 │  reusable read-only Cypher functions       │
                 │  bounded depth · row limits · parameters   │
                 └───────────────┬────────────────────────────┘
                                 │
                 ┌───────────────▼────────────────────────────┐
                 │                  db.py                      │
                 │  connection · health check · error mapping  │
                 └───────────────┬────────────────────────────┘
                                 │
                          ┌──────▼───────┐
                          │  FalkorDB    │   seed_data.py loads
                          │  (tracedesk) │   synthetic demo data
                          └──────────────┘
```

Agent workflow: **question → query planning → FalkorDB → evidence validation → answer synthesis → UI presentation.**

Module responsibilities:

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI for the five views (no direct Cypher). |
| `agent.py` | NL question → intent/entity → graph query → structured, evidenced answer. |
| `query_graph.py` | Reusable, read-only, bounded Cypher queries + query templates. |
| `db.py` | FalkorDB connection, health check, error translation. |
| `seed_data.py` | Idempotent synthetic demo graph. |
| `tests/` | Unit (mocked), integration (live DB) and UI smoke tests. |

---

## 5. Graph schema

**Nodes**

| Label | Key properties |
|---|---|
| `Person` | `id`, `name`, `role`, `team` |
| `Team` | `id`, `name` |
| `Service` | `id`, `name`, `env`, `status` |
| `Project` | `id`, `name`, `status`, `description` |
| `Incident` | `id`, `title`, `severity`, `status`, `timestamp`, `description` |
| `Solution` | `id`, `summary`, `steps`, `reference` |

**Relationships**

```
(:Incident)-[:AFFECTS]->(:Service)
(:Service)-[:DEPENDS_ON]->(:Service)
(:Person)-[:OWNS]->(:Service)
(:Person)-[:WORKED_ON]->(:Project)
(:Person)-[:MEMBER_OF]->(:Team)
(:Project)-[:USES]->(:Service)
(:Incident)-[:FIXED_BY]->(:Solution)
```

**Example query**

```cypher
MATCH (i:Incident)-[:AFFECTS]->(s:Service)
OPTIONAL MATCH (p:Person)-[:OWNS]->(s)
OPTIONAL MATCH (i)-[:FIXED_BY]->(sol:Solution)
RETURN i, s, p, sol
```

Optional matches are always handled, so incidents without an owner or solution are reported honestly rather than dropped or fabricated.

---

## 6. Prerequisites

- **Python 3.10+**
- **Docker Desktop** (to run FalkorDB) — or any reachable FalkorDB instance
- Windows PowerShell, macOS Terminal, or Linux shell

---

## 7. Setup & launch (Windows PowerShell)

```powershell
# 1. From the project root, create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

> If PowerShell blocks activation, run once in the same window:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

---

## 8. Docker / FalkorDB

Start FalkorDB (Redis protocol on `6379`, browser UI on `3000`):

```powershell
docker run -d --name falkordb -p 6379:6379 -p 3000:3000 falkordb/falkordb:latest
```

Verify connectivity:

```powershell
python test_connection.py
# -> [['FalkorDB connected!']]
```

Connection settings can be overridden with environment variables:
`FALKORDB_HOST` (default `localhost`), `FALKORDB_PORT` (default `6379`), `FALKORDB_GRAPH` (default `tracedesk`).

---

## 9. Seeding the fictional demo data

The dataset is **entirely synthetic** and safe to share. It is idempotent — re-running it never creates duplicates.

```powershell
python seed_data.py
```

Loads 6 people, 3 teams, 9 services, 3 projects, 5 incidents, 5 solutions and their relationships. You can also click **"Reseed demo graph"** in the app sidebar.

---

## 10. Example questions & expected behaviour

| Question | Expected behaviour |
|---|---|
| `Who owns the Payments API?` | Returns Maya (Backend Engineer, Payments Team) from the `OWNS` edge. |
| `Which incident affected the Payments API?` | Returns `INC-101` via `AFFECTS`. |
| `What is the solution for the Payments API?` | Returns `SOL-101` and its steps via `FIXED_BY`. |
| `What does the Payments API depend on?` | Bounded `DEPENDS_ON` traversal (Auth Service, Payments DB, Redis Cache). |
| `What is the blast radius of the Payments API?` | Reverse traversal → Checkout Web. |
| `Investigate INC-101` | Full triage: affected service, owner, recorded solution, hypothesis, next steps, evidence. |
| `Who owns the WooCommerce Service?` | Honest no-result message — the entity does not exist. |
| `Tell me a joke` | Unsupported-request message listing what the agent can do. |

When FalkorDB is down, the app shows an **unavailable** status and the agent returns a clear "cannot reach the graph" message instead of guessing.

---

## 11. Running the app

```powershell
streamlit run app.py
```

Then open the printed URL (default `http://localhost:8501`). Use the sidebar to switch between Query Console, Incident Triage, Graph Explorer, Cypher Lab and Runbooks.

---

## 12. Running tests

```powershell
python -m pytest tests -q
```

- **Unit tests** (`test_agent.py`, `test_query_graph.py`) mock the graph layer and always run.
- **Integration tests** (`test_integration.py`) run against a live FalkorDB and are **skipped** (not failed) if it is unavailable.
- **UI smoke tests** (`test_app_smoke.py`) run every view via Streamlit's `AppTest` and pass with or without a database.

Last local run: **44 passed** (25 unit, 11 integration, 8 smoke).

---

## 13. Screenshots

> _Placeholders — replace with your own captures before submitting._

| View | File |
|---|---|
| Query Console | `screenshots/query-console.png` _(add)_ |
| Incident Triage | `screenshots/incident-triage.png` _(add)_ |
| Graph Explorer | `screenshots/graph-explorer.png` _(add)_ |
| Cypher Lab | `screenshots/cypher-lab.png` _(add)_ |
| Runbooks | `screenshots/runbooks.png` _(add)_ |

---

## 14. Known limitations & future work

- **No LLM by default.** Intent handling is rule-based and covers the documented question types. An LLM could be added for freer phrasing without changing the evidence-grounded query layer.
- **Demo data is synthetic.** There is no live telemetry, logging or metrics ingestion; blast radius reflects recorded `DEPENDS_ON` edges only.
- **Root causes are hypotheses.** The graph records remediations, not confirmed causal findings, so the triage view labels them as hypotheses.
- **Read-only investigation.** Only predefined templates execute; arbitrary or write queries are intentionally disallowed.
- **Single graph, fixed schema.** Multi-tenancy and schema versioning are out of scope for the MVP.
- **Future:** live topology refresh, historical incident trends, an LLM summariser over retrieved evidence, and saved investigations.

---

## AI-assisted development & responsibility

This project was developed with substantial AI coding assistance. As the author, I am responsible for understanding the graph schema, the query flow, and the evidence returned, and for testing and validating the implementation before submission. The graph layer is deliberately simple and inspectable — every answer can be traced to a Cypher query you can run yourself in the Cypher Lab view — so the behaviour can be independently verified rather than taken on trust.

---

## Repository layout

```
Tracedesk_AI/
├── app.py              # Streamlit UI (5 views)
├── agent.py            # graph-grounded Q&A + incident investigation
├── query_graph.py      # reusable read-only Cypher queries & templates
├── db.py               # FalkorDB connection + health check
├── seed_data.py        # idempotent synthetic demo data
├── test_connection.py  # tiny connectivity check
├── tests/
│   ├── conftest.py
│   ├── test_agent.py
│   ├── test_query_graph.py
│   ├── test_integration.py
│   └── test_app_smoke.py
├── requirements.txt
├── .gitignore
└── README.md
```
