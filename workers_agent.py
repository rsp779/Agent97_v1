import json
import math
import ssl
from typing import Dict, Any, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
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
    CREDIT_CARD_SPECIALIST_PROMPT,
    HOME_LOAN_SPECIALIST_PROMPT,
    GOLD_LOAN_SPECIALIST_PROMPT,
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
# External Gold Price Fetch Helpers


def fetch_current_gold_price() -> Dict[str, Any]:
    headers = {"User-Agent": "Mozilla/5.0"}
    endpoints = [
        "https://data-asg.goldprice.org/dbXRates/USD",
        "https://api.metals.live/v1/spot/gold",
    ]
    context = ssl.create_default_context()

    for url in endpoints:
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=10, context=context) as response:
                payload = response.read().decode("utf-8")
            data = json.loads(payload)
        except (HTTPError, URLError, json.JSONDecodeError, ValueError) as exc:
            print(f"   [GoldPrice] Failed to fetch from {url}: {exc}")
            continue

        if isinstance(data, dict):
            items = data.get("items") or data.get("data")
            if isinstance(items, list) and items:
                item = items[0]
                price = None
                for key in ["xauPrice", "price", "last"]:
                    if isinstance(item, dict) and key in item:
                        price = item[key]
                        break
                if price is not None:
                    return {
                        "price_per_ounce": float(price),
                        "currency": "USD",
                        "source": url,
                    }
            if "price" in data:
                return {
                    "price_per_ounce": float(data["price"]),
                    "currency": "USD",
                    "source": url,
                }
        elif isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and "price" in first:
                return {
                    "price_per_ounce": float(first["price"]),
                    "currency": "USD",
                    "source": url,
                }

    # Fallback: Use conservative gold price estimate (₹1.5L reference for typical pledges)
    # Fallback price: $50/ounce ≈ ₹1,550/gram (conservative estimate)
    print("   [GoldPrice] All endpoints failed. Using fallback price estimate.")
    return {
        "price_per_ounce": 50.0,
        "currency": "USD",
        "source": "fallback_conservative_estimate",
        "is_fallback": True,
    }


def convert_gold_quantity_to_grams(grams: Optional[float], tolas: Optional[float], ounces: Optional[float]) -> float:
    if grams is not None and grams > 0:
        return grams
    if tolas is not None and tolas > 0:
        return tolas * 11.6638038
    if ounces is not None and ounces > 0:
        return ounces * 31.1034768
    return 0.0

# ---------------------------------------------------------------------------
# Generic Worker Execution Core (Sub-Agents B, C, E, F)
# ---------------------------------------------------------------------------
def generic_worker_runner(state: AgentState, agent_id: str, agent_name: str, prompt_template: str, context_fetcher) -> Dict[str, Any]:
    user_query = state["messages"][-1].content if state.get("messages") else ""
    customer_id = state["customer_id"]
    ctx = context_fetcher(customer_id)
    
    ctx["previously_extracted_data"] = state.get("extracted_data", {})
    ctx["customer_memory"] = {
        "long_term": state.get("extracted_data", {}).get("long_term_memory"),
        "short_term": state.get("extracted_data", {}).get("short_term_memory"),
    }

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


def home_loan_specialist_node(state: AgentState) -> Dict[str, Any]:
    return generic_worker_runner(state, "G", "home_loan_specialist", HOME_LOAN_SPECIALIST_PROMPT, get_offer_context)


def gold_loan_specialist_node(state: AgentState) -> Dict[str, Any]:
    customer_id = state["customer_id"]
    user_query = state["messages"][-1].content if state.get("messages") else ""
    print(f"   [*] Invoking Sub-Agent [H] (gold_loan_specialist)...")

    class GoldLoanRequest(BaseModel):
        gold_quantity_grams: Optional[float] = Field(None, description="Gold quantity pledged in grams.")
        gold_quantity_tolas: Optional[float] = Field(None, description="Gold quantity pledged in tolas.")
        gold_quantity_ounces: Optional[float] = Field(None, description="Gold quantity pledged in ounces.")
        requested_loan_amount: Optional[float] = Field(None, description="The requested gold loan amount.")
        requested_tenure_months: List[int] = Field(default_factory=list, description="Requested loan tenure in months.")
        max_acceptable_emi: Optional[float] = Field(None, description="The maximum EMI the customer can pay.")

    extraction_prompt = """You are a precise extraction assistant for gold loan customer requests.
Extract the following values from the customer query. Convert numeric words like 'lakh' or 'tola' to raw float values.
If a value is missing, leave it null or an empty list.

Fields:
- gold_quantity_grams
- gold_quantity_tolas
- gold_quantity_ounces
- requested_loan_amount
- requested_tenure_months
- max_acceptable_emi
"""
    try:
        structured_extractor = llm.with_structured_output(GoldLoanRequest)
        gold_request = structured_extractor.invoke([
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=user_query)
        ])
    except Exception as exc:
        print(f"   [GoldLoan] Extraction failed: {exc}")
        gold_request = GoldLoanRequest()

    quantity_in_grams = convert_gold_quantity_to_grams(
        gold_request.gold_quantity_grams,
        gold_request.gold_quantity_tolas,
        gold_request.gold_quantity_ounces,
    )

    if quantity_in_grams <= 0:
        response_content = "To calculate your gold loan, please tell me the quantity of gold you are pledging in grams, tolas, or ounces."
    else:
        try:
            price_data = fetch_current_gold_price()
            price_per_ounce = price_data["price_per_ounce"]
            currency = price_data["currency"]
            is_fallback_price = price_data.get("is_fallback", False)
            price_per_gram = price_per_ounce / 31.1034768
            total_gold_value = round(quantity_in_grams * price_per_gram, 2)
            min_disbursement = round(total_gold_value * 0.8, 2)
            max_disbursement = round(total_gold_value * 1.2, 2)

            if gold_request.requested_loan_amount is not None:
                requested_amount = gold_request.requested_loan_amount
                if requested_amount < min_disbursement or requested_amount > max_disbursement:
                    amount_message = (
                        f"Your requested gold loan amount of {requested_amount:.2f} {currency} is outside the current eligible range. "
                        f"Based on {quantity_in_grams:.2f} grams of gold at current price, the eligible loan range is {min_disbursement:.2f} to {max_disbursement:.2f} {currency}."
                    )
                else:
                    amount_message = (
                        f"Your requested amount of {requested_amount:.2f} {currency} falls within the eligible gold loan disbursement range of "
                        f"{min_disbursement:.2f} to {max_disbursement:.2f} {currency}."
                    )
            else:
                amount_message = (
                    f"Based on {quantity_in_grams:.2f} grams of gold at current price, the eligible gold loan disbursement range is "
                    f"{min_disbursement:.2f} to {max_disbursement:.2f} {currency}."
                )

            # Add fallback disclaimer if applicable
            fallback_note = ""
            if is_fallback_price:
                fallback_note = (
                    "\n\n**Note:** We used a conservative reference price (USD $50/oz) as live market data was unavailable. "
                    "For the most accurate disbursement range, please provide the current market gold price, "
                    "and we will recalculate your eligibility."
                )

            payload = {
                "customer_query": user_query,
                "gold_quantity_grams": quantity_in_grams,
                "requested_loan_amount": gold_request.requested_loan_amount,
                "requested_tenure_months": gold_request.requested_tenure_months,
                "max_acceptable_emi": gold_request.max_acceptable_emi,
                "current_price_source": price_data.get("source"),
                "price_per_ounce": price_per_ounce,
                "price_per_gram": round(price_per_gram, 2),
                "total_gold_value": total_gold_value,
                "min_disbursement": min_disbursement,
                "max_disbursement": max_disbursement,
                "amount_message": amount_message,
                "fallback_note": fallback_note,
            }

            response_content = llm.invoke([
                SystemMessage(content=GOLD_LOAN_SPECIALIST_PROMPT),
                HumanMessage(content=json.dumps(payload, default=str))
            ]).content
        except Exception as exc:
            print(f"   [GoldLoan] Unexpected error: {exc}")
            response_content = (
                "We encountered an error while calculating your gold loan eligibility. "
                "Please try again or contact our customer service team for assistance."
            )

    tool_call_id = f"call_H_{customer_id}"
    ai_msg = AIMessage(
        content=f"Invoking gold_loan_specialist with current gold pricing...",
        tool_calls=[{"name": "gold_loan_specialist", "args": {"query": user_query}, "id": tool_call_id}]
    )
    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name="gold_loan_specialist")

    updated_extracted = dict(state.get("extracted_data", {}))
    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
    updated_extracted["gold_loan_specialist"] = response_content

    return {
        "messages": [ai_msg, tool_msg],
        "extracted_data": updated_extracted
    }


# ---------------------------------------------------------------------------
# Structured Extraction Schemas
# ---------------------------------------------------------------------------
class FinancialCalculationIntent(BaseModel):
    category: str = Field(description="Must be one of: 'EMI', 'FD', 'Savings_Tier', 'Cashback_Cap'")
    target_principal: Optional[float] = Field(None, description="The loan or deposit amount requested by user.")
    requested_tenures_months: List[int] = Field(default_factory=list, description="Explicit tenures requested by the user.")
    loan_type: Optional[str] = Field(None, description="The requested loan type, such as Personal Loan, Home Loan, Gold Loan.")
    max_acceptable_emi: Optional[float] = Field(None, description="The maximum monthly installment boundary specified by the user.")
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
        intent = FinancialCalculationIntent(
            category="EMI",
            target_principal=extracted_data.get("loan_amount"),
            requested_tenures_months=extracted_data.get("requested_tenure_months", []),
            loan_type=extracted_data.get("loan_type")
        )

    # 2. Extract database offers
    ctx = get_offer_context(customer_id)
    available_offers = ctx.get("offers", [])
    
    # 3. Dynamic Filtering and Semantic Parsing Engine
    verified_calculation_results = []
    target_principal = intent.target_principal or extracted_data.get("loan_amount") or 0.0
    max_acceptable_emi = intent.max_acceptable_emi if intent.max_acceptable_emi is not None else 0.0

    if target_principal > 0:
        # Instantiate a structured interpreter to parse unstructured text blocks on-the-fly
        offer_interpreter = llm.with_structured_output(SemanticallyParsedOffer)

        for offer in available_offers:
            offer_id = offer.get("offer_id", "unknown")
            details = offer.get("offer_details", offer)
            raw_content = details.get("content", str(details))

            # Semantically audit the unstructured text against the user's target inquiry properties
            user_loan_type = intent.loan_type or "Personal Loan"
            parsing_prompt = f"""Analyze this bank offer block and extract its terms structural limits:
            Offer Content: "{raw_content}"
            User Parameter Target Category: {intent.category} (e.g., if category is EMI, look for Personal Loans or similar amortized variants. Skip Home Loans if user specifically wanted a small dynamic personal metric, skip Credit cards, skip FDs).
            User Requested Loan Type: {user_loan_type}. Only match offers that align with this requested loan type or with generic lending products compatible with it."""
            
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

            # Enforce offer tenure limits: do not allow tenures longer than the offer permits.
            offer_max_tenure_months = int(parsed_metrics.extracted_tenure_years * 12) if parsed_metrics.extracted_tenure_years else None
            active_tenures = list(intent.requested_tenures_months)
            if active_tenures:
                if offer_max_tenure_months is not None:
                    filtered_tenures = [t for t in active_tenures if t <= offer_max_tenure_months]
                    if not filtered_tenures:
                        print(
                            f"   [Tenure Filter]: Skipping '{offer_id}' -> Requested tenure(s) {active_tenures} exceed offer max tenure of {offer_max_tenure_months} months."
                        )
                        continue
                    active_tenures = filtered_tenures
            else:
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

    if not verified_calculation_results:
        response_content = (
            f"Your requested amount of ₹{target_principal:,.0f} cannot be processed with the available offers. "
            "No current offer supports that exact amount under the available loan limits. "
            "Please reduce the requested amount or wait for a higher limit offer to become available."
        )
    else:
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