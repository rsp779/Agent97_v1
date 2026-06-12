# Financial Agent LangGraph

This repository implements a banking agent orchestration system for IDFC FIRST Bank.
The system uses a LangGraph state machine to route customer queries through specialized agents and produce concise, bank-aligned responses.

## Key Features

- Unified credit card specialist for explicit card-related queries
- Dedicated home loan specialist with offer-based rate and tenure handling
- Live gold-collateral loan specialist with real-time gold price fetching
- Supervisor orchestrator for intent routing, clarification handling, and follow-up context reuse
- Specialist agents for offers, transactions, loans, and banking metadata
- Strict prompt rules to avoid inventing offer details, tenures, or reward terms
- Deterministic routing through the supervisor, specialist nodes, and synthesis step
- Extensible for future card products, home loan variants, and collateral-based loan types

## File Overview

- `main.py` - Entry point and interactive terminal interface
- `graph_builder.py` - Defines the state graph and routing logic
- `supervisor_agent.py` - Orchestrates query intent, follow-up routing, and entity extraction
- `workers_agent.py` - Worker nodes for each specialist agent, including gold loan and EMI helpers
- `prompts.py` - Prompt templates and behavior rules for all agents
- `agent_state.py` - Agent state initialization, short-term memory, and conversation memory
- `data/` - Mock customer and offer datasets
- `architecture_summary.md` - High-level system architecture
- `memory.md` - Working notes and state behavior
- `test_gold_loan.py` - Test harness for gold loan specialist integration

## Usage

1. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```
2. Run the app:
   ```bash
   python main.py
   ```
3. Enter a customer ID and ask queries in the terminal.

## Behavior Rules

- Always use only the provided offer catalog and customer context.
- Never invent benefits, rates, cashback, or reward points.
- Never invent loan tenures, loan amounts, or offer limits.
- Ask for clarification when the customer query is vague or missing details.
- Route credit card-related queries only when explicit card language is present.
- Route home loan queries to the `home_loan_specialist` agent.
- Route gold loan queries to the `gold_loan_specialist` agent with current gold pricing.
- Maintain strict product isolation: Personal Loan terms do not apply to Home Loans or Gold Loans.
- Preserve customer context across turns using rolling short-term and longer conversation memory.
- Do not rewrite validated gold-loan rejections in synthesis.

## Context Handling

- Short-term memory stores the last few turns.
- Conversation memory keeps a longer rolling chat history.
- Long-term customer memory is loaded from the datastore at session start.
- Follow-up queries reuse the last active specialist when the context is clear.

## Token Logging

- Every LLM call prints input, output, and total token counts in the terminal.
- If the model API is unavailable, the app falls back safely instead of crashing.

## Gold Loan Integration

The gold loan specialist:
- Accepts gold quantity in grams, tolas, or ounces
- Fetches current gold prices from public APIs (`https://data-asg.goldprice.org/dbXRates/USD`, `https://api.metals.live/v1/spot/gold`)
- Calculates eligible loan disbursement range: `[0.8× total_gold_value, 1.2× total_gold_value]`
- Validates requested loan amounts against the eligible range
- Uses the only allowed fallback price when live pricing fails: `Rs 15000 per gram` or `$150 per gram`

## Loan Rules

- Loan amount must not exceed the offer ceiling.
- Interest rate comes from the offer, not user input.
- Tenure is taken from the offer when the user does not provide it.
- If the user provides tenure, the effective tenure is capped by the offer tenure.
- EMI checks stay active for loan requests.

### Testing

Run `test_gold_loan.py` to validate the gold loan specialist:
```bash
python test_gold_loan.py
```

## Notes

This project is designed for extension. New credit card product variants, home loan features, and collateral-based loan types can be added in the catalog and prompt logic.

## Response Style

- The terminal prints the final graph response directly.
- The output should be plain, customer-readable text, not raw JSON.
