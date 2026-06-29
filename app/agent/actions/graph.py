from __future__ import annotations

from collections.abc import Callable
from typing import Awaitable

from langgraph.graph import END, StateGraph

from app.agent.actions.models import ActionState, ActionType

AsyncNode = Callable[[ActionState], Awaitable[ActionState]]
RouteFn = Callable[[ActionState], ActionType]


def build_business_action_graph(
    *,
    decide: AsyncNode,
    route: RouteFn,
    in_person: AsyncNode,
    online: AsyncNode,
    material: AsyncNode,
    none: AsyncNode,
):
    graph = StateGraph(ActionState)
    graph.add_node("decide", decide)
    graph.add_node("in_person", in_person)
    graph.add_node("online", online)
    graph.add_node("material", material)
    graph.add_node("none", none)
    graph.set_entry_point("decide")
    graph.add_conditional_edges(
        "decide",
        route,
        {
            "in_person_meet": "in_person",
            "online_meet": "online",
            "send_material": "material",
            "none": "none",
        },
    )
    graph.add_edge("in_person", END)
    graph.add_edge("online", END)
    graph.add_edge("material", END)
    graph.add_edge("none", END)
    return graph.compile()
