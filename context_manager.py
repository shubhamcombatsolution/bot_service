# import re
# import spacy
# from typing import Dict, List, Optional

# class ContextManager:
#     def __init__(self):
#         self.nlp = spacy.load("en_core_web_sm")  # Load spaCy model for entity extraction
#         self.context = {
#             "locations": [],  # List of mentioned locations
#             "property_types": [],  # List of mentioned property types (e.g., 3BHK)
#             "last_intent": None,  # Last classified intent
#             "origin": None,  # Explicit origin for commute queries
#             "destination": None,  # Explicit destination for commute queries
#             "last_property": None  # Last mentioned property or location
#         }

#     def extract_entities(self, query: str) -> Dict[str, str]:
#         """Extract entities like locations and property types from the query."""
#         doc = self.nlp(query)
#         entities = {"location": None, "property_type": None}

#         # Extract locations (GPE: Geo-Political Entities)
#         for ent in doc.ents:
#             if ent.label_ == "GPE":
#                 entities["location"] = ent.text
#                 if ent.text not in self.context["locations"]:
#                     self.context["locations"].append(ent.text)

#         # Extract property types using regex
#         property_pattern = r"\b(1bhk|2bhk|3bhk|4bhk|apartment|flat|villa)\b"
#         match = re.search(property_pattern, query.lower())
#         if match:
#             entities["property_type"] = match.group(0)
#             if match.group(0) not in self.context["property_types"]:
#                 self.context["property_types"].append(match.group(0))

#         return entities

#     def extract_parameters(self, query: str, chat_history: List[Dict]) -> Dict:
#         """Extract parameters for tools based on query and chat history."""
#         parameters = {}
#         query = query.lower()

#         # Extract origin and destination for commute
#         commute_pattern = r"from\s+([a-zA-Z\s]+)\s+to\s+([a-zA-Z\s]+)"
#         match = re.search(commute_pattern, query)
#         if match:
#             parameters["origin"] = match.group(1).strip()
#             parameters["destination"] = match.group(2).strip()
#             self.context["origin"] = parameters["origin"]
#             self.context["destination"] = parameters["destination"]
#         else:
#             # Fallback to context or chat history
#             parameters["origin"] = self.context.get("origin") or self.get_last_location(chat_history, role="origin")
#             parameters["destination"] = self.context.get("destination") or self.get_last_location(chat_history, role="destination")

#         # Extract facility type and location for nearby facilities
#         if "school" in query:
#             parameters["facility_type"] = "school"
#         elif "hospital" in query:
#             parameters["facility_type"] = "hospital"
#         elif "bus stop" in query or "bus" in query:
#             parameters["facility_type"] = "bus_stop"
#         if "facility_type" in parameters:
#             parameters["location"] = self.context.get("last_property") or self.get_last_location(chat_history)

#         # Extract calendar parameters
#         if "book" in query or "appointment" in query:
#             parameters["title"] = "Property Viewing Appointment"
#             parameters["location"] = self.context.get("last_property") or self.get_last_location(chat_history)
#             parameters["description"] = f"Appointment for {query}"
#             # Note: start_time and duration need user input; handled in calendar_agent

#         return parameters

#     def get_last_location(self, chat_history: List[Dict], role: Optional[str] = None) -> Optional[str]:
#         """Get the most recent location from chat history or context, considering role (origin/destination)."""
#         if role == "origin" and self.context.get("origin"):
#             return self.context["origin"]
#         if role == "destination" and self.context.get("destination"):
#             return self.context["destination"]
#         if self.context["locations"]:
#             return self.context["locations"][-1]
#         for entry in reversed(chat_history):
#             doc = self.nlp(entry["query"])
#             for ent in doc.ents:
#                 if ent.label_ == "GPE":
#                     return ent.text
#         return None

#     def update_context(self, intent: str, entities: Dict, response: Optional[str] = None):
#         """Update context with new intent, entities, and response details."""
#         self.context["last_intent"] = intent
#         if entities.get("location"):
#             if entities["location"] not in self.context["locations"]:
#                 self.context["locations"].append(entities["location"])
#         if entities.get("property_type"):
#             if entities["property_type"] not in self.context["property_types"]:
#                 self.context["property_types"].append(entities["property_type"])
#         # Update last_property based on response (e.g., property names or locations mentioned)
#         if response:
#             doc = self.nlp(response)
#             for ent in doc.ents:
#                 if ent.label_ == "GPE" and ent.text not in self.context["locations"]:
#                     self.context["locations"].append(ent.text)
#                     self.context["last_property"] = ent.text
#             # Extract property names (e.g., OM Residency, Girnar Heights)
#             property_pattern = r"(OM Residency|31BASIL|Girnar Heights|Mani Madhavi|Samarth Ganesh|Krushna Kunj|Square Business)"
#             match = re.search(property_pattern, response, re.IGNORECASE)
#             if match:
#                 self.context["last_property"] = match.group(0)

#     def get_context(self) -> Dict:
#         """Return current context."""
#         return self.context




import re
import spacy
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class ContextManager:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_sm")  # Load spaCy model for entity extraction
        self.context = {
            "locations": [],  # List of mentioned locations
            "property_types": [],  # List of mentioned property types (e.g., 3BHK)
            "last_intent": None,  # Last classified intent
            "origin": None,  # Explicit origin for commute queries
            "destination": None,  # Explicit destination for commute queries
            "last_property": None,  # Last mentioned property or location
            "custom_context": {}  # Store custom context (e.g., lead_data)
        }
        logger.debug("Initialized ContextManager with context: %s", self.context)

    def extract_entities(self, query: str) -> Dict[str, str]:
        """Extract entities like locations and property types from the query."""
        doc = self.nlp(query)
        entities = {"location": None, "property_type": None}

        # Extract locations (GPE: Geo-Political Entities)
        for ent in doc.ents:
            if ent.label_ == "GPE":
                entities["location"] = ent.text
                if ent.text not in self.context["locations"]:
                    self.context["locations"].append(ent.text)

        # Extract property types using regex
        property_pattern = r"\b(1bhk|2bhk|3bhk|4bhk|apartment|flat|villa)\b"
        match = re.search(property_pattern, query.lower())
        if match:
            entities["property_type"] = match.group(0)
            if match.group(0) not in self.context["property_types"]:
                self.context["property_types"].append(match.group(0))

        logger.debug("Extracted entities from query '%s': %s", query, entities)
        return entities

    def extract_parameters(self, query: str, chat_history: List[Dict]) -> Dict:
        """Extract parameters for tools based on query and chat history."""
        parameters = {}
        query = query.lower()
    
        # Helper method to validate location (assuming access to _validate_location or similar logic)
        def validate_location(location_str: str) -> Dict:
            if not location_str:
                return {"city": None, "area": None}
            # Simplified validation logic (replace with actual _validate_location if accessible)
            parts = [part.strip() for part in location_str.split(",")]
            city = parts[-1] if parts else None
            area = ", ".join(parts[:-1]) if len(parts) > 1 else None
            return {"city": city, "area": area}
    
        # Extract origin and destination for commute
        commute_pattern = r"from\s+([a-zA-Z\s]+)\s+to\s+([a-zA-Z\s]+)"
        match = re.search(commute_pattern, query)
        if match:
            parameters["origin"] = validate_location(match.group(1).strip())
            parameters["destination"] = validate_location(match.group(2).strip())
            self.context["origin"] = parameters["origin"]["city"] or parameters["origin"]["area"]
            self.context["destination"] = parameters["destination"]["city"] or parameters["destination"]["area"]
        else:
            # Fallback to context or chat history
            origin = self.context.get("origin") or self.get_last_location(chat_history, role="origin")
            destination = self.context.get("destination") or self.get_last_location(chat_history, role="destination")
            parameters["origin"] = validate_location(origin) if origin else None
            parameters["destination"] = validate_location(destination) if destination else None
    
        # Extract facility type and location for nearby facilities
        if "school" in query:
            parameters["facility_type"] = "school"
        elif "hospital" in query:
            parameters["facility_type"] = "hospital"
        elif "bus stop" in query or "bus" in query:
            parameters["facility_type"] = "bus_stop"
        if "facility_type" in parameters:
            last_location = self.context.get("last_property") or self.get_last_location(chat_history)
            parameters["location"] = validate_location(last_location) if last_location else None
    
        # Extract calendar parameters
        if "book" in query or "appointment" in query:
            parameters["title"] = "Property Viewing Appointment"
            last_location = self.context.get("last_property") or self.get_last_location(chat_history)
            parameters["location"] = validate_location(last_location) if last_location else None
            parameters["description"] = f"Appointment for {query}"
    
            # Extract start_time and duration if present
            time_pattern = r"\b(\d{1,2}:\d{2}\s*(am|pm)|today|tomorrow)\b"
            duration_pattern = r"\b(\d+\s*(minutes?|hours?|mins?))\b"
            time_match = re.search(time_pattern, query)
            duration_match = re.search(duration_pattern, query)
            if time_match:
                parameters["start_time"] = time_match.group(0)
            if duration_match:
                parameters["duration"] = duration_match.group(0)
    
        logger.debug("Extracted parameters from query '%s': %s", query, parameters)
        return parameters

    def get_last_location(self, chat_history: List[Dict], role: Optional[str] = None) -> Optional[str]:
        """Get the most recent location from chat history or context, considering role (origin/destination)."""
        if role == "origin" and self.context.get("origin"):
            return self.context["origin"]
        if role == "destination" and self.context.get("destination"):
            return self.context["destination"]
        if self.context["locations"]:
            return self.context["locations"][-1]
        for entry in reversed(chat_history):
            doc = self.nlp(entry["query"])
            for ent in doc.ents:
                if ent.label_ == "GPE":
                    return ent.text
        logger.debug("No last location found for role: %s", role)
        return None

    def update_context(self, intent: str, entities: Dict, response: Optional[str] = None, context: Optional[Dict] = None):
        """Update context with new intent, entities, response details, and custom context."""
        self.context["last_intent"] = intent
        if entities.get("location"):
            if entities["location"] not in self.context["locations"]:
                self.context["locations"].append(entities["location"])
        if entities.get("property_type"):
            if entities["property_type"] not in self.context["property_types"]:
                self.context["property_types"].append(entities["property_type"])
        # Update last_property based on response
        if response:
            doc = self.nlp(response)
            for ent in doc.ents:
                if ent.label_ == "GPE" and ent.text not in self.context["locations"]:
                    self.context["locations"].append(ent.text)
                    self.context["last_property"] = ent.text
            # Extract property names
            property_pattern = r"(OM Residency|31BASIL|Girnar Heights|Mani Madhavi|Samarth Ganesh|Krushna Kunj|Square Business)"
            match = re.search(property_pattern, response, re.IGNORECASE)
            if match:
                self.context["last_property"] = match.group(0)
        # Update custom context if provided
        if context is not None:
            self.context["custom_context"].update(context)
        logger.debug("Updated context with intent '%s', entities %s, custom_context: %s", intent, entities, self.context["custom_context"])

    def get_context(self) -> Dict:
        """Return current context."""
        return self.context

    def is_sales_lead_active(self) -> bool:
        """Check if a sales lead capture is in progress."""
        is_active = "lead_data" in self.context["custom_context"] and "lead_step" in self.context["custom_context"]
        logger.debug("Sales lead active check: %s, lead_step: %s", is_active, self.context["custom_context"].get("lead_step"))
        return is_active

    def validate_context(self) -> bool:
        """Validate integrity of custom_context for sales lead."""
        if "lead_data" in self.context["custom_context"] and "lead_step" not in self.context["custom_context"]:
            logger.warning("Invalid context: lead_data present but lead_step missing")
            return False
        if "lead_step" in self.context["custom_context"] and "lead_data" not in self.context["custom_context"]:
            logger.warning("Invalid context: lead_step present but lead_data missing")
            return False
        if self.context["custom_context"].get("lead_step") == "email" and self.context["custom_context"].get("lead_data", {}).get("email"):
            logger.warning("Stale lead_step: email already provided")
            return False
        logger.debug("Context validation passed: %s", self.context["custom_context"])
        return True

    def reset_stale_lead(self):
        """Reset stale lead context if stuck."""
        if self.context["custom_context"].get("lead_step") == "email" and self.context["custom_context"].get("lead_data", {}).get("email"):
            logger.warning("Resetting stale lead context")
            self.context["custom_context"].pop("lead_data", None)
            self.context["custom_context"].pop("lead_step", None)
            self.context["custom_context"]["lead_data"] = {}
            self.context["custom_context"]["lead_step"] = "full_name"
            logger.debug("Reset lead context: %s", self.context["custom_context"])








# import logging
# from datetime import datetime

# logger = logging.getLogger(__name__)

# class ContextManager:
#     def __init__(self):
#         self.context = {"custom_context": {}}
#         self.locked_agent = None
#         self.agent_state = {}

#     def lock_agent(self, agent_name):
#         """Lock an agent to prevent interruptions."""
#         self.locked_agent = agent_name
#         logger.debug(f"Locked agent: {agent_name}")

#     def unlock_agent(self):
#         """Unlock the current agent."""
#         self.locked_agent = None
#         self.agent_state.pop(self.locked_agent, None)
#         logger.debug("Unlocked agent")

#     def get_locked_agent(self):
#         """Get the currently locked agent."""
#         return self.locked_agent

#     def update_agent_state(self, agent_name, state):
#         """Update the state of an agent."""
#         self.agent_state[agent_name] = state
#         logger.debug(f"Updated state for {agent_name}: {state}")

#     def get_agent_state(self, agent_name):
#         """Get the state of an agent."""
#         return self.agent_state.get(agent_name, {})

#     def validate_context(self):
#         """Validate the current context."""
#         return isinstance(self.context, dict) and "custom_context" in self.context

#     def update_context(self, intent, entities, context=None):
#         """Update context with intent and entities."""
#         self.context["custom_context"].update({"intent": intent, "entities": entities})
#         if context:
#             self.context["custom_context"].update(context)
#         logger.debug(f"Updated context: {self.context}")

#     def get_context(self):
#         """Get the current context."""
#         return self.context

#     def extract_entities(self, query):
#         """Extract entities from query (placeholder)."""
#         # Implement entity extraction logic (e.g., using regex or NLP)
#         entities = {}
#         if "3bhk" in query.lower():
#             entities["property_type"] = "3BHK"
#         if "mumbai" in query.lower():
#             entities["location"] = "Mumbai"
#         return entities

#     def extract_parameters(self, query, chat_memory):
#         """Extract parameters from query and history (placeholder)."""
#         # Implement parameter extraction logic
#         parameters = {}
#         if "book" in query.lower():
#             parameters["title"] = query
#         return parameters

#     def get_last_location(self, chat_memory, role=None):
#         """Get the last mentioned location (placeholder)."""
#         for entry in reversed(chat_memory):
#             if "location" in entry["query"].lower():
#                 return entry["query"]
#         return None