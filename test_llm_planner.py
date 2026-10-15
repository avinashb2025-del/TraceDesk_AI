
import json
from types import SimpleNamespace

import pytest

import llm_planner as planner


def test_planner_requires_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(planner.LLMPlannerError):
        planner.plan_tools("Who owns the Payments API?")


def test_valid_service_owner_arguments():
    result = planner._validate_arguments(
        "get_service_owner",
        {"service_name": " Payments API "},
    )

    assert result == {
        "service_name": "Payments API"
    }


def test_invalid_traversal_depth_is_rejected():
    with pytest.raises(planner.LLMPlannerError):
        planner._validate_arguments(
            "get_service_dependencies",
            {
                "service_name": "Payments API",
                "depth": 99,
            },
        )


def test_unknown_tool_is_rejected():
    with pytest.raises(planner.LLMPlannerError):
        planner._validate_arguments(
            "run_arbitrary_cypher",
            {},
        )


def test_invalid_incident_id_is_rejected():
    with pytest.raises(planner.LLMPlannerError):
        planner._validate_arguments(
            "get_incident_details",
            {"incident_id": "DROP DATABASE"},
        )


def test_question_length_is_checked():
    with pytest.raises(planner.LLMPlannerError):
        planner.plan_tools("x" * 4001)


def test_tool_schema_has_no_extra_properties():
    for tool in planner.TOOL_DEFINITIONS:
        schema = tool["parameters"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(
            schema["properties"]
        )
