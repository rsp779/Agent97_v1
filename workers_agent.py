import json
import math
import re
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


def _fetch_json_from_url(url: str) -> Optional[Any]:
    headers = {"User-Agent": "Mozilla/5.0"}
    context = ssl.create_default_context()
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10, context=context) as response:
            payload = response.read().decode("utf-8")
        return json.loads(payload)
    except (HTTPError, URLError, json.JSONDecodeError, ValueError) as exc:
        print(f"   [GoldPrice] Failed to fetch from {url}: {exc}")
        return None


def _fetch_text_from_url(url: str) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    context = ssl.create_default_context()
    try:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=10, context=context) as response:
            return response.read().decode("utf-8", errors="ignore")
    except (HTTPError, URLError, ValueError) as exc:
        print(f"   [GoldPrice] Failed to fetch text from {url}: {exc}")
        return None


def _extract_oz_price_from_text(text: str) -> Optional[float]:
    patterns = [
        r"\$<!-- -->([0-9][0-9,]*(?:\.[0-9]+)?)<span[^>]*>Per\s*Oz\.",
        r'"price"\s*:\s*([0-9][0-9,]*(?:\.[0-9]+)?)',
        r"price\":([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"\$\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*Per\s*Oz",
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*Per\s*Oz",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
    return None


def _fetch_usd_to_inr_rate() -> float:
    endpoints = [
        "https://open.er-api.com/v6/latest/USD",
        "https://api.exchangerate.host/latest?base=USD&symbols=INR",
    ]
    for url in endpoints:
        data = _fetch_json_from_url(url)
        if data is None:
            continue
        if isinstance(data, dict):
            if "rates" in data and isinstance(data["rates"], dict) and data["rates"].get("INR"):
                return float(data["rates"]["INR"])
            if "result" in data and data.get("result") == "success":
                rates = data.get("rates") or {}
                if rates.get("INR"):
                    return float(rates["INR"])
            if "INR" in data and isinstance(data["INR"], (int, float)):
                return float(data["INR"])
    return None


def fetch_current_gold_price(display_currency: Optional[str] = None) -> Dict[str, Any]:
    endpoints = [
        "https://gold-api.com/",
        "https://data-asg.goldprice.org/dbXRates/USD",
        "https://api.metals.live/v1/spot/gold",
    ]

    usd_price_per_ounce: Optional[float] = None
    source_url: Optional[str] = None

    for url in endpoints:
        if url == "https://gold-api.com/":
            text = _fetch_text_from_url(url)
            if text is not None:
                usd_price_per_ounce = _extract_oz_price_from_text(text)
                if usd_price_per_ounce is not None:
                    source_url = url
                    break
            continue

        data = _fetch_json_from_url(url)
        if data is None:
            continue

        if isinstance(data, dict):
            items = data.get("items") or data.get("data")
            if isinstance(items, list) and items:
                item = items[0]
                for key in ["xauPrice", "price", "last"]:
                    if isinstance(item, dict) and key in item:
                        usd_price_per_ounce = float(item[key])
                        source_url = url
                        break
            if usd_price_per_ounce is None and "price" in data:
                usd_price_per_ounce = float(data["price"])
                source_url = url
        elif isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict):
                for key in ["xauPrice", "price", "last"]:
                    if key in first:
                        usd_price_per_ounce = float(first[key])
                        source_url = url
                        break

        if usd_price_per_ounce is not None:
            break

    if usd_price_per_ounce is None:
        return {
            "price_per_ounce": None,
            "currency": (display_currency or "INR").upper(),
            "source": None,
            "usd_to_inr_rate": None,
            "is_fallback": False,
            "needs_customer_price": True,
        }

    is_fallback = False
    display_currency = (display_currency or "INR").upper()
    if display_currency == "USD":
        return {
            "price_per_ounce": usd_price_per_ounce,
            "currency": "USD",
            "source": source_url,
            "usd_to_inr_rate": None,
            "is_fallback": is_fallback,
        }

    usd_to_inr_rate = _fetch_usd_to_inr_rate()
    if usd_to_inr_rate is None:
        return {
            "price_per_ounce": None,
            "currency": "INR",
            "source": source_url,
            "usd_to_inr_rate": None,
            "is_fallback": False,
            "needs_customer_price": True,
        }
    return {
        "price_per_ounce": round(usd_price_per_ounce * usd_to_inr_rate, 2),
        "currency": "INR",
        "source": source_url,
        "usd_to_inr_rate": usd_to_inr_rate,
        "is_fallback": is_fallback,
    }


def convert_gold_quantity_to_grams(grams: Optional[float], tolas: Optional[float], ounces: Optional[float]) -> float:
    if grams is not None and grams > 0:
        return grams
    if tolas is not None and tolas > 0:
        return tolas * 11.6638038
    if ounces is not None and ounces > 0:
        return ounces * 31.1034768
    return 0.0


def _format_rupee_amount(amount: float) -> str:
    return f"₹{amount:,.2f}"


def _parse_home_loan_offer_terms(content: str) -> Dict[str, Any]:
    lowered = content.lower()

    rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%.*?interest", lowered)
    tenure_match = re.search(r"for\s+(\d+)\s+years", lowered)
    limit_match = re.search(r"upto\s+(\d+(?:\.\d+)?)\s*(crores?|crore|lakhs?|lacs?|lac)", lowered)

    max_limit = None
    if limit_match:
        value = float(limit_match.group(1))
        unit = limit_match.group(2)
        if unit.startswith("crore"):
            max_limit = value * 10_000_000
        else:
            max_limit = value * 100_000

    return {
        "interest_rate": float(rate_match.group(1)) if rate_match else None,
        "tenure_years": int(tenure_match.group(1)) if tenure_match else None,
        "max_limit": max_limit,
    }


def _parse_loan_offer_terms(content: str) -> Dict[str, Any]:
    lowered = content.lower()

    rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%.*?interest", lowered)
    tenure_match = re.search(r"for\s+(\d+)\s+(years?|months?)", lowered)
    limit_match = re.search(r"upto\s+(\d+(?:\.\d+)?)\s*(crores?|crore|lakhs?|lacs?|lac)", lowered)

    max_limit = None
    if limit_match:
        value = float(limit_match.group(1))
        unit = limit_match.group(2)
        if unit.startswith("crore"):
            max_limit = value * 10_000_000
        else:
            max_limit = value * 100_000

    tenure_months = None
    if tenure_match:
        value = int(tenure_match.group(1))
        unit = tenure_match.group(2)
        tenure_months = value * 12 if unit.startswith("year") else value

    return {
        "interest_rate": float(rate_match.group(1)) if rate_match else None,
        "tenure_months": tenure_months,
        "max_limit": max_limit,
    }


def _select_best_home_loan_offer(
    customer_id: str,
    requested_amount: Optional[float],
    requested_tenure_months: List[int],
) -> Dict[str, Any]:
    catalog = DATASTORE.get_offer_catalog()
    eligible_offer_ids = {
        item.get("offer_id")
        for item in DATASTORE.get_customer_offer_scores(customer_id)
        if item.get("offer_id")
    }
    candidates = []

    for offer_id, offer in catalog.items():
        if offer_id not in eligible_offer_ids:
            continue
        content = (offer or {}).get("content", "")
        if "home loan" not in content.lower():
            continue

        terms = _parse_home_loan_offer_terms(content)
        max_limit = terms["max_limit"]
        tenure_years = terms["tenure_years"]
        interest_rate = terms["interest_rate"]

        if requested_amount is not None and max_limit is not None and requested_amount > max_limit:
            continue

        if requested_tenure_months and tenure_years is not None:
            if any(tenure > tenure_years * 12 for tenure in requested_tenure_months):
                continue

        candidates.append(
            {
                "offer_id": offer_id,
                "content": content,
                "interest_rate": interest_rate,
                "tenure_years": tenure_years,
                "max_limit": max_limit,
            }
        )

    if not candidates:
        return {}

    candidates.sort(
        key=lambda item: (
            item["interest_rate"] if item["interest_rate"] is not None else float("inf"),
            item["max_limit"] if item["max_limit"] is not None else float("inf"),
            item["tenure_years"] if item["tenure_years"] is not None else float("inf"),
        )
    )
    return candidates[0]


def _find_customer_gold_loan_offer(customer_id: str) -> Dict[str, Any]:
    catalog = DATASTORE.get_offer_catalog()
    for item in DATASTORE.get_customer_offer_scores(customer_id):
        offer_id = item.get("offer_id")
        content = catalog.get(offer_id, {}).get("content", "")
        if "gold loan" not in content.lower():
            continue
        terms = _parse_loan_offer_terms(content)
        return {
            "offer_id": offer_id,
            "content": content,
            "interest_rate": terms["interest_rate"],
            "tenure_months": terms["tenure_months"],
            "max_limit": terms["max_limit"],
        }
    return {}


def _detect_currency_from_query(query: str, fallback_currency: Optional[str] = None) -> str:
    lowered = query.lower()
    if any(token in query for token in ["₹", "rs", "inr"]):
        return "INR"
    if any(token in lowered for token in ["rupee", "rupees", "lakh", "lakhs", "crore", "crores"]):
        return "INR"
    if any(token in query for token in ["$", "USD", "usd"]) or "dollar" in lowered:
        return "USD"
    return (fallback_currency or "INR").upper()


def _format_currency(amount: float, currency: str) -> str:
    currency = currency.upper()
    if currency == "USD":
        return f"${amount:,.2f}"
    return f"₹{amount:,.2f}"


def _extract_gold_loan_terms_from_query(query: str) -> Dict[str, Any]:
    class GoldLoanRequest(BaseModel):
        gold_quantity_grams: Optional[float] = Field(None, description="Gold quantity pledged in grams.")
        gold_quantity_tolas: Optional[float] = Field(None, description="Gold quantity pledged in tolas.")
        gold_quantity_ounces: Optional[float] = Field(None, description="Gold quantity pledged in ounces.")
        requested_loan_amount: Optional[float] = Field(None, description="The requested gold loan amount.")
        requested_tenure_months: List[int] = Field(default_factory=list, description="Requested loan tenure in months.")
        max_acceptable_emi: Optional[float] = Field(None, description="The maximum EMI the customer can pay.")
        requested_currency: Optional[str] = Field(None, description="Requested currency code such as INR or USD.")

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
- requested_currency
"""
    try:
        structured_extractor = llm.with_structured_output(GoldLoanRequest)
        extracted = structured_extractor.invoke([
            SystemMessage(content=extraction_prompt),
            HumanMessage(content=query)
        ])
        return extracted.model_dump()
    except Exception as exc:
        print(f"   [GoldLoan] Extraction failed: {exc}")
        return GoldLoanRequest().model_dump()


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
    updated_extracted["last_active_specialist"] = agent_name

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
    customer_id = state["customer_id"]
    extracted = state.get("extracted_data", {})
    user_query = state["messages"][-1].content if state.get("messages") else ""
    requested_amount = extracted.get("loan_amount")
    requested_tenures = extracted.get("requested_tenure_months", []) or []
    requested_emi = extracted.get("max_acceptable_emi")

    print(f"   [*] Invoking Sub-Agent [G] (home_loan_specialist)...")

    if requested_amount is None and not requested_tenures and requested_emi is None:
        response_content = (
            "Please share the home loan amount, tenure, or EMI target so I can check your eligible home loan offer."
        )
    else:
        selected_offer = _select_best_home_loan_offer(customer_id, requested_amount, requested_tenures)

        if not selected_offer:
            response_content = (
                "No eligible home loan offer in your customer profile matches the requested amount and tenure."
            )
        else:
            offer_content = selected_offer["content"]
            interest_rate = selected_offer["interest_rate"]

            if requested_amount is None:
                response_content = (
                    f"Your eligible home loan offer is: {offer_content}. Please share the loan amount to calculate EMI."
                )
            elif not requested_tenures:
                response_content = (
                    f"Your eligible home loan offer is: {offer_content}. Please share the tenure to calculate EMI."
                )
            elif interest_rate is None:
                response_content = (
                    f"Your eligible home loan offer is: {offer_content}. The catalog does not include an interest rate, so EMI cannot be calculated."
                )
            else:
                tenure_months = requested_tenures[0]
                math_metrics = run_reducing_balance_emi(requested_amount, interest_rate, tenure_months)
                emi = math_metrics["primary_metric"]
                total_interest = math_metrics["total_interest"]
                total_repayment = math_metrics["total_repayment"]

                response_content = (
                    f"Your eligible home loan offer is: {offer_content}. "
                    f"For {_format_rupee_amount(requested_amount)} over {tenure_months} months, the estimated EMI is "
                    f"{_format_rupee_amount(emi)}, total interest is {_format_rupee_amount(total_interest)}, "
                    f"and total repayment is {_format_rupee_amount(total_repayment)}."
                )

    tool_call_id = f"call_G_{customer_id}"
    ai_msg = AIMessage(
        content="Selecting the best matching home loan offer from the catalog...",
        tool_calls=[{"name": "home_loan_specialist", "args": {"query": user_query}, "id": tool_call_id}]
    )
    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name="home_loan_specialist")

    updated_extracted = dict(extracted)
    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
    updated_extracted["home_loan_specialist"] = response_content
    updated_extracted["last_active_specialist"] = "home_loan_specialist"
    if requested_amount is not None:
        updated_extracted["home_loan_requested_amount"] = requested_amount
    if requested_tenures:
        updated_extracted["home_loan_requested_tenure_months"] = requested_tenures

    return {
        "messages": [ai_msg, tool_msg],
        "extracted_data": updated_extracted
    }


def gold_loan_specialist_node(state: AgentState) -> Dict[str, Any]:
    customer_id = state["customer_id"]
    extracted = state.get("extracted_data", {})
    user_query = state["messages"][-1].content if state.get("messages") else ""
    print(f"   [*] Invoking Sub-Agent [H] (gold_loan_specialist)...")
    updated_context = None
    selected_offer = _find_customer_gold_loan_offer(customer_id)

    if not selected_offer:
        response_content = (
            "I cannot process a gold loan for this profile because no gold-loan offer is present in the customer's eligible offers."
        )
    else:
        gold_request = _extract_gold_loan_terms_from_query(user_query)
        previous_context = extracted.get("gold_loan_context", {}) if isinstance(extracted, dict) else {}

        quantity_in_grams = convert_gold_quantity_to_grams(
            gold_request.get("gold_quantity_grams") or previous_context.get("gold_quantity_grams"),
            gold_request.get("gold_quantity_tolas") or previous_context.get("gold_quantity_tolas"),
            gold_request.get("gold_quantity_ounces") or previous_context.get("gold_quantity_ounces"),
        )

        requested_amount = (
            gold_request.get("requested_loan_amount")
            or previous_context.get("requested_loan_amount")
        )
        requested_currency = _detect_currency_from_query(
            user_query,
            gold_request.get("requested_currency") or previous_context.get("currency") or "INR",
        )
        price_data = fetch_current_gold_price(requested_currency)
        price_per_ounce = price_data["price_per_ounce"]
        currency = price_data["currency"]
        price_per_gram = (price_per_ounce / 31.1034768) if price_per_ounce is not None else None
        is_fallback_price = price_data.get("is_fallback", False)

        response_lines = []
        offer_content = selected_offer.get("content", "Gold loan offer")
        offer_rate = selected_offer.get("interest_rate")
        offer_tenure_months = selected_offer.get("tenure_months")
        response_lines.append(f"Eligible gold-loan offer: {offer_content}.")

        if quantity_in_grams <= 0 and requested_amount is None and not previous_context:
            response_content = (
                "Please share either the gold quantity you want to pledge or the loan amount you need, and I will calculate the eligible range."
            )
        elif price_data.get("needs_customer_price"):
            response_content = (
                f"I could not fetch a live gold price for {currency}. Please share the current gold price in {currency} so I can calculate the eligible loan range."
            )
        else:
            if quantity_in_grams > 0:
                total_gold_value = round(quantity_in_grams * price_per_gram, 2)
                min_disbursement = round(total_gold_value * 0.8, 2)
                max_disbursement = round(total_gold_value * 1.2, 2)
                response_lines.append(
                    f"For {quantity_in_grams:.2f} grams of gold, the eligible loan range is "
                    f"{_format_currency(min_disbursement, currency)} to {_format_currency(max_disbursement, currency)}."
                )
            else:
                total_gold_value = None
                min_disbursement = None
                max_disbursement = None

            if requested_amount is not None and min_disbursement is not None and max_disbursement is not None:
                if requested_amount < min_disbursement or requested_amount > max_disbursement:
                    required_gold_lower = (requested_amount / 1.2) / price_per_gram
                    required_gold_upper = (requested_amount / 0.8) / price_per_gram
                    response_content = (
                        f"Your requested loan of {_format_currency(requested_amount, currency)} is outside the eligible range for "
                        f"{quantity_in_grams:.2f} grams of gold. The current eligible range is "
                        f"{_format_currency(min_disbursement, currency)} to {_format_currency(max_disbursement, currency)}. "
                        f"To support {_format_currency(requested_amount, currency)}, you would need about "
                        f"{required_gold_lower:.2f} to {required_gold_upper:.2f} grams of gold."
                    )
                    updated_context = {
                        "gold_quantity_grams": quantity_in_grams if quantity_in_grams > 0 else previous_context.get("gold_quantity_grams"),
                        "gold_quantity_tolas": gold_request.get("gold_quantity_tolas") or previous_context.get("gold_quantity_tolas"),
                        "gold_quantity_ounces": gold_request.get("gold_quantity_ounces") or previous_context.get("gold_quantity_ounces"),
                        "requested_loan_amount": requested_amount,
                        "requested_tenure_months": gold_request.get("requested_tenure_months") or previous_context.get("requested_tenure_months") or [],
                        "max_acceptable_emi": gold_request.get("max_acceptable_emi") or previous_context.get("max_acceptable_emi"),
                        "currency": currency,
                        "price_per_ounce": price_per_ounce,
                        "price_per_gram": round(price_per_gram, 2) if price_per_gram is not None else None,
                        "total_gold_value": total_gold_value,
                        "min_disbursement": min_disbursement,
                        "max_disbursement": max_disbursement,
                        "offer_id": selected_offer.get("offer_id"),
                        "offer_interest_rate": offer_rate,
                        "offer_tenure_months": offer_tenure_months,
                    }
                    tool_call_id = f"call_H_{customer_id}"
                    ai_msg = AIMessage(
                        content="Checking gold-loan eligibility and current pricing...",
                        tool_calls=[{"name": "gold_loan_specialist", "args": {"query": user_query}, "id": tool_call_id}]
                    )
                    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name="gold_loan_specialist")

                    updated_extracted = dict(state.get("extracted_data", {}))
                    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
                    updated_extracted["gold_loan_specialist"] = response_content
                    updated_extracted["last_active_specialist"] = "gold_loan_specialist"
                    updated_extracted["gold_loan_context"] = updated_context

                    return {
                        "messages": [ai_msg, tool_msg],
                        "extracted_data": updated_extracted
                    }

            if requested_amount is not None:
                lower_gold_value = requested_amount / 1.2
                upper_gold_value = requested_amount / 0.8
                lower_grams = lower_gold_value / price_per_gram
                upper_grams = upper_gold_value / price_per_gram
                response_lines.append(
                    f"To support a loan of {_format_currency(requested_amount, currency)}, you need about "
                    f"{lower_grams:.2f} to {upper_grams:.2f} grams of gold."
                )

            tenure_months = gold_request.get("requested_tenure_months") or previous_context.get("requested_tenure_months") or []
            max_acceptable_emi = gold_request.get("max_acceptable_emi") or previous_context.get("max_acceptable_emi")

            if requested_amount is not None:
                principal = requested_amount
            elif total_gold_value is not None:
                principal = max_disbursement
            else:
                principal = None

            if principal is not None:
                if tenure_months:
                    selected_tenure = tenure_months[0]
                    if offer_rate is None:
                        response_lines.append(
                            "The eligible gold-loan offer does not include an interest rate in the catalog, so EMI cannot be calculated."
                        )
                    else:
                        metrics = run_reducing_balance_emi(principal, offer_rate, selected_tenure)
                        response_lines.append(
                            f"For {selected_tenure} months, the estimated EMI is {_format_currency(metrics['primary_metric'], currency)}."
                        )
                        response_lines.append(
                            f"Total repayment is {_format_currency(metrics['total_repayment'], currency)}."
                        )
                        if max_acceptable_emi is not None and metrics["primary_metric"] > max_acceptable_emi:
                            response_lines.append(
                                f"This EMI is above your budget of {_format_currency(max_acceptable_emi, currency)}."
                            )
                else:
                    response_lines.append("Please share the tenure in months so I can calculate the EMI.")

            response_content = " ".join(response_lines)

            updated_context = {
                "gold_quantity_grams": quantity_in_grams if quantity_in_grams > 0 else previous_context.get("gold_quantity_grams"),
                "gold_quantity_tolas": gold_request.get("gold_quantity_tolas") or previous_context.get("gold_quantity_tolas"),
                "gold_quantity_ounces": gold_request.get("gold_quantity_ounces") or previous_context.get("gold_quantity_ounces"),
                "requested_loan_amount": requested_amount,
                "requested_tenure_months": tenure_months,
                "max_acceptable_emi": max_acceptable_emi,
                "currency": currency,
                "price_per_ounce": price_per_ounce,
                "price_per_gram": round(price_per_gram, 2) if price_per_gram is not None else None,
                "total_gold_value": total_gold_value,
                "min_disbursement": min_disbursement,
                "max_disbursement": max_disbursement,
                "offer_id": selected_offer.get("offer_id"),
                "offer_interest_rate": offer_rate,
                "offer_tenure_months": offer_tenure_months,
            }

    tool_call_id = f"call_H_{customer_id}"
    ai_msg = AIMessage(
        content="Checking gold-loan eligibility and current pricing...",
        tool_calls=[{"name": "gold_loan_specialist", "args": {"query": user_query}, "id": tool_call_id}]
    )
    tool_msg = ToolMessage(content=str(response_content), tool_call_id=tool_call_id, name="gold_loan_specialist")

    updated_extracted = dict(state.get("extracted_data", {}))
    updated_extracted["current_step_index"] = updated_extracted.get("current_step_index", 0) + 1
    updated_extracted["gold_loan_specialist"] = response_content
    updated_extracted["last_active_specialist"] = "gold_loan_specialist"
    if updated_context is not None:
        updated_extracted["gold_loan_context"] = updated_context

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
