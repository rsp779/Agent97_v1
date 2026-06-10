# Workflow Overview

The application is a stateful LangGraph conversation system.

## Runtime Order

1. `main.py` receives the user message.
2. `AgentState` is updated with the new turn.
3. `supervisor_node` inspects the latest message plus conversation context.
4. The supervisor routes to one specialist node.
5. The specialist uses the customer data and offer data it is allowed to see.
6. The `synthesis` node compiles the final answer.
7. `main.py` formats the result for terminal output.

## Main Branches

- Home loan: stay within eligible home-loan offers only.
- Gold loan: check customer eligibility first, then fetch live gold price.
- Credit card: route only to the unified card specialist.
- Transactions: use stored transaction history.
- Offers: use offer catalog plus customer score list.
- Banking: use profile and memory context.

## Context Handling

The supervisor now tracks:

- the current active specialist
- recent short-term memory
- the latest extracted loan fields

That helps the system continue follow-up questions like:

- `18 months`
- `what will be my emi`
- `what is the max amount`

