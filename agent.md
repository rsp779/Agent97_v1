# Financial Agent System

## Overview
This repository implements a banking agent orchestrator for IDFC FIRST Bank. It uses a state graph to route customer queries through specialized agents and synthesizes responses using a language model.

## Agent Roles

### Supervisor Agent
- Determines the correct execution path based on customer query intent.
- Extracts numeric and contextual entities from queries.
- Enforces routing rules and ambiguity handling.
- Routes credit card queries to `credit_card_specialist` and personal loan queries to `loan_product_calculator` / `offers_specialist`.

### Credit Card Specialist Agent
- Unified handler for all credit card-related queries.
- Handles retail offers, cashback, reward points, bill-to-EMI conversions, balance transfers, merchant EMI, and future card loan products.
- Uses only offer catalog data and does not invent benefits or terms.
- Asks for clarification when user queries are vague or incomplete.

### Offers Specialist Agent
- Evaluates active offers and campaigns.
- Prioritizes semantic relevance and profile fit.
- Recommends offers with clear match justification and benefit summaries.

### Transaction Specialist Agent
- Analyzes transaction history, spending, merchant activity, and transaction patterns.
- Used for past transaction lookups and spending analytics when queries are not credit card offer-specific.

### Loan Product Calculator Agent
- Calculates EMI schedules, loan feasibility, and deposit projections.
- Uses verified loan terms and parsed offer limits.
- Does not assume tenure or invent interest rates.

### Banking Specialist Agent
- Handles general banking metadata, account balances, and owned product summaries.
- Used for account-level or profile-level queries outside transaction and offer analysis.

### Home Loan Specialist Agent
- Specialized handler for all home loan-related queries.
- Manages home loan EMI calculations, tenure discussions, and total repayment analysis.
- Uses only home loan offer data from the catalog.
- Does not apply generic personal loan rates or terms.

### Gold Loan Specialist Agent
- Dedicated handler for gold-collateral loan requests.
- Extracts customer's pledged gold quantity (in grams, tolas, or ounces).
- Fetches current gold prices from the internet and calculates eligible disbursement range: **[0.8× total_gold_value, 1.2× total_gold_value]**.
- Validates customer-requested loan amounts against the computed eligible range.
- Gracefully falls back if live gold price fetch fails, asking customer to provide current gold price.
- Supports requested tenure and EMI boundaries for future EMI calculation integration.

## Routing and Clarification
- Vague or ambiguous queries should trigger a clarification request rather than a guess.
- Credit card queries route to `credit_card_specialist` unless they are clearly pure transaction history requests.
- Home loan queries route directly to `home_loan_specialist`.
- Gold loan queries route directly to `gold_loan_specialist`.
- Personal loan and non-card/non-collateral loan queries route through `loan_product_calculator` / `offers_specialist` agents.

## Files
- `main.py` — entry point and interactive loop.
- `graph_builder.py` — constructs the state machine and routing logic.
- `supervisor_agent.py` — orchestrator and intent extraction.
- `workers_agent.py` — worker nodes for each specialist.
- `prompts.py` — prompt templates and guidance for agents.
- `agent_state.py` — state management wrapper.

## Notes
- Do not add or invent offer details beyond the provided catalog data.
- All user-facing responses should be concise and professional.
- Gold loan prices are fetched live from public APIs; fallback messages are provided if fetch fails.
- The system is designed to be extendable with new credit card product variants, home loan features, and collateral-based loan types.
- Product-specific agents (home loan, gold loan) enforce strict data isolation to prevent offer/rate leakage between loan types.