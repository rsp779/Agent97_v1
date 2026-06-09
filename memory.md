# Project Memory

## What This Repo Is

This repository is a LangGraph-based banking digital relationship manager for IDFC FIRST Bank. It routes customer queries through specialist agents, reads local customer and offer data, and synthesizes a terminal-friendly response.

## Core Runtime Flow

1. `main.py` prompts for a customer ID.
2. Customer data is loaded from the local JSON datastore.
3. `AgentState` is initialized with message history and extracted context.
4. Each user query is appended to the state.
5. `banking_financial_graph` runs the supervisor and specialist nodes.
6. The synthesis node generates the final response.
7. `main.py` does a final cleanup pass for short terminal output.

## Important Files

- `main.py`: CLI entry point and conversation loop.
- `graph_builder.py`: LangGraph state machine and routing logic.
- `supervisor_agent.py`: route planning and entity extraction.
- `workers_agent.py`: specialist node implementations and math helpers.
- `agent_state.py`: shared graph state and memory helpers.
- `data/mock_db.py`: JSON-backed datastore.
- `prompts.py`: system prompts and behavioral guardrails.
- `settings.py`: shared LLM configuration.
- `test_gold_loan.py`: gold-loan flow test harness.

## State Shape

`AgentState` currently carries:

- `messages`
- `is_in_scope`
- `customer_id`
- `extracted_data`

The helper functions in `agent_state.py` support:

- initializing state
- appending messages
- storing short-term memory
- merging extracted values

## Routing Rules

The supervisor builds an `ordered_path` for the current user query.

Common routes:

- `credit_card_specialist`
- `transaction_specialist`
- `loan_product_calculator -> offers_specialist`
- `home_loan_specialist`
- `gold_loan_specialist`
- `banking_specialist`

The router in `graph_builder.py` translates those route tokens into graph nodes.

## Data Sources

The datastore reads:

- `data/customer_profiles_db.json`
- `data/customer_offers_db.json`
- `data/variant_db.json`
- `data/transaction_db.json`

Those files provide:

- customer profiles
- offer scores
- offer catalog entries
- transaction history

## Product Logic

### Offers

Offer logic is driven by the offer catalog and the customer-specific score list. The prompts explicitly say not to invent rates, rewards, or fees.

### Loans

Loan calculations use verified offer text plus structured extraction. The system supports personal loans and home loans from the catalog, and it centralizes credit-card-related flows in the credit card specialist.

### Gold Loan

Gold loans are special-cased:

- gold quantity is extracted from the query
- live gold prices are fetched from public endpoints
- the system computes an eligible disbursement range
- if live price lookup fails, a fallback estimate is used

## Current Gaps

- `BANKING_SPECIALIST_PROMPT` is still a placeholder.
- The final response is post-processed by another LLM pass in `main.py`.
- Documentation is slightly ahead of implementation in a few places, so prompts and code should be treated as the most accurate behavior source.

## Operational Notes

- Keep customer context isolated by `customer_id`.
- Do not fabricate financial values.
- Ask for clarification when required details are missing.
- Treat the offer catalog as the product source of truth.
- The repo is designed to be extended with more specialist types later.

## Session Memory

When working in this repo, the most useful mental model is:

`CLI -> state init -> supervisor routing -> specialist execution -> synthesis -> final cleanup`

