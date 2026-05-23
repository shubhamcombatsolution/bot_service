class BaseAgent:
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.tools = {}

    def add_tool(self, tool_name, tool):
        self.tools[tool_name] = tool

    def handle_request(self, user_input):
        """
        Handle the user request and select the appropriate tool to process the input.
        """
        if "appointment" in user_input:
            return self.tools['calendar_tool'].book_appointment(
                title="Appointment Title", 
                location="Location",
                description="Description of the appointment", 
                start_time_str="2025-02-01T09:00:00", 
                duration=1, 
                attendees=["example@example.com"]
            )
        elif "commute" in user_input:
            return self.tools['commute_tool'].process(
                origin="User Location", 
                destination="Property Location", 
                future_date_str="2025-02-01"
            )
        else:
            return "Sorry, I didn't understand that request."

