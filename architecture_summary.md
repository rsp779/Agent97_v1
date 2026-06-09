# Architecture Summary

## Purpose

This repository implements a banking digital relationship manager for IDFC FIRST Bank using a LangGraph state machine. The system routes customer queries to specialist agents, uses local customer and offer data where available, and synthesizes a final response for terminal use.

## High-Level Flow

1. `main.py` starts the interactive CLI.
2. The customer enters a `customer_id`, which is used to load profile, offer, and transaction context from the local datastore.
3. The app initializes a shared `AgentState` object.
4. Each user query is appended to the state and passed into `banking_financial_graph`.
5. The supervisor decides which specialist node(s) should run.
6. Specialist nodes read customer context, perform product-specific analysis, and write results back into state.
7. The synthesis node produces the final response.
8. `main.py` optionally runs a final cleanup pass to keep the terminal output concise and professional.

## Core Components

### `main.py`

Entry point for the CLI application.

- Prompts for a customer ID.
- Loads customer profile data from the datastore.
- Generates a short welcome message with the LLM.
- Maintains the turn-by-turn interaction loop.
- Sends messages through the LangGraph execution pipeline.
- Performs a final formatting pass on the assistant response.

### `graph_builder.py`

Defines the LangGraph state machine.

- Registers the supervisor, worker, and synthesis nodes.
- Uses a conditional router to select the next node based on `extracted_data`.
- Supports ordered execution paths through the graph.
- Ends the flow at the `synthesis` node.

### `supervisor_agent.py`

Acts as the routing and extraction layer.

- Interprets the latest customer message.
- Produces an `ordered_path` describing which specialist nodes should run.
- Extracts loan-related entities such as:
  - loan amount
  - maximum EMI
  - requested tenure in months
  - loan type
- Stores routing and extraction output in `state["extracted_data"]`.

### `workers_agent.py`

Contains the specialist agent implementations.

- `offers_specialist_node`
- `transaction_specialist_node`
- `loan_product_calculator_node`
- `home_loan_specialist_node`
- `gold_loan_specialist_node`
- `credit_card_specialist_node`
- `banking_specialist_node`

It also includes:

- offer and banking context fetchers
- gold price fetch helpers
- EMI and fixed-deposit math helpers
- structured extraction schemas

### `agent_state.py`

Defines the shared execution state.

State fields include:

- `messages`
- `is_in_scope`
- `customer_id`
- `extracted_data`

It also provides helper functions for:

- initializing state
- appending messages
- storing short-term memory
- merging extracted values

### `data/mock_db.py`

Implements the local JSON-backed datastore.

It provides access to:

- customer profiles
- customer offer scores
- offer catalog
- transaction history
- long-term memory derived from profile and transaction data

The datastore is loaded from:

- `data/customer_profiles_db.json`
- `data/customer_offers_db.json`
- `data/variant_db.json`
- `data/transaction_db.json`

### `prompts.py`

Contains the system prompts for the orchestrator and all specialist agents.

The prompts define:

- routing behavior
- compliance boundaries
- response formatting rules
- product-specific behavior
- loan and offer guardrails

### `settings.py`

Creates the shared LLM client.

- Loads environment variables from `.env`
- Instantiates `ChatOpenAI(model="gpt-4o-mini")`

### `test_gold_loan.py`

Small integration harness for the gold loan flow.

It tests:

- gold quantity extraction
- current gold price lookup
- eligible loan range calculation
- clarification behavior when quantity is missing

## Data Model

### Customer Profile

Customer profile data is used for:

- identity and demographic context
- customer description
- long-term memory generation
- personalization of responses

### Offer Scores

The offer-score file maps each customer to a list of candidate offers with model scores.

These scores are used as an input signal, but specialist prompts emphasize semantic relevance and explicit catalog terms.

### Offer Catalog

The offer catalog is the product source of truth.

The current catalog includes:

- personal loan offers
- home loan offers
- credit card offers
- fixed-deposit offer

### Transactions

Transaction records are used for:

- spending analysis
- merchant analysis
- category-level aggregation
- customer memory generation

## Routing Model

The supervisor produces an ordered execution path.

Representative routes:

- `credit_card_specialist`
- `transaction_specialist`
- `home_loan_specialist`
- `loan_product_calculator -> offers_specialist`
- `banking_specialist`
- `gold_loan_specialist`

The router in `graph_builder.py` converts route tokens into concrete graph nodes.

## Product Rules

The system is designed to avoid inventing financial details.

Key rules enforced by prompts and code:

- Use only the provided customer and offer context.
- Do not fabricate rates, rewards, fees, or eligibility.
- Ask for clarification when required details are missing.
- Keep credit card queries centralized in the credit card specialist.
- Keep home loan logic separate from personal loan logic.
- Treat gold loan pricing as live and external to the local catalog.

## Current Implementation Notes

- The architecture is mostly complete for the main banking flows.
- `BANKING_SPECIALIST_PROMPT` is still a placeholder.
- The gold loan flow depends on live public price endpoints and falls back if they fail.
- `main.py` performs a second LLM pass to make the terminal response shorter and more polished.
- Some documentation is more expansive than the code, so the prompts should be treated as the most current behavior specification.

## Suggested Extension Points

The design is intentionally extensible.

Likely future additions include:

- richer banking metadata handling
- fuller account and balance support
- more offer variants
- more product-specific collateral loans
- stronger deterministic post-processing
- dedicated output schemas per specialist

## Quick Mental Model

If you want the shortest possible summary:

`CLI -> state init -> supervisor routes -> specialist runs -> synthesis -> terminal response`

