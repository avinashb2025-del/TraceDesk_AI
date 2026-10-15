
from falkordb import FalkorDB

client = FalkorDB(host="localhost", port=6379)
graph = client.select_graph("tracedesk")


def get_graph_data():
    query = """
    MATCH (p:Person)-[:OWNS]->(s:Service)
    OPTIONAL MATCH (i:Incident)-[:AFFECTS]->(s)
    OPTIONAL MATCH (i)-[:FIXED_BY]->(sol:Solution)
    RETURN
        s.name,
        p.name,
        i.id,
        i.title,
        i.severity,
        sol.summary
    """

    result = graph.ro_query(query)
    return result.result_set


def ask_agent(question):
    question_lower = question.lower()

    rows = get_graph_data()

    if not rows:
        return "I couldn't find connected service information in the graph."

    # Find information about the Payments API.
    matching_rows = [
        row for row in rows
        if row[0] and row[0].lower() in question_lower
    ]

    # Also recognize common ways of mentioning this service.
    if not matching_rows and (
        "payment" in question_lower
        or "timeout" in question_lower
        or "incident" in question_lower
        or "owner" in question_lower
        or "solution" in question_lower
        or "fix" in question_lower
    ):
        matching_rows = [
            row for row in rows
            if row[0] and "payment" in row[0].lower()
        ]

    if not matching_rows:
        return (
            "I couldn't identify a matching service in the graph. "
            "Try asking about the Payments API."
        )

    answers = []

    for row in matching_rows:
        service, owner, incident_id, title, severity, solution = row

        if "who owns" in question_lower or "owner" in question_lower:
            answers.append(
                f"The {service} is owned by {owner}."
            )

        elif (
            "incident" in question_lower
            or "timeout" in question_lower
            or "problem" in question_lower
            or "happened" in question_lower
        ):
            if incident_id:
                answers.append(
                    f"Incident {incident_id}: {title}. "
                    f"Severity: {severity}."
                )
            else:
                answers.append(
                    f"No incident was found for {service}."
                )

        elif (
            "solution" in question_lower
            or "fix" in question_lower
            or "resolved" in question_lower
            or "how" in question_lower
        ):
            if solution:
                answers.append(
                    f"Related solution recorded for {service}: "
                    f"{solution}"
                )
            else:
                answers.append(
                    f"No solution is recorded for {service}."
                )

        else:
            answers.append(
                f"Service: {service}\n"
                f"Owner: {owner}\n"
                f"Incident: {incident_id or 'None found'}\n"
                f"Problem: {title or 'None found'}\n"
                f"Severity: {severity or 'Unknown'}\n"
                f"Related solution: {solution or 'None recorded'}"
            )

    return "\n".join(answers)


if __name__ == "__main__":
    print("TraceDesk AI is ready!")
    print("Ask about the Payments API.")
    print("Type 'exit' to quit.")

    while True:
        question = input("\nYou: ").strip()

        if question.lower() in ("exit", "quit"):
            print("TraceDesk AI: Goodbye!")
            break

        if not question:
            continue

        try:
            answer = ask_agent(question)
            print("\nTraceDesk AI:", answer)
        except Exception as error:
            print("Error while querying FalkorDB:", error)
