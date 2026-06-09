#!/usr/bin/env python3
"""
Test Gold Loan Specialist Integration
Simulates a gold loan query to validate end-to-end gold pricing and disbursement range calculation.
"""

import json
from langchain_core.messages import HumanMessage
from data.mock_db import DATASTORE
from agent_state import initialise_state, update_extracted
from graph_builder import banking_financial_graph


def test_gold_loan_specialist():
    print("\n=== TEST: Gold Loan Specialist Integration ===\n")
    
    # Use a fixed test customer
    customer_id = "rsp"
    
    try:
        customer_profile = DATASTORE.get_customer_profile(customer_id)
        print(f"[Setup] Customer ID: {customer_id}")
        print(f"[Setup] Customer Name: {customer_profile.get('DEMOGS_FIRST_NAME', 'Unknown')}\n")
    except Exception as e:
        print(f"[Error] Failed to load customer profile: {e}")
        return
    
    # Initialize graph state
    state = initialise_state(customer_id=customer_id)
    update_extracted(state, **DATASTORE.get_customer_data(customer_id))
    update_extracted(
        state,
        long_term_memory=DATASTORE.get_customer_long_term_memory(customer_id),
        short_term_memory=[],
    )
    state["is_in_scope"] = True
    
    # Test Case 1: Gold loan with gold quantity specified
    print("[Test 1] Query: Gold loan request with 50 grams of gold")
    print("-" * 60)
    
    query_1 = "I want to pledge 50 grams of gold and get a loan. What's the eligible loan range?"
    state["messages"] = [HumanMessage(content=query_1)]
    
    try:
        output_state_1 = banking_financial_graph.invoke(state)
        last_msg = output_state_1["messages"][-1].content
        print(f"Response:\n{last_msg}\n")
        extracted_1 = output_state_1.get("extracted_data", {})
        print(f"Extracted data keys: {list(extracted_1.keys())}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    # Test Case 2: Gold loan with specific tenure and EMI
    print("[Test 2] Query: Gold loan with requested tenure and specific amount")
    print("-" * 60)
    
    state = initialise_state(customer_id=customer_id)
    update_extracted(state, **DATASTORE.get_customer_data(customer_id))
    update_extracted(
        state,
        long_term_memory=DATASTORE.get_customer_long_term_memory(customer_id),
        short_term_memory=[],
    )
    state["is_in_scope"] = True
    
    query_2 = "I have 100 grams of gold and want a 2-lakh rupees loan for 24 months."
    state["messages"] = [HumanMessage(content=query_2)]
    
    try:
        output_state_2 = banking_financial_graph.invoke(state)
        last_msg = output_state_2["messages"][-1].content
        print(f"Response:\n{last_msg}\n")
        extracted_2 = output_state_2.get("extracted_data", {})
        print(f"Extracted data keys: {list(extracted_2.keys())}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    # Test Case 3: Gold loan without gold quantity (should ask for clarification)
    print("[Test 3] Query: Vague gold loan request without quantity")
    print("-" * 60)
    
    state = initialise_state(customer_id=customer_id)
    update_extracted(state, **DATASTORE.get_customer_data(customer_id))
    update_extracted(
        state,
        long_term_memory=DATASTORE.get_customer_long_term_memory(customer_id),
        short_term_memory=[],
    )
    state["is_in_scope"] = True
    
    query_3 = "I need a gold loan. Can you tell me the eligibility?"
    state["messages"] = [HumanMessage(content=query_3)]
    
    try:
        output_state_3 = banking_financial_graph.invoke(state)
        last_msg = output_state_3["messages"][-1].content
        print(f"Response:\n{last_msg}\n")
    except Exception as e:
        print(f"Error: {e}\n")
    
    print("\n=== Gold Loan Specialist Test Complete ===\n")


if __name__ == "__main__":
    test_gold_loan_specialist()
