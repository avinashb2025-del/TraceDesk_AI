from falkordb import FalkorDB

client = FalkorDB(host="localhost", port=6379)
graph = client.select_graph("tracedesk")

result = graph.query(
    "RETURN 'FalkorDB connected!' AS message"
)

print(result.result_set)
