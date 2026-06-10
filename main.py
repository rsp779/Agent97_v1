from langchain_core.messages import HumanMessage
from data.mock_db import DATASTORE
from settings import llm
from agent_state import initialise_state, update_extracted, append_short_term_memory
from graph_builder import banking_financial_graph

def main():
    print("\n=== IDFC FIRST BANK DIGITAL RM [PROD GRAPH] ===\n")
    customer_id = input("Customer ID : ").strip()

    try:
        customer_profile = DATASTORE.get_customer_profile(customer_id)
        customer_desc = customer_profile.get("customer_description", "Valued Customer")
    except Exception as e:
        print(f"\nError initializing customer profile: {e}")
        return

    welcome_prompt = f"""
    Customer Profile Segment/Description:
    {customer_desc}

    Generate a warm, custom banking welcome message
    CRITICAL: Maximum 15 words.
    """
    welcome = llm.invoke(welcome_prompt).content.strip()
    print(f"\nRM : {welcome}\n")

    # Initialize the centralized LangGraph execution matrix state safely
    state = initialise_state(customer_id=customer_id)
    update_extracted(state, **DATASTORE.get_customer_data(customer_id))
    update_extracted(
        state,
        long_term_memory=DATASTORE.get_customer_long_term_memory(customer_id),
        short_term_memory=[],
    )
    state["is_in_scope"] = True

    while True:
        user_query = input("You : ").strip()
        if user_query.upper() == "EXIT":
            print("\nSession logged off securely. Thank you for banking with IDFC FIRST Bank.")
            break
        if not user_query:
            continue

        # Flow conversation histories natively into the graph message list
        state["messages"].append(HumanMessage(content=user_query))
        
        # Atomically run the LangGraph sequential agent workflow pipeline
        output_state = banking_financial_graph.invoke(state)
        
        final_display = output_state["messages"][-1].content
        print(f"\nRM : {final_display}\n")
        
        # Track short-term memory for the current session
        append_short_term_memory(output_state, {
            "query": user_query,
            "response": final_display,
        })

        # Re-link live state track references to maintain persistent multi-turn history memory
        state = output_state


if __name__ == "__main__":
    main()
