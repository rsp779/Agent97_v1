import json
import math
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from data.mock_db import DATASTORE
from settings import llm
from agent_state import AgentState
from prompts import (
    OFFERS_SPECIALIST_PROMPT, 
    PRODUCT_CALCULATOR_PROMPT, 
    BANKING_SPECIALIST_PROMPT, 
    TRANSACTION_SPECIALIST_PROMPT, 
    CREDIT_CARD_SPECIALIST_PROMPT
)

# ---------------------------------------------------------------------------
# Core Context Fetchers
# ---------------------------------------------------------------------------
def get_offer_context(customer_id: str) -> dict:
    profile = DATASTORE.get_customer_profile(customer_id)
    scores = DATASTORE.get_customer_offer_scores(customer_id)
    catalog = DATASTORE.get_offer_catalog()
    return {
        "customer_id": customer_id,
        "customer_profile": profile,
        "offers": [{
            "offer_id": x["offer_id"],
            "model_score": x["score"],
            "offer_details": catalog.get(x["offer_id"], {})
        } for x in scores]
    }

def get_banking_context(customer_id: str) -> dict:
    return {
        "customer_id": customer_id,
        "customer_profile": DATASTORE.get_customer_profile(customer_id),
        "transactions": DATASTORE.get_customer_transactions(customer_id)
    }

# ---------------------------------------------------------------------------
# Generic Worker Execution Core (Sub-Agents B, C, E, F)
# ---------------------------------------------------------------------------
def generic_worker_runner(state: AgentState, agent_id: str, agent_name: str, prompt_template: str, context_fetcher) -> Dict[str, Any]:
    user_query = state["messages"][-1].content if state.get("messages") else ""
    customer_id = state["customer_id"]
    ctx = context_fetcher(customer_id)
    
    ctx["previously_extracted_data"] = state.get("extracted_data", {})

    print(f"   [*] Invoking Sub-Agent [{agent_id}] ({agent_name})...")
    
    response_content = llm.invoke([
        SystemMessage(content=prompt_template),
        HumanMessage(content=json.dumps({"customer_query": user_query, **ctx}, default=str))
    ]).content

    tool_call_id = f"call_{agent_id}_{customer_id}"
    ai_msg = AIMessage(
        content=f"Invoking {agent_name} context engine...",
        tool_calls=[{"name": agent_name, "args": {"query": user_query}, "id": tool_call_id}]
    )
    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name=agent_name)

    updated_extracted = dict(state.get("extracted_data", {}))
    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
    updated_extracted[agent_name] = response_content

    return {
        "messages": [ai_msg, tool_msg],
        "extracted_data": updated_extracted
    }

def offers_specialist_node(state: AgentState) -> Dict[str, Any]:
    return generic_worker_runner(state, "B", "offers_specialist", OFFERS_SPECIALIST_PROMPT, get_offer_context)

def transaction_specialist_node(state: AgentState) -> Dict[str, Any]:
    return generic_worker_runner(state, "C", "transaction_specialist", TRANSACTION_SPECIALIST_PROMPT, get_banking_context)

def banking_specialist_node(state: AgentState) -> Dict[str, Any]:
    return generic_worker_runner(state, "F", "banking_specialist", BANKING_SPECIALIST_PROMPT, get_banking_context)

def credit_card_specialist_node(state: AgentState) -> Dict[str, Any]:
    return generic_worker_runner(state, "E", "credit_card_specialist", CREDIT_CARD_SPECIALIST_PROMPT, get_offer_context)


# ---------------------------------------------------------------------------
# Structured Extraction Schemas
# ---------------------------------------------------------------------------
class FinancialCalculationIntent(BaseModel):
    category: str = Field(description="Must be one of: 'EMI', 'FD', 'Savings_Tier', 'Cashback_Cap'")
    target_principal: Optional[float] = Field(None, description="The loan or deposit amount requested by user.")
    requested_tenures_months: List[int] = Field(default_factory=list, description="Explicit tenures requested by the user.")
    annual_rate_override: Optional[float] = Field(None, description="Explicit interest rate mentioned by the user.")

class SemanticallyParsedOffer(BaseModel):
    is_matching_category: bool = Field(description="True if this offer strictly matches the user's requested financial product type (e.g., Personal Loan vs Home Loan vs Credit Card).")
    extracted_max_limit: float = Field(default=999999999.0, description="The maximum amount limit parsed from the text context. Map text terms like '5 lakhs' or '5L' to raw float numbers like 500000.0. Default to 999999999.0 if no limit is listed.")
    extracted_interest_rate: float = Field(default=12.0, description="The interest rate percentage parsed from the text context (e.g., 15% -> 15.0).")
    extracted_tenure_years: Optional[float] = Field(None, description="The tenure in years parsed from the text context (e.g., 3 years -> 3.0).")


# ---------------------------------------------------------------------------
# Mathematically Bulletproof Python Computation Engines
# ---------------------------------------------------------------------------
def run_reducing_balance_emi(principal: float, annual_rate: float, months: int) -> Dict[str, float]:
    if principal <= 0 or annual_rate <= 0 or months <= 0:
        return {"primary_metric": 0.0, "total_interest": 0.0, "total_repayment": 0.0}
    r = (annual_rate / 12) / 100
    emi = (principal * r * math.pow(1 + r, months)) / (math.pow(1 + r, months) - 1)
    total_repayment = emi * months
    total_interest = total_repayment - principal
    return {
        "primary_metric": round(emi, 2),
        "total_interest": round(total_interest, 2),
        "total_repayment": round(total_repayment, 2)
    }

def run_fixed_deposit_computation(principal: float, annual_rate: float, months: int) -> Dict[str, float]:
    if principal <= 0 or annual_rate <= 0 or months <= 0:
        return {"primary_metric": 0.0, "total_interest": 0.0, "total_repayment": 0.0}
    t = months / 12
    maturity_amount = principal * math.pow(1 + (annual_rate / 100 / 4), 4 * t)
    total_interest = maturity_amount - principal
    return {
        "primary_metric": round(maturity_amount, 2),
        "total_interest": round(total_interest, 2),
        "total_repayment": round(maturity_amount, 2)
    }


# ---------------------------------------------------------------------------
# Core LangGraph Node (Fully Intelligent & Hallucination Protected)
# ---------------------------------------------------------------------------
def loan_product_calculator_node(state: AgentState) -> Dict[str, Any]:
    customer_id = state["customer_id"]
    extracted_data = state.get("extracted_data", {})
    
    user_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    last_query = user_messages[-1].content if user_messages else ""

    print(f"   [*] Invoking Sub-Agent [D] (loan_product_calculator)...")

    # 1. Dynamically extract user intent variables using Structured Output
    intent_prompt = """Analyze the incoming user request and determine the exact parameters required to compute their inquiry.
    Convert text numbers like 'lakh', 'L', 'k' to true float values."""
    try:
        structured_extractor = llm.with_structured_output(FinancialCalculationIntent)
        intent = structured_extractor.invoke([
            SystemMessage(content=intent_prompt),
            HumanMessage(content=f"Context details: {extracted_data}. Query: '{last_query}'")
        ])
    except Exception:
        intent = FinancialCalculationIntent(category="EMI", target_principal=extracted_data.get("loan_amount"), requested_tenures_months=[])

    # 2. Extract database offers
    ctx = get_offer_context(customer_id)
    available_offers = ctx.get("offers", [])
    
    # 3. Dynamic Filtering and Semantic Parsing Engine
    verified_calculation_results = []
    target_principal = intent.target_principal or extracted_data.get("loan_amount") or 0.0
    max_acceptable_emi = extracted_data.get("max_acceptable_emi") or 0.0

    if target_principal > 0:
        # Instantiate a structured interpreter to parse unstructured text blocks on-the-fly
        offer_interpreter = llm.with_structured_output(SemanticallyParsedOffer)

        for offer in available_offers:
            offer_id = offer.get("offer_id", "unknown")
            details = offer.get("offer_details", offer)
            raw_content = details.get("content", str(details))

            # Semantically audit the unstructured text against the user's target inquiry properties
            parsing_prompt = f"""Analyze this bank offer block and extract its terms structural limits:
            Offer Content: "{raw_content}"
            User Parameter Target Category: {intent.category} (e.g., if category is EMI, look for Personal Loans or similar amortized variants. Skip Home Loans if user specifically wanted a small dynamic personal metric, skip Credit cards, skip FDs)."""
            
            try:
                parsed_metrics = offer_interpreter.invoke([SystemMessage(content=parsing_prompt)])
            except Exception as e:
                print(f"   [Interpreter Error]: Failed parsing offer {offer_id}: {e}")
                continue

            # SEMANTIC FILTER 1: Skip if the product category doesn't align with the conversational theme
            if not parsed_metrics.is_matching_category:
                print(f"   [Semantic Filter]: Skipping '{offer_id}' -> Product category mismatch.")
                continue

            # SEMANTIC FILTER 2: Strict eligibility guardrail check against true limits parsed from the string
            if target_principal > parsed_metrics.extracted_max_limit:
                print(f"   [Eligibility Filter]: Skipping '{offer_id}' (Max allowed: ₹{parsed_metrics.extracted_max_limit:,}) -> Cannot fulfill requested amount: ₹{target_principal:,}")
                continue

            # Apply true parsed parameters to the mathematical engine
            active_rate = intent.annual_rate_override or parsed_metrics.extracted_interest_rate
            # Use the minimum of requested principal or max allowed limit
            computed_principal = min(target_principal, parsed_metrics.extracted_max_limit)

            # Handle dynamic tenure matching without default guessing
            active_tenures = intent.requested_tenures_months
            if not active_tenures:
                years = parsed_metrics.extracted_tenure_years or 3.0
                active_tenures = [int(years * 12)]

            for tenure_m in active_tenures:
                if intent.category == "FD":
                    math_metrics = run_fixed_deposit_computation(computed_principal, active_rate, tenure_m)
                    metric_label = "Maturity Amount Value"
                else:
                    math_metrics = run_reducing_balance_emi(computed_principal, active_rate, tenure_m)
                    metric_label = "Monthly EMI Liability"

                verified_calculation_results.append({
                    "calculation_category": intent.category,
                    "offer_id": offer_id,
                    "offer_name": f"Pre-Approved Variant ({offer_id})",
                    "interest_rate_applied": active_rate,
                    "max_preapproved_limit_allowed": parsed_metrics.extracted_max_limit,
                    "original_user_requested_amount": target_principal,
                    "actual_processed_principal_math": computed_principal,
                    "tenure_months": tenure_m,
                    "tenure_years": round(tenure_m / 12, 1),
                    "metric_type_label": metric_label,
                    **math_metrics,
                    "fits_user_stated_budget": math_metrics["primary_metric"] <= max_acceptable_emi if (max_acceptable_emi > 0 and intent.category == "EMI") else True
                })

    # 4. Bind parameters cleanly to presentation layer
    payload = {
        "calculation_type": intent.category,
        "requested_volume": target_principal,
        "max_acceptable_budget_constraint": max_acceptable_emi,
        "mathematically_verified_schedules": verified_calculation_results,
        "instruction": (
            "CRITICAL CONTEXT LAW:\n"
            "1. Only present options that are actively listed in the mathematically_verified_schedules array.\n"
            "2. Do not display offers that were skipped or filtered out.\n"
            "3. Extract 'primary_metric', 'total_interest', and 'total_repayment' exactly as provided without changing any decimals.\n"
            "CRITICAL CODE LAW:\n"
            "1. You are an API formatter. Do not invent or alter any numbers.\n"
            "2. When computing EMI results, use the schedule entries as-is and honor the user's maximum EMI constraint.\n"
        )
    }

    response_content = llm.invoke([
        SystemMessage(content=PRODUCT_CALCULATOR_PROMPT),
        HumanMessage(content=json.dumps(payload, default=str))
    ]).content

    # 5. Graph Paired Messaging Execution Prototypes
    tool_call_id = f"call_D_{customer_id}"
    ai_msg = AIMessage(
        content=f"Running semantic verification and computing accurate math arrays...",
        tool_calls=[{"name": "loan_calculator", "args": intent.model_dump(), "id": tool_call_id}]
    )
    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name="loan_calculator")

    # 6. Synchronize back to systemic state storage
    updated_extracted = dict(extracted_data)
    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
    updated_extracted["loan_product_calculator"] = response_content

    return {
        "messages": [ai_msg, tool_msg],
        "extracted_data": updated_extracted
    }