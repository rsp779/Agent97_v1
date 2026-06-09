# AGENTS.md

## Purpose

This file is the working guide for agents contributing to this repository. It summarizes the repo structure, execution flow, and the conventions to follow when making changes.

## Repo Summary

This project is a LangGraph-based banking digital relationship manager for IDFC FIRST Bank. It routes customer queries to specialist agents, uses local customer and offer data, and produces terminal-friendly banking responses.

## Main Flow

1. `main.py` loads a customer ID and initializes the session state.
2. The customer query is appended to `AgentState`.
3. `supervisor_agent.py` determines the execution path.
4. Specialist nodes in `workers_agent.py` perform the requested analysis.
5. `graph_builder.py` coordinates routing between nodes.
6. The `synthesis` node generates the final response.
7. `main.py` optionally performs a final cleanup pass before printing.

## Important Files

- `main.py`: CLI entry point and conversation loop.
- `graph_builder.py`: LangGraph state machine.
- `supervisor_agent.py`: route planning and structured extraction.
- `workers_agent.py`: specialist node implementations and calculation helpers.
- `agent_state.py`: shared graph state and memory helpers.
- `data/mock_db.py`: JSON-backed customer, offer, and transaction store.
- `prompts.py`: prompt templates and behavior rules.
- `settings.py`: shared LLM initialization.
- `test_gold_loan.py`: test harness for gold-loan behavior.

## State Model

`AgentState` includes:

- `messages`
- `is_in_scope`
- `customer_id`
- `extracted_data`

Use the helper functions in `agent_state.py` to:

- initialize state
- append messages
- update extracted data
- store short-term memory

## Routing Notes

The supervisor writes an `ordered_path` into `extracted_data`, and the router uses that list to determine the next graph node.

Known specialist routes:

- `offers_specialist`
- `transaction_specialist`
- `loan_product_calculator`
- `home_loan_specialist`
- `gold_loan_specialist`
- `credit_card_specialist`
- `banking_specialist`

## Data Rules

- Customer context comes from the local JSON datastore.
- Offer recommendations must use the catalog and customer offer scores.
- Transaction analysis must use the stored transaction records.
- Do not invent financial values, rates, rewards, fees, or eligibility.

## Product Boundaries

- Credit card queries are centralized in `credit_card_specialist`.
- Home loan queries are handled by `home_loan_specialist`.
- Gold loan queries are handled by `gold_loan_specialist` and may use live gold prices.
- Personal loan queries usually follow `loan_product_calculator` and may involve `offers_specialist`.

## Implementation Caveats

- `BANKING_SPECIALIST_PROMPT` is currently a placeholder.
- The gold-loan flow depends on external price endpoints and falls back if they fail.
- The terminal response is post-processed by a second LLM call in `main.py`.
- Some docs are more expansive than the current implementation, so treat code and prompts as the source of truth.

## Editing Conventions

- Prefer small, focused changes.
- Preserve the repo’s existing LangGraph architecture unless the task explicitly requires a redesign.
- Do not overwrite user changes in unrelated files.
- Use `apply_patch` for file edits.
- Avoid introducing non-ASCII characters unless the file already uses them or there is a clear need.

## Working Principle

When changing this codebase, keep the following order of priority:

1. Preserve banking-data safety.
2. Preserve routing correctness.
3. Preserve numerical accuracy.
4. Preserve concise, professional user-facing responses.

