from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from agent_state import AgentState
from supervisor_agent import supervisor_node
from workers_agent import (
    offers_specialist_node,
    transaction_specialist_node,
    loan_product_calculator_node,
    credit_card_specialist_node,
    banking_specialist_node
)
from prompts import SUPERVISOR_SYSTEM_PROMPT
from langchain_core.messages import SystemMessage, AIMessage
from settings import llm

def synthesis_node(state: AgentState) -> Dict[str, Any]:
    print("   [*] Synthesizing final response package...")
    
    semantic_logic_guard = """You are a strict financial communications compiler for IDFC FIRST Bank.
Analyze the tool messages provided above and present the metrics directly to the user.
Evaluate constraints dynamically, compute exact math values provided by tools, and maintain absolute alignment with verified banking numbers.
"""
    payload = [
        SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT),
        SystemMessage(content=semantic_logic_guard)
    ] + state["messages"]

    final_text = llm.invoke(payload).content.strip()
    return {"messages": [AIMessage(content=final_text)]}

def router_edge(state: AgentState) -> Literal["B", "C", "D", "E", "F", "synthesis"]:
    """Deterministic routing edge. Determines the next agent from the ordered path matrix."""
    extracted_data = state.get("extracted_data", {})
    path = extracted_data.get("ordered_path", [])
    idx = extracted_data.get("current_step_index", 0)
    
    # If we reached the end of the planned route pipeline, go to synthesis
    if idx >= len(path):
        return "synthesis"
        
    next_agent_id = path[idx]
    
    print(f" -> [Router Routing Edge]: Route path step {idx+1}/{len(path)}. Diverting execution to Sub-Agent [{next_agent_id}]")
    
    mapping = {"B": "B", "C": "C", "D": "D", "E": "E", "F": "F"}
    return mapping.get(next_agent_id, "synthesis")

# Compile the Graph State Machine Structure cleanly
builder = StateGraph(AgentState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("B", offers_specialist_node)
builder.add_node("C", transaction_specialist_node)
builder.add_node("D", loan_product_calculator_node)
builder.add_node("E", credit_card_specialist_node)
builder.add_node("F", banking_specialist_node)
builder.add_node("synthesis", synthesis_node)

builder.set_entry_point("supervisor")

# Define explicitly how the graph routes out of the supervisor node
builder.add_conditional_edges(
    "supervisor",
    router_edge,
    {"B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "synthesis": "synthesis"}
)

# Connect all worker nodes back to the router edge evaluation checkpoint
for node_id in ["B", "C", "D", "E", "F"]:
    builder.add_conditional_edges(
        node_id,
        router_edge,
        {"B": "B", "C": "C", "D": "D", "E": "E", "F": "F", "synthesis": "synthesis"}
    )

builder.add_edge("synthesis", END)
banking_financial_graph = builder.compile()