# Financial Agent LangGraph

This repository implements a banking agent orchestration system for IDFC FIRST Bank.
The system uses a state graph to route customer queries through specialized agents and compile safe, bank-aligned responses.

## Key Features

- Unified credit card specialist for all card-related products
- Dedicated home loan specialist with isolated offer data
- Live gold-collateral loan specialist with real-time gold price fetching
- Supervisor orchestrator for intent routing and clarification handling
- Specialist agents for offers, transactions, loans, and banking metadata
- Strict prompt rules to avoid inventing offer details or reward terms
- Extensible for future card products, home loan variants, and collateral-based loan types

## File Overview

- `main.py` - Entry point and interactive terminal interface
- `graph_builder.py` - Defines the state graph and routing logic
- `supervisor_agent.py` - Orchestrates query intent and ordered execution paths
- `workers_agent.py` - Worker nodes for each specialist agent (includes gold loan specialist with price fetch helpers)
- `prompts.py` - Prompt templates and behavior rules for all agents
- `agent_state.py` - Agent state initialization and data updates
- `data/` - Mock customer and offer datasets
- `agent.md` - Agent architecture and behavior documentation
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
- Ask for clarification when the customer query is vague or missing details.
- Route credit card-related queries to the `credit_card_specialist` agent.
- Route home loan queries to the `home_loan_specialist` agent.
- Route gold loan queries to the `gold_loan_specialist` agent with current gold pricing.
- Maintain strict product isolation: Personal Loan terms do not apply to Home Loans or Gold Loans.

## Gold Loan Integration

The gold loan specialist:
- Accepts gold quantity in grams, tolas, or ounces
- Fetches current gold prices from public APIs (`https://data-asg.goldprice.org/dbXRates/USD`, `https://api.metals.live/v1/spot/gold`)
- Calculates eligible loan disbursement range: `[0.8× total_gold_value, 1.2× total_gold_value]`
- Validates requested loan amounts against the eligible range
- Gracefully handles API failures with fallback messaging

### Testing

Run `test_gold_loan.py` to validate the gold loan specialist:
```bash
python test_gold_loan.py
```

## Notes

This project is designed for extension. New credit card product variants, home loan features, and collateral-based loan types can be added in the catalog and prompt logic.
