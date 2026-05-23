import requests
from .BaseTool import BaseTool

class FinanceTool(BaseTool):
    """
    Tool to calculate loan eligibility based on CIBIL score and salary.
    """
    def __init__(self, bankbazaar_api_key):
        super().__init__(
            name="Finance Tool",
            description="Calculate loan eligibility for users based on financial information."
        )
        self.bankbazaar_api_key = bankbazaar_api_key

    def process(self, cibil_score, salary):
        """
        Calculate loan eligibility.

        Args:
            cibil_score (int): User's CIBIL score.
            salary (float): User's monthly salary.

        Returns:
            str: Loan eligibility information.
        """
        if cibil_score < 600:
            return "Loan not approved due to low CIBIL score."

        # Prepare the request payload
        payload = {
            'cibil_score': cibil_score,
            'salary': salary,
            'api_key': self.bankbazaar_api_key
        }

        # Make a request to the BankBazaar API
        response = requests.post('https://api.bankbazaar.com/loan_offers', data=payload)

        if response.status_code == 200:
            loan_offers = response.json()
            if loan_offers:
                offers = "\n".join([f"Bank: {offer['bank_name']}, Loan Amount: {offer['loan_amount']}, Interest Rate: {offer['interest_rate']}%" for offer in loan_offers])
                return f"Eligible loan offers:\n{offers}"
            else:
                return "No loan offers available."
        else:
            return f"Error fetching loan offers: {response.status_code} - {response.text}"
