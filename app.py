"""TraceDesk AI — dark SRE operations console (Streamlit).

Five functional areas, all backed by the FalkorDB knowledge graph:
  1. Query Console    — natural-language investigation chat
  2. Incident Triage  — evidence-backed workspace for one incident
  3. Graph Explorer   — interactive topology with a node inspector
  4. Cypher Lab       — read-only query templates
  5. Runbooks         — recorded solutions and remediation review

The UI only presents what the graph returns. When the graph is unavailable or a
question has no matching records, it says so instead of inventing an answer.

This module is intentionally presentation-only: all database access is delegated
to ``db`` and ``query_graph``, and all reasoning to ``agent``.
"""

import html

import streamlit as st
import streamlit.components.v1 as components

import db
import query_graph as q
import seed_data
from agent import ask_agent, build_investigation
from db import GraphUnavailableError

try:
    from pyvis.network import Network  # noqa: F401

    PYVIS_AVAILABLE = True
except ImportError:  # pragma: no cover - optional visual dependency
    PYVIS_AVAILABLE = False


NAV_ITEMS = ["Query Console", "Incident Triage", "Graph Explorer", "Cypher Lab", "Runbooks"]

ENTITY_COLORS = {
    "Service": "#00F0FF",
    "Incident": "#F87171",
    "Person": "#8B5CF6",
    "Project": "#FBBF24",
    "Solution": "#00D2B4",
    "Team": "#94A3B8",
}


st.set_page_config(
    page_title="TraceDesk AI",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# --------------------------------------------------------------------------
# Design system
# --------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --bg-base: #090D16;
    --panel: #0E1117;
    --card: #161C26;
    --border: #1E2638;
    --accent: #00F0FF;
    --accent-2: #8B5CF6;
    --success: #00D2B4;
    --warning: #FBBF24;
    --critical: #F87171;
    --text: #F1F5F9;
    --text-dim: #94A3B8;
    --radius: 12px;
}

html, body, .stApp {
    background: var(--bg-base);
    color: var(--text);
    font-family: 'Inter', system-ui, -apple-system, 'Segoe UI', sans-serif;
    -webkit-font-smoothing: antialiased;
}

header[data-testid="stHeader"] { background: transparent; }

.block-container {
    max-width: 1240px;
    padding: 1.4rem 2.2rem 5rem 2.2rem;
}

#MainMenu, footer { visibility: hidden; }

h1, h2, h3, h4 { color: var(--text); letter-spacing: -0.02em; font-weight: 650; }

a { color: var(--accent); }

/* ---------- Sidebar ---------- */
[data-testid="stSidebar"] {
    background: var(--panel);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] > div:first-child { padding-top: 1.3rem; }

.td-brand { display: flex; align-items: center; gap: 11px; }
.td-mark {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    display: grid; place-items: center;
}
.td-name { font-size: 1.06rem; font-weight: 700; color: #FFFFFF; line-height: 1.1; }
.td-sub { font-size: 0.72rem; color: var(--text-dim); margin: 3px 0 0 0; line-height: 1.35; }

.td-label {
    text-transform: uppercase; font-size: 0.64rem; font-weight: 700;
    letter-spacing: 0.14em; color: #64748B; margin: 1.4rem 0 0.5rem 0;
}

/* Sidebar navigation (radio styled as nav list) */
[data-testid="stSidebar"] div[role="radiogroup"] { gap: 3px; }
[data-testid="stSidebar"] div[role="radiogroup"] > label {
    display: flex; align-items: center; gap: 2px;
    padding: 9px 12px; margin: 0; border-radius: 9px;
    border: 1px solid transparent; cursor: pointer;
    transition: background 0.12s ease, border-color 0.12s ease;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:hover {
    background: var(--card); border-color: var(--border);
}
[data-testid="stSidebar"] div[role="radiogroup"] > label > div:first-child {
    /* hide the radio dot for a nav-list look */
    display: none;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label p {
    font-size: 0.9rem; font-weight: 500; color: var(--text-dim); margin: 0;
    white-space: nowrap;
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) {
    background: rgba(0, 240, 255, 0.08);
    border-color: rgba(0, 240, 255, 0.35);
}
[data-testid="stSidebar"] div[role="radiogroup"] > label:has(input:checked) p {
    color: var(--accent); font-weight: 600;
}

.td-status {
    border: 1px solid var(--border); background: var(--card);
    border-radius: 10px; padding: 11px 13px;
}
.td-status-title { font-size: 0.82rem; font-weight: 600; }
.td-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 8px; }
.td-dot-ok { background: var(--success); }
.td-dot-bad { background: var(--critical); }
.td-status-meta {
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    color: var(--text-dim); margin-top: 7px; line-height: 1.6;
}
.td-counts { display: flex; gap: 16px; margin-top: 9px; }
.td-count { flex: 1; }
.td-count .n { font-family: 'JetBrains Mono', monospace; font-size: 1.0rem; font-weight: 600; color: var(--text); }
.td-count .k { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748B; }

/* ---------- Top bar ---------- */
.td-topbar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 0 0.9rem 0; margin-bottom: 1.1rem;
    border-bottom: 1px solid var(--border);
}
.td-topbar-brand { font-weight: 700; font-size: 0.95rem; color: var(--text); }
.td-topbar-sep { color: #334155; margin: 0 9px; }
.td-topbar-ws { color: var(--accent); font-weight: 600; font-size: 0.92rem; }
.td-topbar-conn {
    font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: var(--text-dim);
}

/* ---------- Page head ---------- */
.td-head { margin: 0.2rem 0 1.4rem 0; }
.td-head h1 { font-size: 1.7rem; margin: 0 0 0.45rem 0; font-weight: 700; }
.td-head p { color: var(--text-dim); font-size: 0.94rem; margin: 0; line-height: 1.6; max-width: 720px; }

.td-section {
    text-transform: uppercase; font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.13em; color: #64748B; margin: 1.5rem 0 0.6rem 0;
}
.td-mono { font-family: 'JetBrains Mono', monospace; }

/* ---------- Cards ---------- */
.td-card {
    background: var(--card); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 15px 17px; height: 100%;
}
.td-card.td-accent { border-left: 3px solid var(--accent); }
.td-card.td-warn { border-left: 3px solid var(--warning); }
.td-card.td-crit { border-left: 3px solid var(--critical); }
.td-card.td-ok { border-left: 3px solid var(--success); }
.td-card-title { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.1em; color: #64748B; font-weight: 700; }
.td-card-value { font-size: 1.02rem; font-weight: 600; margin-top: 5px; color: var(--text); }
.td-card-sub { font-size: 0.8rem; color: var(--text-dim); margin-top: 5px; line-height: 1.55; }

/* ---------- Pills ---------- */
.pill { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.71rem; font-weight: 600; letter-spacing: 0.02em; }
.pill-critical, .pill-high, .pill-degraded { background: rgba(248,113,113,0.14); color: #FCA5A5; border: 1px solid rgba(248,113,113,0.4); }
.pill-medium { background: rgba(251,191,36,0.14); color: #FCD34D; border: 1px solid rgba(251,191,36,0.4); }
.pill-low, .pill-healthy { background: rgba(0,210,180,0.12); color: #5EEAD4; border: 1px solid rgba(0,210,180,0.35); }
.pill-status { background: rgba(139,92,246,0.14); color: #C4B5FD; border: 1px solid rgba(139,92,246,0.35); }
.pill-neutral { background: rgba(148,163,184,0.12); color: #CBD5E1; border: 1px solid rgba(148,163,184,0.3); }

/* ---------- Chat input ---------- */
[data-testid="stChatInput"] {
    border: 1px solid var(--border); border-radius: 14px;
    background: var(--panel) !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px rgba(0, 240, 255, 0.12);
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus {
    font-family: 'Inter', system-ui, sans-serif !important;
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    background-color: transparent !important;
    caret-color: var(--accent) !important;
    font-size: 0.95rem;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #64748B !important;
    -webkit-text-fill-color: #64748B !important;
}

/* ---------- Buttons ---------- */
.stButton > button {
    border-radius: 10px; border: 1px solid var(--border);
    background: var(--card); color: var(--text);
    min-height: 40px; font-weight: 500; font-size: 0.88rem;
    transition: border-color 0.12s ease, background 0.12s ease, color 0.12s ease;
}
.stButton > button:hover {
    border-color: var(--accent); color: var(--accent);
    background: #1B2330;
}
.stButton > button:focus:not(:active) { border-color: var(--accent); color: var(--accent); }

/* Suggested-question cards */
[class*="st-key-td_suggest"] button {
    width: 100%; min-height: 76px; padding: 13px 15px;
    text-align: left; justify-content: flex-start; white-space: pre-line;
    line-height: 1.45; font-size: 0.86rem; color: var(--text-dim);
}
[class*="st-key-td_suggest"] button:hover { color: var(--text); }

/* Follow-up question chips */
[class*="st-key-td_followup"] button {
    min-height: 34px; padding: 6px 13px; font-size: 0.82rem;
    border-radius: 18px; color: var(--text-dim);
}
[class*="st-key-td_followup"] button:hover { color: var(--accent); }

/* ---------- Chat messages ---------- */
[data-testid="stChatMessage"] {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 14px 16px; margin-bottom: 10px;
}
.td-role {
    font-size: 0.66rem; font-weight: 700; letter-spacing: 0.12em;
    text-transform: uppercase; margin-bottom: 7px;
}
.td-role-user { color: var(--text-dim); }
.td-role-assistant { color: var(--accent); }

/* ---------- Tables ---------- */
.td-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; margin-top: 4px; }
table.td-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; font-family: 'JetBrains Mono', monospace; }
table.td-table thead tr { background: #111827; color: var(--text-dim); text-align: left; }
table.td-table th { padding: 8px 12px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.05em; font-size: 0.66rem; }
table.td-table td { padding: 8px 12px; border-bottom: 1px solid #151B26; color: #E2E8F0; vertical-align: top; }
table.td-table tr:last-child td { border-bottom: none; }
table.td-table tr:hover td { background: #111827; }

/* ---------- Misc ---------- */
.td-legend { display: flex; flex-wrap: wrap; gap: 14px; margin: 6px 0 12px 0; }
.td-legend-item { display: flex; align-items: center; gap: 7px; font-size: 0.78rem; color: var(--text-dim); }
.td-swatch { width: 11px; height: 11px; border-radius: 3px; }

.td-evidence-line {
    font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
    color: var(--text-dim); background: #111827; border: 1px solid var(--border);
    border-radius: 8px; padding: 8px 11px; margin: 4px 0;
}
.td-footnote { color: #64748B; font-size: 0.74rem; margin-top: 0.8rem; }

.td-empty {
    border: 1px dashed var(--border); border-radius: var(--radius);
    padding: 26px 20px; text-align: center; color: var(--text-dim);
    font-size: 0.88rem; background: rgba(22,28,38,0.4);
}

/* Streamlit native containers styled as cards */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    background: var(--panel);
}
[data-testid="stExpander"] summary { font-size: 0.85rem; }

/* Code blocks */
.stCode, pre { background: #0B1220 !important; border: 1px solid var(--border) !important; border-radius: 10px !important; }

@media (max-width: 900px) {
    .block-container { padding: 1rem 1rem 4rem 1rem; }
    .td-head h1 { font-size: 1.45rem; }
}
</style>
""",
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------
# Session state
# --------------------------------------------------------------------------
def _init_state():
    defaults = {
        "messages": [],
        "pending_prompt": None,
        "reviewed_remediations": set(),
        "cypher_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def start_new_chat():
    st.session_state.messages = []
    st.session_state.pending_prompt = None


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------
def h(value):
    """HTML-escape a value for safe inline rendering."""
    if value is None:
        return ""
    return html.escape(str(value))


def run_query_safe(fn, *args, **kwargs):
    """Run a graph function, returning ``(value, error_message)``."""
    try:
        return fn(*args, **kwargs), None
    except GraphUnavailableError as error:
        return None, str(error)


def section(title):
    st.markdown(f'<div class="td-section">{h(title)}</div>', unsafe_allow_html=True)


def severity_pill(severity):
    sev = (severity or "").lower()
    cls = {
        "critical": "pill-critical",
        "high": "pill-high",
        "medium": "pill-medium",
        "low": "pill-low",
    }.get(sev, "pill-neutral")
    return f'<span class="pill {cls}">{h(severity or "Unknown")}</span>'


def status_pill(status):
    return f'<span class="pill pill-status">{h(status or "Unknown")}</span>'


def service_status_pill(status):
    cls = "pill-healthy" if (status or "").lower() == "healthy" else "pill-degraded"
    return f'<span class="pill {cls}">{h(status or "unknown")}</span>'


def render_table(rows, columns=None):
    """Render a list of dicts as a themed HTML table (no pandas dependency)."""
    if not rows:
        return
    columns = columns or list(rows[0].keys())
    head = "".join(f"<th>{h(col)}</th>" for col in columns)
    body = ""
    for row in rows:
        cells = "".join(f"<td>{h(row.get(col, ''))}</td>" for col in columns)
        body += f"<tr>{cells}</tr>"
    st.markdown(
        f'<div class="td-table-wrap"><table class="td-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_evidence(evidence, label="Graph evidence"):
    if not evidence:
        return
    with st.expander(f"{label} · {len(evidence)} result set(s)"):
        for item in evidence:
            st.markdown(f"**{h(item.get('title', 'Query'))}**")
            if item.get("cypher"):
                st.code(item["cypher"], language="cypher")
            if item.get("params"):
                st.caption(f"parameters: `{item['params']}`")
            rows = item.get("rows") or []
            if rows:
                render_table(rows, item.get("columns"))
            else:
                st.caption("No rows returned — the graph has no matching records.")
            if item.get("run_time_ms") is not None:
                st.caption(f"execution time: {item['run_time_ms']:.2f} ms")
            st.divider()


def evidence_chain_line(chain):
    st.markdown(f'<div class="td-evidence-line">{chain}</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
_BRAND_ICON = (
    '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" '
    'stroke="#04121A" stroke-width="2" stroke-linecap="round">'
    '<circle cx="6" cy="6" r="2.6"/><circle cx="18" cy="6" r="2.6"/>'
    '<circle cx="12" cy="18" r="2.6"/>'
    '<line x1="7.9" y1="7.2" x2="10.8" y2="15.8"/>'
    '<line x1="16.1" y1="7.2" x2="13.2" y2="15.8"/>'
    '<line x1="8.6" y1="6" x2="15.4" y2="6"/></svg>'
)


def render_sidebar(status):
    with st.sidebar:
        st.markdown(
            f"""
            <div class="td-brand">
                <div class="td-mark">{_BRAND_ICON}</div>
                <div>
                    <div class="td-name">TraceDesk AI</div>
                    <div class="td-sub">Graph-powered incident investigation</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown('<div class="td-label">Workspace</div>', unsafe_allow_html=True)
        view = st.radio("Navigation", NAV_ITEMS, label_visibility="collapsed")

        st.markdown('<div class="td-label">FalkorDB</div>', unsafe_allow_html=True)
        if status["connected"]:
            st.markdown(
                f"""
                <div class="td-status">
                    <div class="td-status-title"><span class="td-dot td-dot-ok"></span>Connected</div>
                    <div class="td-status-meta">{h(status['host'])}:{h(status['port'])} · '{h(status['graph'])}'</div>
                    <div class="td-counts">
                        <div class="td-count"><div class="n">{h(status['node_count'])}</div><div class="k">nodes</div></div>
                        <div class="td-count"><div class="n">{h(status['relationship_count'])}</div><div class="k">edges</div></div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"""
                <div class="td-status" style="border-color:rgba(248,113,113,0.4);">
                    <div class="td-status-title" style="color:#FCA5A5;"><span class="td-dot td-dot-bad"></span>Unavailable</div>
                    <div class="td-status-meta">{h(status['host'])}:{h(status['port'])} unreachable. Start FalkorDB, then reseed.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown('<div class="td-label">Data</div>', unsafe_allow_html=True)
        if st.button("Reseed demo graph", key="td_reseed", use_container_width=True):
            try:
                stats = seed_data.seed()
                st.success(f"Seeded {stats['services']} services, {stats['incidents']} incidents.")
                st.rerun()
            except Exception as error:  # noqa: BLE001
                st.error(f"Seeding failed: {error}")

        st.markdown(
            '<div class="td-footnote">Evidence retrieved from FalkorDB · read-only queries</div>',
            unsafe_allow_html=True,
        )
    return view


def render_topbar(view, status):
    conn = "connected" if status["connected"] else "offline"
    dot = "td-dot-ok" if status["connected"] else "td-dot-bad"
    st.markdown(
        f"""
        <div class="td-topbar">
            <div>
                <span class="td-topbar-brand">TraceDesk AI</span>
                <span class="td-topbar-sep">/</span>
                <span class="td-topbar-ws">{h(view)}</span>
            </div>
            <div class="td-topbar-conn"><span class="td-dot {dot}"></span>FalkorDB {conn}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_db_error(error, context="FalkorDB is unavailable"):
    st.markdown(
        f"""
        <div class="td-empty">
            <div style="color:#FCA5A5;font-weight:600;margin-bottom:5px;">{h(context)}</div>
            <div class="td-mono" style="font-size:0.8rem;">{h(error)}</div>
            <div style="margin-top:10px;">Start the database, then use <b>Reseed demo graph</b> in the sidebar.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Follow-up question generation (based on returned data)
# --------------------------------------------------------------------------
def _as_list(value):
    """Normalise an entity value that may be a string or a list into a list."""
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item]
    return [value]


def derive_followups(response, asked=None):
    entities = response.get("entities", {}) or {}
    services = _as_list(entities.get("services")) or _as_list(entities.get("service"))
    incidents = _as_list(entities.get("incidents")) or _as_list(entities.get("incident"))
    asked_norm = (asked or "").strip().lower()
    candidates = []

    if incidents:
        candidates.append(("Investigate " + incidents[0], f"Investigate incident {incidents[0]}"))
    if services:
        svc = services[0]
        candidates += [
            (f"Who owns {svc}?", f"Who owns the {svc}?"),
            (f"Impact of {svc}", f"What is the blast radius of the {svc}?"),
            (f"Dependencies of {svc}", f"What does the {svc} depend on?"),
            (f"Solutions for {svc}", f"What is the solution for the {svc}?"),
        ]
    if response.get("intent") == "investigate" and services:
        candidates.insert(0, ("Open triage", f"Investigate incident {incidents[0]}" if incidents else f"Investigate {services[0]}"))

    seen, result = set(), []
    for label, prompt in candidates:
        if prompt.lower() == asked_norm or prompt in seen:
            continue
        seen.add(prompt)
        result.append((label, prompt))
    return result[:4]


# --------------------------------------------------------------------------
# Response rendering
# --------------------------------------------------------------------------
def render_assistant_message(message):
    response = message["response"]
    with st.chat_message("assistant"):
        st.markdown('<div class="td-role td-role-assistant">TraceDesk analysis</div>', unsafe_allow_html=True)

        if response.get("status") == "error":
            st.error(response["answer"])
        else:
            st.markdown(response["answer"])
            if response.get("status") == "no_result":
                st.caption("No matching records were found in the graph for this question.")

        if response.get("relationships"):
            st.markdown(
                '<div class="td-section">Relationships used</div>', unsafe_allow_html=True
            )
            for rel in response["relationships"][:8]:
                st.markdown(
                    f'<div class="td-evidence-line">{h(rel["from"])} '
                    f'<span style="color:var(--accent-2)">-[{h(rel["type"])}]-></span> {h(rel["to"])}</div>',
                    unsafe_allow_html=True,
                )

        render_evidence(response.get("evidence"))

        if response.get("limitations"):
            with st.expander("Limitations & assumptions"):
                for note in response["limitations"]:
                    st.markdown(f"- {note}")

        followups = derive_followups(response, message.get("asked"))
        if followups:
            st.markdown('<div class="td-section">Suggested follow-ups</div>', unsafe_allow_html=True)
            cols = st.columns(min(len(followups), 2))
            for index, (label, prompt) in enumerate(followups):
                with cols[index % len(cols)]:
                    if st.button(label, key=f"td_followup_{message['id']}_{index}", use_container_width=True):
                        st.session_state.pending_prompt = prompt


def render_user_message(message):
    with st.chat_message("user"):
        st.markdown('<div class="td-role td-role-user">You</div>', unsafe_allow_html=True)
        st.markdown(message["content"])


# --------------------------------------------------------------------------
# View 1 — Query Console
# --------------------------------------------------------------------------
def build_suggestions(status):
    inc_id, svc = "INC-101", "Payments API"
    if status["connected"]:
        incidents, _ = run_query_safe(q.list_incidents)
        services, _ = run_query_safe(q.list_services)
        if incidents:
            inc_id = incidents[0]["id"]
        if services:
            svc = services[0]["name"]
    return [
        ("Incident investigation", f"Investigate incident {inc_id}"),
        ("Service ownership", f"Who owns the {svc}?"),
        ("Dependency impact", f"What is the blast radius of the {svc}?"),
        ("Recorded solutions", f"What is the solution for the {svc}?"),
    ]


def view_query_console(status):
    st.markdown(
        """
        <div class="td-head">
            <h1>Investigate your graph.</h1>
            <p>Ask about incidents, services, owners, dependencies and recorded solutions.
            Every answer is retrieved from FalkorDB and shows the graph evidence behind it.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not st.session_state.messages:
        section("Suggested investigations")
        suggestions = build_suggestions(status)
        cols = st.columns(2)
        for index, (category, prompt) in enumerate(suggestions):
            with cols[index % 2]:
                label = f"**{category}**  \n{prompt}"
                if st.button(label, key=f"td_suggest_{index}", help=prompt, use_container_width=True):
                    st.session_state.pending_prompt = prompt

    for message in st.session_state.messages:
        if message["role"] == "user":
            render_user_message(message)
        else:
            render_assistant_message(message)

    typed = st.chat_input("Ask TraceDesk about an incident, service, owner or solution...")
    question = typed or st.session_state.pending_prompt
    st.session_state.pending_prompt = None

    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.spinner("Querying FalkorDB and assembling evidence..."):
            response = ask_agent(question)
        st.session_state.messages.append(
            {
                "role": "assistant",
                "id": len(st.session_state.messages),
                "asked": question,
                "response": response,
            }
        )
        st.rerun()


# --------------------------------------------------------------------------
# View 2 — Incident Triage
# --------------------------------------------------------------------------
def view_incident_triage(status):
    st.markdown(
        """
        <div class="td-head">
            <h1>Incident Triage</h1>
            <p>Investigate one incident using only the relationships recorded in the graph.
            Hypotheses are clearly separated from confirmed facts.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not status["connected"]:
        render_db_error(status["error"] or "Connection failed.")
        return

    incidents, error = run_query_safe(q.list_incidents)
    if error:
        render_db_error(error)
        return
    if not incidents:
        st.markdown('<div class="td-empty">No incidents are present in the graph. Use <b>Reseed demo graph</b> in the sidebar.</div>', unsafe_allow_html=True)
        return

    options = {f"{i['id']} · {i['title']}": i["id"] for i in incidents}
    choice = st.selectbox("Select an incident", list(options.keys()))
    incident_id = options[choice]

    investigation, error = run_query_safe(build_investigation, incident_id)
    if error:
        render_db_error(error)
        return
    if not investigation:
        st.warning(f"Incident {incident_id} was not found.")
        return

    incident = investigation["incident"]

    st.markdown(
        f"""
        <div class="td-card td-crit">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:14px;flex-wrap:wrap;">
                <div>
                    <div class="td-card-value"><span class="td-mono" style="color:var(--accent)">{h(incident['id'])}</span> &nbsp;{h(incident['title'])}</div>
                    <div class="td-card-sub">{h(incident['timestamp'] or 'timestamp unknown')} · {h(incident['description'] or '')}</div>
                </div>
                <div>{severity_pill(incident['severity'])} {status_pill(incident['status'])}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        section("Affected services")
        if incident["services"]:
            for service in incident["services"]:
                st.markdown(f"- {service}")
        else:
            st.caption("No AFFECTS relationship recorded.")

        section("Recorded owners")
        if investigation["owners"]:
            for owner in investigation["owners"]:
                team = f" · {owner['team']}" if owner.get("team") else ""
                st.markdown(f"- **{owner['name']}** ({owner['service']}){team}")
        else:
            st.caption("No owner recorded for the affected services.")

        section("Recorded solution")
        if incident["solution"]:
            st.markdown(f"**{incident['solution']['id']}** — {incident['solution']['summary']}")
            if incident["solution"].get("reference"):
                st.caption(f"reference: `{incident['solution']['reference']}`")
        else:
            st.caption("No FIXED_BY solution recorded.")

    with col2:
        section("Root-cause hypothesis")
        hypothesis = investigation["hypothesis"]
        st.markdown(
            f"""
            <div class="td-card td-warn">
                <div class="td-card-sub" style="color:var(--text);font-weight:600;">{h(hypothesis['statement'])}</div>
                <div class="td-card-sub">{h(hypothesis['basis'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        section("Recommended diagnostic steps")
        if investigation["recommended_steps"]:
            for index, step in enumerate(investigation["recommended_steps"], start=1):
                st.markdown(f"{index}. {step}")
        else:
            st.caption("No recorded runbook steps for this incident.")

    section("Blast radius (from graph relationships)")
    if investigation["blast_radius"]:
        for radius in investigation["blast_radius"]:
            affected = radius["affected"]
            if affected:
                names = ", ".join(a["name"] for a in affected)
                st.markdown(f"- If **{radius['origin']['name']}** fails → consumers: {names}")
            else:
                st.markdown(f"- **{radius['origin']['name']}** has no recorded consumers.")
    else:
        st.caption("No blast radius information available.")

    section("Timeline")
    if investigation["timeline"]:
        for event in investigation["timeline"]:
            st.markdown(f"- `{event['time']}` — {event['event']}")
    else:
        st.caption("No timestamps recorded for this incident.")

    render_evidence(investigation["evidence"], label="Evidence panel")
    with st.expander("Limitations & assumptions"):
        for note in investigation["limitations"]:
            st.markdown(f"- {note}")


# --------------------------------------------------------------------------
# View 3 — Graph Explorer
# --------------------------------------------------------------------------
def _build_topology_html(topo, highlight_ids=None):
    highlight_ids = highlight_ids or set()
    net = Network(height="600px", width="100%", bgcolor="#0E1117", font_color="#E2E8F0", directed=True, cdn_resources="in_line")
    net.barnes_hut(gravity=-9000, central_gravity=0.3, spring_length=170)

    node_ids = {n["id"] for n in topo["nodes"]}
    for node in topo["nodes"]:
        color = ENTITY_COLORS.get(node["label"], "#64748B")
        is_hl = node["id"] in highlight_ids
        net.add_node(
            node["id"],
            label=node["title"],
            title=f"{node['label']} · {node['detail']}",
            color="#FFB020" if is_hl else color,
            borderWidth=4 if is_hl else 1,
            size=26 if is_hl else 17,
        )
    for edge in topo["edges"]:
        if edge["from"] not in node_ids or edge["to"] not in node_ids:
            continue
        highlighted = edge["from"] in highlight_ids and edge["to"] in highlight_ids
        net.add_edge(
            edge["from"],
            edge["to"],
            title=edge["type"],
            color="#FFB020" if highlighted else "#334155",
            width=3 if highlighted else 1,
        )
    return net.generate_html()


def view_graph_explorer(status):
    st.markdown(
        """
        <div class="td-head">
            <h1>Graph Explorer</h1>
            <p>Interactive view of the knowledge graph. Node colours indicate entity type;
            select a node to inspect its properties.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not status["connected"]:
        render_db_error(status["error"] or "Connection failed.")
        return

    entities = list(ENTITY_COLORS.keys())
    filter_col, highlight_col = st.columns([2, 1])
    with filter_col:
        selected_types = st.multiselect("Entity types", entities, default=entities)
    with highlight_col:
        incidents, _ = run_query_safe(q.list_incidents)
        incident_ids = [i["id"] for i in incidents] if incidents else []
        highlight_choice = st.selectbox("Highlight incident path", ["None"] + incident_ids)

    topo, error = run_query_safe(q.get_topology, selected_types)
    if error:
        render_db_error(error)
        return
    if not topo["nodes"]:
        st.markdown('<div class="td-empty">No graph data to display. Use <b>Reseed demo graph</b> in the sidebar.</div>', unsafe_allow_html=True)
        return

    legend = "".join(
        f'<div class="td-legend-item"><span class="td-swatch" style="background:{ENTITY_COLORS[name]}"></span>{h(name)}</div>'
        for name in ENTITY_COLORS
    )
    st.markdown(f'<div class="td-legend">{legend}</div>', unsafe_allow_html=True)

    highlight_ids = set()
    if highlight_choice != "None":
        path, _ = run_query_safe(q.get_incident_path, highlight_choice)
        if path:
            highlight_ids = set(path["service_ids"])
            service_titles = {n["id"]: n["title"] for n in topo["nodes"] if n["label"] == "Service"}
            names = [service_titles.get(i, i) for i in highlight_ids]
            st.caption(f"Highlighted path services for {highlight_choice}: " + ", ".join(names))

    if PYVIS_AVAILABLE:
        components.html(_build_topology_html(topo, highlight_ids), height=620, scrolling=True)
    else:
        st.warning("pyvis is not installed, so the interactive graph is unavailable. Install it with `pip install pyvis`.")
        render_table(topo["nodes"])

    detail_col, _ = st.columns([2, 1])
    with detail_col:
        section("Node inspector")
        node_titles = {f"{n['title']} ({n['label']})": n["id"] for n in topo["nodes"]}
        chosen = st.selectbox("Select a node", ["—"] + list(node_titles.keys()))
        if chosen != "—":
            details, error = run_query_safe(q.get_node_details, node_titles[chosen])
            if error:
                st.error(f"Could not load node: {error}")
            elif details:
                st.markdown(f"**{h(details['title'])}** · {status_pill(details['label'])}", unsafe_allow_html=True)
                props = [{"property": k, "value": v} for k, v in details["properties"].items()]
                render_table(props, ["property", "value"])


# --------------------------------------------------------------------------
# View 4 — Cypher Lab
# --------------------------------------------------------------------------
def view_cypher_lab(status):
    st.markdown(
        """
        <div class="td-head">
            <h1>Cypher Lab</h1>
            <p>Run the read-only Cypher templates that power TraceDesk's answers.
            Only predefined, read-only queries are executed; arbitrary or write queries are not allowed.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not status["connected"]:
        render_db_error(status["error"] or "Connection failed.")
        return

    services, error = run_query_safe(q.list_services)
    if error:
        render_db_error(error)
        return
    incidents, _ = run_query_safe(q.list_incidents)

    template_labels = {v["title"]: k for k, v in q.QUERY_TEMPLATES.items()}
    left, right = st.columns([3, 2])
    with left:
        selected_title = st.selectbox("Query template", list(template_labels.keys()))
    template_key = template_labels[selected_title]
    template = q.QUERY_TEMPLATES[template_key]

    with right:
        st.caption(template["description"])

    params = {}
    depth = q.DEFAULT_DEPTH
    pcol1, pcol2 = st.columns([2, 1])
    with pcol1:
        if template["param"] == "service":
            service_names = [s["name"] for s in services]
            if not service_names:
                st.info("No services in the graph. Reseed demo data from the sidebar.")
                return
            params["name"] = st.selectbox("Service", service_names)
        else:
            if not incidents:
                st.info("No incidents in the graph. Reseed demo data from the sidebar.")
                return
            params["id"] = st.selectbox("Incident", [i["id"] for i in incidents])
    with pcol2:
        if "..N" in template["cypher"]:
            depth = st.slider("Max depth", 1, q.MAX_DEPTH, q.DEFAULT_DEPTH)

    run_clicked = st.button("Run read-only query", key="td_run_cypher", use_container_width=True)
    if run_clicked:
        try:
            st.session_state.cypher_result = q.run_template(template_key, params, depth)
        except GraphUnavailableError as error:
            st.session_state.cypher_result = None
            st.error(f"Query failed: {error}")

    result = st.session_state.cypher_result
    if result:
        section("Executed Cypher")
        st.code(result["cypher"], language="cypher")

        metric_cols = st.columns(3)
        with metric_cols[0]:
            st.markdown(
                f'<div class="td-card"><div class="td-card-title">Parameters</div>'
                f'<div class="td-card-value td-mono" style="font-size:0.82rem;">{h(result["params"])}</div></div>',
                unsafe_allow_html=True,
            )
        with metric_cols[1]:
            duration = f"{result['run_time_ms']:.2f} ms" if result["run_time_ms"] is not None else "n/a"
            st.markdown(
                f'<div class="td-card"><div class="td-card-title">Execution</div>'
                f'<div class="td-card-value td-mono">{h(duration)}</div></div>',
                unsafe_allow_html=True,
            )
        with metric_cols[2]:
            st.markdown(
                f'<div class="td-card"><div class="td-card-title">Rows</div>'
                f'<div class="td-card-value td-mono">{len(result["rows"])}</div></div>',
                unsafe_allow_html=True,
            )

        section("Results")
        if result["rows"]:
            render_table(result["rows"], result["columns"])
        else:
            st.markdown('<div class="td-empty">No matching records were returned by this query.</div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------
# View 5 — Runbooks
# --------------------------------------------------------------------------
def view_runbooks(status):
    st.markdown(
        """
        <div class="td-head">
            <h1>Runbooks &amp; Remediation</h1>
            <p>Recorded solutions linked to incidents and services. Marking a runbook as reviewed is
            local to your session; simulated remediation never changes any real system.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not status["connected"]:
        render_db_error(status["error"] or "Connection failed.")
        return

    solutions, error = run_query_safe(q.list_solutions)
    if error:
        render_db_error(error)
        return
    if not solutions:
        st.markdown('<div class="td-empty">No runbooks are recorded in the graph. Use <b>Reseed demo graph</b> in the sidebar.</div>', unsafe_allow_html=True)
        return

    st.caption(f"{len(solutions)} recorded solution(s) in the graph.")

    for solution in solutions:
        sol_id = solution["id"]
        incident_id = solution.get("incident_id")
        service = solution.get("service")
        reviewed = sol_id in st.session_state.reviewed_remediations

        with st.expander(f"{sol_id} · {solution['summary']}", expanded=False):
            meta_col, status_col = st.columns([3, 1])
            with meta_col:
                incident_txt = f"{incident_id} · {solution.get('incident_title') or ''}" if incident_id else "no linked incident"
                st.markdown(f"**Related incident:** {h(incident_txt)}", unsafe_allow_html=True)
                st.markdown(f"**Affected service:** {h(service or 'unrecorded')}", unsafe_allow_html=True)
                if solution.get("reference"):
                    st.caption(f"Runbook reference: `{solution['reference']}`")
            with status_col:
                st.markdown(
                    '<div class="pill pill-healthy">reviewed</div>' if reviewed else '<div class="pill pill-neutral">not reviewed</div>',
                    unsafe_allow_html=True,
                )

            section("Diagnostic steps")
            steps = [s.strip() for s in str(solution.get("steps") or "").splitlines() if s.strip()]
            if steps:
                for index, step in enumerate(steps, start=1):
                    st.markdown(f"{index}. {step}")
            else:
                st.caption("No steps recorded for this solution.")

            section("Evidence supporting this recommendation")
            if incident_id:
                evidence_chain_line(f"{h(incident_id)} -[FIXED_BY]-&gt; {h(sol_id)}")
            if incident_id and service:
                evidence_chain_line(f"{h(incident_id)} -[AFFECTS]-&gt; {h(service)}")

            action_cols = st.columns(2)
            with action_cols[0]:
                if reviewed:
                    st.success("Marked as reviewed.")
                else:
                    if st.button("Mark as reviewed", key=f"td_review_{sol_id}", use_container_width=True):
                        st.session_state.reviewed_remediations.add(sol_id)
                        st.rerun()
            with action_cols[1]:
                if st.button("Record simulated remediation", key=f"td_sim_{sol_id}", use_container_width=True):
                    st.warning(
                        f"SIMULATED ACTION — no change was made to any system. "
                        f"Applying {sol_id} in a real deployment would require explicit "
                        f"authorization and confirmation."
                    )


# --------------------------------------------------------------------------
# Router
# --------------------------------------------------------------------------
def main():
    _init_state()
    status = db.health_check()
    view = render_sidebar(status)
    render_topbar(view, status)

    if view == "Query Console":
        view_query_console(status)
    elif view == "Incident Triage":
        view_incident_triage(status)
    elif view == "Graph Explorer":
        view_graph_explorer(status)
    elif view == "Cypher Lab":
        view_cypher_lab(status)
    elif view == "Runbooks":
        view_runbooks(status)


if __name__ == "__main__":
    main()
