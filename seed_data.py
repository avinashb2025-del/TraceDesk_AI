
from falkordb import FalkorDB

client = FalkorDB(host="localhost", port=6379)
graph = client.select_graph("tracedesk")

graph.query("""
MERGE (p:Person {id: 'P1'})
SET p.name = 'Maya',
    p.role = 'Backend Engineer'

MERGE (s:Service {id: 'S1'})
SET s.name = 'Payments API'

MERGE (pr:Project {id: 'PR1'})
SET pr.name = 'Checkout Platform'

MERGE (i:Incident {id: 'INC-101'})
SET i.title = 'Payment requests timing out',
    i.severity = 'High'

MERGE (sol:Solution {id: 'SOL-101'})
SET sol.summary =
    'Review connection pool limits and connection release'

MERGE (p)-[:OWNS]->(s)
MERGE (p)-[:WORKED_ON]->(pr)
MERGE (pr)-[:USES]->(s)
MERGE (i)-[:AFFECTS]->(s)
MERGE (i)-[:FIXED_BY]->(sol)
""")

print("TraceDesk knowledge graph created!")
