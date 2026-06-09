import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agent_state import AgentState
from settings import llm

class ExecutionRoadmap(BaseModel):
    """Schema to force a strict, linear tool dependency pipeline."""
    reasoning: str = Field(description="Step-by-step logic detailing why this specific sequence path is required.")
    ordered_path: List[str] = Field(description="The exact order chain of sub-agent IDs to execute, e.g., ['B', 'D']")

class LoanParameters(BaseModel):
    """Schema to safely extract variable entities from conversational text."""
    loan_amount: Optional[float] = Field(None, description="The target principal loan amount requested by the user.")
    max_acceptable_emi: Optional[float] = Field(None, description="The maximum monthly installment boundary specified by the user.")

def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes the user's query intent, builds a deterministic execution map,
    and extracts entity parameters directly into the graph state.
    """
    user_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    if not user_messages:
        return {"extracted_data": {**state.get("extracted_data", {}), "ordered_path": [], "current_step_index": 0}}
    
    last_query = user_messages[-1].content
    print(f"\n[Supervisor]: Orchestrating request: '{last_query}'")

    system_routing_guide = """You are the Global Dependency Architect Matrix for IDFC FIRST Bank.
    Your job is to analyze incoming user queries and output a strict, linear pipeline execution path of specialized sub-agents.

    AVAILABLE SPECIALIST SUB-AGENTS:
    - B (Offers Specialist): Fetches campaign interest rates, credit caps, and profile-specific pre-approved ceilings.
    - C (Transaction Analyst): Crunches, filters, ranks, and aggregates multi-month financial transaction histories.
    - D (Loan Calculator): Executes compound reducing balance amortization mathematics using real verified loan rates.
    - E (Credit Card Specialist): Calculates retail merchant checkout instant discounts, cashback boundaries, and point rewards.
    - F (Banking Core Specialist): Extracts raw ledger tracking metadata, balances, and owned account portfolio types.

    CRITICAL PIPELINE DEPENDENCY MATRIX RULES:
    1. LOAN DEPENDENCY RULE: If a calculation (D) requires an interest rate or tier ceiling from a profile offer, you MUST execute B before D so the rate is discovered first.
    2. TRANSACTION BALANCE RULE: If an account status verification depends on past trends, you MUST execute C before F.
    3. EFFICIENCY CONSTRAINT (STRICT RULE): Never include transaction analysis (C) or banking core operations (F) for hypothetical loan simulations or standard interest queries unless the user explicitly requests transaction auditing, tracking histories, or balance status statements. If they only ask for loan terms or interest calculations, use ONLY ['B', 'D'].
    4. CONTEXT CORRUPTION PREVENTION: Never include an unrelated agent. If a user asks for a Personal Loan, do NOT include Credit Card tools (E) under any circumstance.
    """

    # 1. Determine optimal pipeline route
    try:
        structured_llm = llm.with_structured_output(ExecutionRoadmap)
        roadmap = structured_llm.invoke([
            SystemMessage(content=system_routing_guide),
            HumanMessage(content=f"Analyze intent and compile roadmap path for query: '{last_query}'")
        ])
        ordered_path = roadmap.ordered_path
    except Exception:
        ordered_path = ["B", "D"]

    # 2. Extract numeric entities matching input specifications
    extraction_prompt = """You are an accurate data extraction utility. Your sole job is to parse numeric values 
    from a retail banking customer query. Convert text values like '4 lakh' or '4L' to raw floats (e.g., 400000.0). 
    If a value is entirely missing from the query, leave its field as null. Do not invent or assume data."""
        
    try:
        structured_extractor = llm.with_structured_output(LoanParameters)
        extracted = structured_extractor.invoke([
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=last_query)
        ])
        loan_amount = extracted.loan_amount
        max_acceptable_emi = extracted.max_acceptable_emi
    except Exception:
        loan_amount, max_acceptable_emi = None, None

    print(f" -> [Generated Path]: {' -> '.join(ordered_path)}")
    print(f" -> [Extracted Entities]: Amount: {loan_amount}, Max EMI: {max_acceptable_emi}")

    # Maintain existing dict references
    updated_extracted = dict(state.get("extracted_data", {}))
    updated_extracted.update({
        "ordered_path": ordered_path,
        "current_step_index": 0,
        "loan_amount": loan_amount,
        "max_acceptable_emi": max_acceptable_emi
    })

    return {"extracted_data": updated_extracted}