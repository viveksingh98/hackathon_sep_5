from langgraph.graph import END, START, StateGraph

from graph.nodes import cookbook, log_reader, notification, remediation, ticket
from graph.state import IncidentState


def build_graph(llm_client, slack_client):
    graph = StateGraph(IncidentState)
    graph.add_node("log_reader", log_reader.run(llm_client))
    graph.add_node("remediation", remediation.run(llm_client))
    graph.add_node("ticket", ticket.run())
    graph.add_node("cookbook", cookbook.run())
    graph.add_node("notification", notification.run(slack_client))

    graph.add_edge(START, "log_reader")
    graph.add_edge("log_reader", "remediation")
    graph.add_edge("remediation", "ticket")
    graph.add_edge("ticket", "cookbook")
    graph.add_edge("cookbook", "notification")
    graph.add_edge("notification", END)

    return graph.compile()
