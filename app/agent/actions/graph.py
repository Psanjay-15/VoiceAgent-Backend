from __future__ import annotations

from collections.abc import Awaitable, Callable

from langgraph.graph import END, StateGraph

from app.agent.actions.models import ActionState, ActionType

ActionNode = Callable[[ActionState], Awaitable[ActionState]]
RouteNode = Callable[[ActionState], ActionType]


def build_business_action_graph(
    *,
    decide: ActionNode,
    route: RouteNode,
    admin_followup: ActionNode,
    in_person: ActionNode,
    online: ActionNode,
    none: ActionNode,
):
    graph = StateGraph(ActionState)
    graph.add_node("decide", decide)
    graph.add_node("admin_followup", admin_followup)
    graph.add_node("in_person", in_person)
    graph.add_node("online", online)
    graph.add_node("none", none)
    graph.set_entry_point("decide")
    graph.add_conditional_edges(
        "decide",
        route,
        {
            "admin_followup": "admin_followup",
            "in_person_meet": "in_person",
            "online_meet": "online",
            "none": "none",
        },
    )
    graph.add_edge("admin_followup", END)
    graph.add_edge("in_person", END)
    graph.add_edge("online", END)
    graph.add_edge("none", END)
    return graph.compile()
