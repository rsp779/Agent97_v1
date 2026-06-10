import json
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from agent_state import AgentState
from settings import llm

class ExecutionRoadmap(BaseModel):
    """Schema to force a strict, linear tool dependency pipeline."""
    reasoning: str = Field(description="Step-by-step logic detailing why this specific sequence path is required.")
    ordered_path: List[str] = Field(description="The exact order chain of sub-agent IDs to execute, e.g., ['offers_specialist', 'loan_product_calculator']")

class LoanParameters(BaseModel):
    """Schema to safely extract variable entities from conversational text."""
    loan_amount: Optional[float] = Field(None, description="The target principal loan amount requested by the user.")
    max_acceptable_emi: Optional[float] = Field(None, description="The maximum monthly installment boundary specified by the user.")
    requested_tenure_months: List[int] = Field(default_factory=list, description="The requested loan tenure in months extracted from the user's query.")
    loan_type: Optional[str] = Field(None, description="The requested loan type, such as Personal Loan, Home Loan, Gold Loan, etc.")


def _build_context_snapshot(state: AgentState) -> str:
    extracted = state.get("extracted_data", {})
    short_term = extracted.get("short_term_memory", [])
    recent_memory = short_term[-3:] if isinstance(short_term, list) else []
    snapshot = {
        "current_step_index": extracted.get("current_step_index"),
        "loan_type": extracted.get("loan_type"),
        "loan_amount": extracted.get("loan_amount"),
        "requested_tenure_months": extracted.get("requested_tenure_months"),
        "max_acceptable_emi": extracted.get("max_acceptable_emi"),
        "gold_loan_context": extracted.get("gold_loan_context"),
        "home_loan_requested_amount": extracted.get("home_loan_requested_amount"),
        "home_loan_requested_tenure_months": extracted.get("home_loan_requested_tenure_months"),
        "recent_short_term_memory": recent_memory,
    }
    return json.dumps(snapshot, default=str)


def _looks_like_follow_up_query(query: str) -> bool:
    lowered = query.lower().strip()
    if not lowered:
        return False
    follow_up_markers = [
        "emi",
        "tenure",
        "months",
        "month",
        "repayment",
        "amount",
        "rate",
        "interest",
        "what will be",
        "how much",
    ]
    return any(marker in lowered for marker in follow_up_markers) or lowered.replace(" ", "").isdigit()


def _route_from_context(state: AgentState, last_query: str) -> Optional[List[str]]:
    extracted = state.get("extracted_data", {})
    lowered = last_query.lower().strip()
    last_active = extracted.get("last_active_specialist")
    explicit_home = "home loan" in lowered
    explicit_gold = "gold loan" in lowered or "gold" in lowered
    explicit_credit = any(token in lowered for token in ["credit card", "card ", " card", "cc "])
    explicit_personal = "personal loan" in lowered

    if _looks_like_follow_up_query(last_query):
        if explicit_home:
            return ["home_loan_specialist"]
        if explicit_gold:
            return ["gold_loan_specialist"]
        if explicit_credit:
            return ["credit_card_specialist"]
        if explicit_personal:
            return ["loan_product_calculator", "offers_specialist"]

        if last_active == "home_loan_specialist":
            return ["home_loan_specialist"]
        if last_active == "gold_loan_specialist":
            return ["gold_loan_specialist"]
        if last_active == "credit_card_specialist":
            return ["credit_card_specialist"]
        if last_active in {"loan_product_calculator", "offers_specialist"}:
            return ["loan_product_calculator", "offers_specialist"]

    return None

def supervisor_node(state: AgentState) -> Dict[str, Any]:
    """Analyzes the user's query intent, builds a deterministic execution map,
    and extracts entity parameters directly into the graph state.
    """
    user_messages = [m for m in state.get("messages", []) if isinstance(m, HumanMessage)]
    if not user_messages:
        return {"extracted_data": {**state.get("extracted_data", {}), "ordered_path": [], "current_step_index": 0}}
    
    last_query = user_messages[-1].content
    context_snapshot = _build_context_snapshot(state)
    print(f"\n[Supervisor]: Orchestrating request: '{last_query}'")

    system_routing_guide = """You are the Global Dependency Architect Matrix for IDFC FIRST Bank.
    Your job is to analyze incoming user queries and output a strict, linear pipeline execution path of specialized sub-agents.

    YOUR FOUR SUPERVISOR JOBS:
    1. If a query is vague, ambiguous, or missing key details, return an empty ordered_path and prompt for more information.
    2. If a query is beyond the customer banking relationship domain, return an empty ordered_path and allow the system to reply that it is out of scope.
    3. Route valid banking queries to the exact one or more appropriate sub-agents.
    4. Do not perform specialist analysis yourself; only orchestrate the correct tool chain.

    AVAILABLE SPECIALIST SUB-AGENTS:
    - offers_specialist (Offers Specialist): Fetches campaign interest rates, credit caps, and profile-specific pre-approved ceilings.
    - transaction_specialist (Transaction Analyst): Crunches, filters, ranks, and aggregates multi-month financial transaction histories.
    - loan_product_calculator (Loan Calculator): Executes compound reducing balance amortization mathematics using real verified loan rates.
    - home_loan_specialist (Home Loan Specialist): Handles Home Loan EMI, tenure, amount discussions, and total repayment calculations using Home Loan offer data.
    - gold_loan_specialist (Gold Loan Specialist): Handles gold-collateral loan eligibility, current price valuation, and disbursement range calculation.
    - credit_card_specialist (Credit Card Specialist): Calculates retail merchant checkout instant discounts, cashback boundaries, and point rewards.
    - banking_specialist (Banking Core Specialist): Extracts raw ledger tracking metadata, balances, and owned account portfolio types.

    CRITICAL PIPELINE DEPENDENCY MATRIX RULES:
    1. LOAN DEPENDENCY RULE: If a calculation (loan_product_calculator) requires an interest rate or tier ceiling from a profile offer, you MUST execute offers_specialist before loan_product_calculator so the rate is discovered first.
    2. TRANSACTION BALANCE RULE: If an account status verification depends on past trends, you MUST execute transaction_specialist before banking_specialist.
    3. EFFICIENCY CONSTRAINT (STRICT RULE): Never include transaction analysis (transaction_specialist) or banking core operations (banking_specialist) for hypothetical loan simulations or standard interest queries unless the user explicitly requests transaction auditing, tracking histories, or balance status statements. If they only ask for loan terms or interest calculations, use ONLY ['offers_specialist', 'loan_product_calculator'].
    4. CONTEXT CORRUPTION PREVENTION: Never include an unrelated agent. If a user asks for a Personal Loan, do NOT include credit_card_specialist under any circumstance unless the query itself is explicitly about credit card offers, credit card bill EMI conversion, or credit-card related rewards/perks.

    Your output must be the exact ordered_path list only, selected from available specialist IDs.
    
    CLARIFICATION RULE: If the user's query is vague, ambiguous, or missing key details needed to choose the correct specialist, do not guess. Return an empty ordered_path list and ask a concise follow-up clarification question.
    
    OUT-OF-DOMAIN RULE: If the user's query is outside any customer banking relationship domain, return an empty ordered_path list and do not route to any specialist.
    
    CRITICAL ROUTING RULE - CREDIT CARD CENTRALIZATION:
    ALL credit card-related queries (offers, rewards, EMI conversions, balance transfers, loans, merchant EMI, cashback, discounts, etc.) MUST route ONLY to ['credit_card_specialist'].
    The credit_card_specialist is the unified handler for all credit card operations and will manage all variants as they are added to the catalog.
    Do NOT split credit card queries across multiple agents.
    
    ROUTING DECISION MATRIX:
    1. If query mentions credit card, card, cardholder, card bill, card transaction, EMI on card, balance transfer, loan on card, or any card-related financial product -> ['credit_card_specialist']
    2. If query is ONLY about past banking history/transactions and does NOT mention credit card benefits/offers -> ['transaction_specialist']
    3. If query is about a Home Loan -> ['home_loan_specialist']
    4. If query is about a Personal Loan (not card-related) -> ['loan_product_calculator', 'offers_specialist']
    5. If query is about general account info (not transactions, not offers) -> ['banking_specialist']
    
    Examples:
    - "What is the transaction on my Credit Card on Amazon?" -> ['credit_card_specialist'] (card-related)
    - "I want to convert my 25K credit card bill to EMI for 6 months" -> ['credit_card_specialist'] (card EMI)
    - "What balance offers do I have on my credit card?" -> ['credit_card_specialist'] (card offer)
    - "Can I get a loan on my credit card?" -> ['credit_card_specialist'] (card product)
    - "What merchant EMI options are available on my card?" -> ['credit_card_specialist'] (card offer)
    - "How much did I spend last month?" -> ['transaction_specialist'] (pure history, no card offer context)
    - "I need a personal loan for 5 lakhs" -> ['loan_product_calculator', 'offers_specialist'] (non-card loan)
    - "I want a home loan of 50 lakhs for 20 years" -> ['home_loan_specialist'] (home loan)
    
    Do not depend on external code heuristics; use only your understanding of the user query and the specialist definitions above.
    """

    # 1. Determine optimal pipeline route
    try:
        structured_llm = llm.with_structured_output(ExecutionRoadmap)
        roadmap = structured_llm.invoke([
            SystemMessage(content=system_routing_guide),
            HumanMessage(content=(
                f"Conversation context snapshot: {context_snapshot}\n"
                f"Analyze intent and compile roadmap path for query: '{last_query}'"
            ))
        ])
        ordered_path = roadmap.ordered_path
    except Exception:
        ordered_path = ["offers_specialist", "loan_product_calculator"]

    contextual_route = _route_from_context(state, last_query)
    if contextual_route is not None:
        ordered_path = contextual_route

    # 2. Extract numeric entities matching input specifications
    extraction_prompt = """You are an accurate data extraction utility. Your sole job is to parse numeric values 
    and loan type information from a retail banking customer query. Convert text values like '4 lakh' or '4L' to raw floats (e.g., 400000.0).
    Extract requested tenure values and normalize them to months (e.g., '5 years' -> 60 months).
    Extract the requested loan type if present (e.g., Personal Loan, Home Loan, Gold Loan).
    If a value is entirely missing from the query, leave its field as null or an empty list.
    Do not invent or assume data, and do not reuse any values from previous turns unless the current query explicitly repeats them."""
        
    try:
        structured_extractor = llm.with_structured_output(LoanParameters)
        extracted = structured_extractor.invoke([
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=(
                f"Conversation context snapshot: {context_snapshot}\n"
                f"Latest user message: '{last_query}'"
            ))
        ])
        loan_amount = extracted.loan_amount
        max_acceptable_emi = extracted.max_acceptable_emi
        requested_tenure_months = extracted.requested_tenure_months
        loan_type = extracted.loan_type
    except Exception:
        loan_amount, max_acceptable_emi, requested_tenure_months, loan_type = None, None, [], None

    if contextual_route == ["gold_loan_specialist"] and loan_type is None:
        loan_type = "Gold Loan"
    if contextual_route == ["home_loan_specialist"] and loan_type is None:
        loan_type = "Home Loan"
    if contextual_route == ["credit_card_specialist"] and loan_type is None:
        loan_type = "Credit Card"

    print(f" -> [Generated Path]: {' -> '.join(ordered_path)}")
    print(f" -> [Extracted Entities]: Amount: {loan_amount}, Max EMI: {max_acceptable_emi}, Tenure months: {requested_tenure_months}, Loan type: {loan_type}")

    # Maintain existing dict references
    updated_extracted = dict(state.get("extracted_data", {}))
    updated_extracted.update({
        "ordered_path": ordered_path,
        "current_step_index": 0,
        "loan_amount": loan_amount,
        "max_acceptable_emi": max_acceptable_emi,
        "requested_tenure_months": requested_tenure_months,
        "loan_type": loan_type,
    })

    return {"extracted_data": updated_extracted}
