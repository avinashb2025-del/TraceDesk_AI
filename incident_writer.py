"""Validated write operations for creating TraceDesk incidents.

The AI query tools must remain read-only. This module exposes only the explicit
incident-creation operation used by the Streamlit form.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import query_graph as q
from db import GraphUnavailableError, get_graph


class IncidentWriteError(ValueError):
    """Raised when an incident cannot safely be created."""


_ALLOWED_SEVERITIES = {"Critical", "High", "Medium", "Low"}
_ALLOWED_STATUSES = {"Investigating", "Monitoring", "Resolved"}
_INCIDENT_ID_RE = re.compile(r"^INC-[0-9]{3,8}$")


def create_incident(
    incident_id: str,
    title: str,
    severity: str,
    status: str,
    service_name: str,
    description: str,
) -> dict:
    """Create one Incident node and its AFFECTS edge to an existing Service."""
    incident_id = (incident_id or "").strip().upper()
    title = (title or "").strip()
    severity = (severity or "").strip().title()
    status = (status or "").strip().title()
    service_name = (service_name or "").strip()
    description = (description or "").strip()

    if not _INCIDENT_ID_RE.fullmatch(incident_id):
        raise IncidentWriteError("Incident ID must look like INC-106 (3–8 digits).")
    if not title or len(title) > 180:
        raise IncidentWriteError("Title is required and must be at most 180 characters.")
    if severity not in _ALLOWED_SEVERITIES:
        raise IncidentWriteError("Choose a valid severity.")
    if status not in _ALLOWED_STATUSES:
        raise IncidentWriteError("Choose a valid incident status.")
    if not service_name:
        raise IncidentWriteError("Choose an affected service.")
    if not description or len(description) > 2000:
        raise IncidentWriteError("Description is required and must be at most 2000 characters.")

    try:
        service = q.get_service(service_name)
        if not service:
            raise IncidentWriteError(
                f"Service '{service_name}' was not found. Select a service already in the graph."
            )
        existing = q.get_incident(incident_id)
        if existing:
            raise IncidentWriteError(
                f"Incident ID {incident_id} already exists. Use a new ID."
            )

        timestamp = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        graph = get_graph()
        graph.query(
            "MATCH (s:Service {name: $service_name}) "
            "CREATE (i:Incident {id: $id, title: $title, severity: $severity, "
            "status: $status, timestamp: $timestamp, description: $description}) "
            "CREATE (i)-[:AFFECTS]->(s) "
            "RETURN i.id AS id",
            {
                "service_name": service_name,
                "id": incident_id,
                "title": title,
                "severity": severity,
                "status": status,
                "timestamp": timestamp,
                "description": description,
            },
        )
        # Confirm that the graph now exposes the incident through the read path.
        created = q.get_incident(incident_id)
        if not created:
            raise IncidentWriteError(
                "The database write did not return the new incident. Check the graph connection."
            )
        return {
            "id": incident_id,
            "title": title,
            "severity": severity,
            "status": status,
            "timestamp": timestamp,
            "description": description,
            "service": service_name,
        }
    except IncidentWriteError:
        raise
    except GraphUnavailableError:
        raise
    except Exception as error:
        raise IncidentWriteError(f"Could not create incident: {error}") from error
