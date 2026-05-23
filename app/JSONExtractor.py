import json
import re

class JSONExtractor:
    """
    A class to handle JSON extraction and parameterization.
    """
    def __init__(self, response: str):
        """
        Initialize with the response string.
        
        Parameters:
            response (str): A string containing JSON data.
        """
        self.response = response

    def extract(self) -> dict:
      
        try:
            # Extract the JSON-like part of the response using a regex
            json_pattern = re.search(r'{.*}', self.response, re.DOTALL)
            if json_pattern:
                json_data_str = json_pattern.group()  # Extract the JSON part
                # Convert single quotes to double quotes and parse JSON
                parsed_data = json.loads(json_data_str.replace("'", '"'))
                return parsed_data
            else:
                print("No valid JSON found in the response.")
                return None
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return None

    def is_valid(self) -> bool:
      
        try:
            json_pattern = re.search(r'{.*}', self.response, re.DOTALL)
            if json_pattern:
                json_data_str = json_pattern.group()
                json.loads(json_data_str.replace("'", '"'))
                return True
            else:
                return False
        except json.JSONDecodeError:
            return False

    def to_parameters(self) -> tuple:
         
        json_data = self.extract()
        print(f"JSON DATA   :  {json_data}")
        if json_data:
            intent = json_data.get("intent", "").strip()
            print(f"intent DATA   :  {intent}")
            symbol = json_data.get("symbol", "").strip()
            print(f"symbol DATA   :  {symbol}")
            quantity = json_data.get("quantity", "").strip()
            print(f"quantity DATA   :  {quantity}")
            price = json_data.get("price", "").strip()
            print(f"price DATA   :  {price}")
            stop_loss_take_profit = json_data.get("stop_loss_take_profit", "").strip()
            print(f"stop_loss_take_profit DATA   :  {stop_loss_take_profit}")
            message = json_data.get("message", "").strip()
            print(f"message DATA   :  {message}")
            order_id = json_data.get("order_id", "").strip()
            print(f"order_id DATA   :  {order_id}")
            return intent, symbol, quantity, price, stop_loss_take_profit, message, order_id
        else:
            return None

 