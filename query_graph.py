
from falkordb import FalkorDB

client = FalkorDB(host="localhost", port=6379)
graph = client.select_graph("tracedesk")

query = """
MATCH (i:Incident)-[:AFFECTS]->(s:Service)
MATCH (p:Person)-[:OWNS]->(s)
MATCH (i)-[:FIXED_BY]->(sol:Solution)
WHERE s.name = 'Payments API'
RETURN i.id, i.title, p.name, sol.summary
"""

result = graph.ro_query(query)

for row in result.result_set:
    print("Incident:", row[0])
    print("Problem:", row[1])
    print("Service owner:", row[2])
    print("Related solution:", row[3])
