# Workflow

This folder contains a visual and text view of the current agent workflow.

Files:

- `workflow.mmd` - Mermaid diagram source
- `workflow.txt` - ASCII flow view
- `workflow.md` - Short explanatory overview

## How To Read It

The runtime flow is:

`main.py -> state init -> supervisor -> specialist node(s) -> synthesis -> terminal cleanup`

The supervisor is context-aware and can continue follow-up conversations from the last active specialist.

