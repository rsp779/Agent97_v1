# Financial Agent LangGraph

This repository implements a banking agent orchestration system for IDFC FIRST Bank.
The system uses a state graph to route customer queries through specialized agents and compile safe, bank-aligned responses.

## Key Features

- Unified credit card specialist for all card-related products
- Supervisor orchestrator for intent routing and clarification handling
- Specialist agents for offers, transactions, loans, and banking metadata
- Strict prompt rules to avoid inventing offer details or reward terms
- Extensible for future card products like balance offers, merchant EMI, and card loans

## File Overview

- `main.py` - Entry point and interactive terminal interface
- `graph_builder.py` - Defines the state graph and routing logic
- `supervisor_agent.py` - Orchestrates query intent and ordered execution paths
- `workers_agent.py` - Worker nodes for each specialist agent
- `prompts.py` - Prompt templates and behavior rules for all agents
- `agent_state.py` - Agent state initialization and data updates
- `data/` - Mock customer and offer datasets
- `agent.md` - Agent architecture and behavior documentation

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

## Notes

This project is designed for extension. New credit card product variants and offer types can be added in the catalog and prompt logic.
