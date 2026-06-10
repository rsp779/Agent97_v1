import json
from typing import Dict, Any, Literal
from langgraph.graph import StateGraph, END
from agent_state import AgentState
from supervisor_agent import supervisor_node
from workers_agent import (
    offers_specialist_node,
    transaction_specialist_node,
    loan_product_calculator_node,
    home_loan_specialist_node,
    gold_loan_specialist_node,
    credit_card_specialist_node,
    banking_specialist_node
)
from langchain_core.messages import SystemMessage, AIMessage
from settings import llm

def synthesis_node(state: AgentState) -> Dict[str, Any]:
    print("   [*] Synthesizing final response package...")
    
    semantic_logic_guard = """You are a customer-facing banking assistant for IDFC FIRST Bank.
Write only plain English.
Do not return JSON, code blocks, or labels like next_actor / should_exit / reason.
Use only the verified values from the tool messages.
If no valid offer or calculation is available, say that clearly in one short sentence and ask for the missing detail.
Keep the reply brief, readable, and professional.
"""
    payload = [
        SystemMessage(content=semantic_logic_guard)
    ] + state["messages"]

    final_text = llm.invoke(payload).content.strip()

    try:
        parsed = json.loads(final_text)
        if isinstance(parsed, dict):
            final_text = parsed.get("content") or parsed.get("reason") or final_text
    except Exception:
        pass

    return {"messages": [AIMessage(content=final_text)]}

def router_edge(state: AgentState) -> Literal[
    "offers_specialist",
    "transaction_specialist",
    "loan_product_calculator",
    "home_loan_specialist",
    "gold_loan_specialist",
    "credit_card_specialist",
    "banking_specialist",
    "synthesis",
]:
    """Deterministic routing edge. Determines the next agent from the ordered path matrix."""
    extracted_data = state.get("extracted_data", {})
    path = extracted_data.get("ordered_path", [])
    idx = extracted_data.get("current_step_index", 0)

    # If we reached the end of the planned route pipeline, go to synthesis
    if idx >= len(path):
        return "synthesis"

    next_agent_id = path[idx]
    agent_name_mapping = {
        "B": "offers_specialist",
        "C": "transaction_specialist",
        "D": "loan_product_calculator",
        "G": "home_loan_specialist",
        "H": "gold_loan_specialist",
        "E": "credit_card_specialist",
        "F": "banking_specialist",
    }
    next_node = agent_name_mapping.get(next_agent_id, next_agent_id)

    if next_node not in {
        "offers_specialist",
        "transaction_specialist",
        "loan_product_calculator",
        "home_loan_specialist",
        "gold_loan_specialist",
        "credit_card_specialist",
        "banking_specialist",
        "synthesis",
    }:
        next_node = "synthesis"

    print(
        f" -> [Router Routing Edge]: Route path step {idx+1}/{len(path)}. "
        f"Diverting execution to Sub-Agent [{next_node}]"
    )
    return next_node

# Compile the Graph State Machine Structure cleanly
builder = StateGraph(AgentState)

builder.add_node("supervisor", supervisor_node)
builder.add_node("offers_specialist", offers_specialist_node)
builder.add_node("transaction_specialist", transaction_specialist_node)
builder.add_node("loan_product_calculator", loan_product_calculator_node)
builder.add_node("home_loan_specialist", home_loan_specialist_node)
builder.add_node("gold_loan_specialist", gold_loan_specialist_node)
builder.add_node("credit_card_specialist", credit_card_specialist_node)
builder.add_node("banking_specialist", banking_specialist_node)
builder.add_node("synthesis", synthesis_node)

builder.set_entry_point("supervisor")

# Define explicitly how the graph routes out of the supervisor node
builder.add_conditional_edges(
    "supervisor",
    router_edge,
    {
        "offers_specialist": "offers_specialist",
        "transaction_specialist": "transaction_specialist",
        "loan_product_calculator": "loan_product_calculator",
        "home_loan_specialist": "home_loan_specialist",
        "gold_loan_specialist": "gold_loan_specialist",
        "credit_card_specialist": "credit_card_specialist",
        "banking_specialist": "banking_specialist",
        "synthesis": "synthesis",
    }
)

# Connect all worker nodes back to the router edge evaluation checkpoint
for node_id in [
    "offers_specialist",
    "transaction_specialist",
    "loan_product_calculator",
    "home_loan_specialist",
    "gold_loan_specialist",
    "credit_card_specialist",
    "banking_specialist",
]:
    builder.add_conditional_edges(
        node_id,
        router_edge,
        {
            "offers_specialist": "offers_specialist",
            "transaction_specialist": "transaction_specialist",
            "loan_product_calculator": "loan_product_calculator",
            "home_loan_specialist": "home_loan_specialist",
            "gold_loan_specialist": "gold_loan_specialist",
            "credit_card_specialist": "credit_card_specialist",
            "banking_specialist": "banking_specialist",
            "synthesis": "synthesis",
        }
    )

builder.add_edge("synthesis", END)
banking_financial_graph = builder.compile()
