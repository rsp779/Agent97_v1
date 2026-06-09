from __future__ import annotations
import json
from pathlib import Path
from typing import Dict,Any,List


class DataStore:

    """Central datastore for all customer information."""

    def __init__(
        self,
        profile_file:str,
        customer_offer_file:str,
        offer_file:str,
        transaction_file:str
    ):
        self.profile_db=self._load_json(profile_file)
        self.customer_offer_db=self._load_json(customer_offer_file)
        self.offer_db=self._load_json(offer_file)
        self.transaction_db=self._load_json(transaction_file)

    @staticmethod
    def _load_json(file_path:str)->Dict:
        """Load JSON file into memory."""
        with open(Path(file_path),"r",encoding="utf-8") as f:
            return json.load(f)

    def validate_customer(self,customer_id:str):
        """Validate that customer exists in datastore."""
        if customer_id not in self.profile_db:
            raise ValueError(f"Customer '{customer_id}' not found")

    def get_customer_profile(self,customer_id:str)->Dict[str,Any]:
        """
        Retrieve complete customer profile.

        Contains:
        - demographics
        - customer description
        - owned products
        - occupation
        - location information
        """
        self.validate_customer(customer_id)
        return self.profile_db[customer_id]

    def get_customer_transactions(
        self,
        customer_id:str
    )->List[Dict[str,Any]]:
        """
        Retrieve all customer transactions.

        Includes both savings account and credit card transactions.
        Agents should perform their own filtering and analysis.

        columns values and meaning :
        transactionType : Describes the type of transactions (UPI,OFFLINE,ONLINE)

        timestamp : The exact timestamp on which the transaction has happend (I includes date and time of the transaction)

        categoryType : The category of spead where it was on (Utility/Fuel/Expense/Qmart/HPCL(fuel compamy)/Restraunts and other categories)

        amount : The exact amount of which transactions occured

        MERC_NAME : Merchant Name like (Rapido,ASTROTALK)

        transaction_type : whether it is Saving account transaction or Credit Card Transaction

        """
        self.validate_customer(customer_id)
        return self.transaction_db.get(customer_id,[])

    def get_customer_offer_scores(
        self,
        customer_id:str
    )->List[Dict[str,Any]]:
        """
        Retrieve raw customer offer scores.

        Contains:
        - offer_id : The offers for which customer is eligible
        - score : This is model generate score

        Agents should perform ranking and selection.
        """
        self.validate_customer(customer_id)
        return self.customer_offer_db.get(customer_id,[])

    def get_offer_catalog(self)->Dict[str,Any]:
        """
        Retrieve complete offer catalogue.

        Maps:
        offer_id -> offer content
        content : The exact offer which customer is eligible for

        Agents can lookup offer descriptions and generate recommendations.
        """
        return self.offer_db

    def get_offer(self,offer_id:str)->Dict[str,Any]:
        """
        Retrieve a specific offer by offer id.
        """
        return self.offer_db.get(offer_id,{})

    def get_customer_data(self,customer_id:str)->Dict[str,Any]:
        """
        Retrieve all available customer information.

        Returns:
        - profile
        - transactions
        - offer scores

        Intended for supervisor agents that need full context.
        """
        self.validate_customer(customer_id)

        return {
            "customer_id":customer_id,
            "profile":self.profile_db[customer_id],
            "transactions":self.transaction_db.get(customer_id,[]),
            "offer_scores":self.customer_offer_db.get(customer_id,[])
        }


DATASTORE=DataStore(
    profile_file="data/customer_profiles_db.json",
    customer_offer_file="data/customer_offers_db.json",
    offer_file="data/variant_db.json",
    transaction_file="data/transaction_db.json"
)
# print(DATASTORE.get_offer_catalog.get(x["offer_id"],{}))
