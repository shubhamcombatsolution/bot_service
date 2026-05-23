# generateprompt.py
import json
from app.models import BaseAgent, CustomBot
from app.database.DatabaseOperationPostgreSQL import db_session

class DynamicPromptGenerator:
    def __init__(self, tenant_id, bot_id=None, industry="Real Estate and Property Management", tone="Friendly, Professional, and Clear"):
        self.tenant_id = tenant_id
        self.bot_id = bot_id
        self.industry = industry
        self.tone = tone
        self.bot_data = self._fetch_bot_data()
        
    def _fetch_bot_data(self):
        """Fetch bot data from the database."""
        if not self.bot_id or not self.tenant_id:
            print("Bot ID or Tenant ID missing, using fallback configuration.")
            return {
                "bot_name": "Default Bot",
                "purpose": "General-purpose chatbot assistance.",
                "core_features": ["General conversation support"],
                "tone": self.tone,
                "industry": self.industry,
                "instructions": ["Follow general conversational guidelines."]
            }
        
        session = next(db_session())
        try:
            bot = session.query(CustomBot).filter_by(
                bot_id=self.bot_id,
                tenant_id=self.tenant_id,
                del_flg=False
            ).first()
            
            if not bot:
                print(f"No bot found for bot_id {self.bot_id} and tenant_id {self.tenant_id}")
                return {
                    "bot_name": "Unknown Bot",
                    "purpose": "No purpose defined.",
                    "core_features": [],
                    "tone": self.tone,
                    "industry": self.industry,
                    "instructions": []
                }
            
            core_features = bot.core_features if isinstance(bot.core_features, list) else eval(bot.core_features) if bot.core_features else []
            instructions = bot.instructions if isinstance(bot.instructions, list) else eval(bot.instructions) if bot.instructions else []
            processed_instructions = [
                instr["question"] if isinstance(instr, dict) and "question" in instr else str(instr)
                for instr in instructions
            ]
            
            bot_data = {
                "bot_name": bot.bot_name,
                "purpose": bot.purpose or "No purpose defined.",
                "core_features": core_features,
                "tone": bot.tone_of_voice.value if bot.tone_of_voice else self.tone,
                "industry": bot.industry.value if bot.industry else self.industry,
                "instructions": processed_instructions
            }
            return bot_data
            
        except Exception as e:
            print(f"Error fetching bot data: {str(e)}")
            return {
                "bot_name": "Error Bot",
                "purpose": "Error retrieving bot data.",
                "core_features": [],
                "tone": self.tone,
                "industry": self.industry,
                "instructions": []
            }
        finally:
            session.close()

    def _fetch_agent_data(self, agent):
        """Helper method to ensure agent data is valid."""
        if not isinstance(agent, BaseAgent):
            raise ValueError("Agent must be an instance of BaseAgent")
        return {
            "role": agent.agent_role or "Unknown Role",
            "description": agent.agent_description or "No description provided",
            "instructions": agent.agent_instructions or "No instructions provided",
            "examples": agent.Examples or "No examples provided"
        }

    def generate_decision_agent_prompt(self, user_query, agent_response, decision_agent, history_text, query):
        """Generate prompt for decision agent."""
        agent_data = self._fetch_agent_data(decision_agent)
        bot_features = "\n- " + "\n- ".join(self.bot_data["core_features"]) if self.bot_data["core_features"] else "No specific features defined."
        bot_instructions = "\n- " + "\n- ".join(self.bot_data["instructions"]) if self.bot_data["instructions"] else "Follow general conversational guidelines."
        
        prompt_template = f"""
            Act As DecisionAgent, {agent_data['role']}

            ## **Agent Description**
            {agent_data['description']}
    
            ## **BOT CONFIGURATION**  
            - **Bot Name**: {self.bot_data['bot_name']}
            - **Industry**: {self.bot_data['industry']}
            - **Tone of Voice**: {self.bot_data['tone']}
            - **Purpose**: {self.bot_data['purpose']}
    
            ## **BOT INSTRUCTIONS**  
            {bot_instructions}
    
            ## **AGENT INSTRUCTIONS**  
            {agent_data['instructions']}
    
            ## **CHAT CONTEXT**  
            {history_text}  
    
            ## **CURRENT QUERY**  
            "{query}"  
    
            ## **AVAILABLE AGENTS**  
            - greeting: Handles greetings (e.g., "hi", "hello").
            - kb: Handles property searches (e.g., "3BHK", "rental properties").
            - nearby_facilities: Finds facilities like schools or hospitals.
            - calendar: Books appointments.
            - commute: Calculates travel time or routes.
            - rental_income: Estimates rental income.
            
            Based on the query and context, select the most appropriate agent to handle the request. Return only the agent name as a single word or phrase (e.g., kb, nearby_facilities).
        """
        return prompt_template
        
    def generate_response_agent_prompt(self, user_query, agent_response, response_agent):
        """Generate prompt for response agent."""
        agent_data = self._fetch_agent_data(response_agent)
        bot_features = "\n- " + "\n- ".join(self.bot_data["core_features"]) if self.bot_data["core_features"] else "No specific features defined."
        bot_instructions = "\n- " + "\n- ".join(self.bot_data["instructions"]) if self.bot_data["instructions"] else "Follow general conversational guidelines."
        
        prompt_template = f"""
            Act As ResponseAgent, {agent_data['role']}

            ## **Agent Description**
            {agent_data['description']}
    
            ## **BOT CONFIGURATION**  
            - **Bot Name**: {self.bot_data['bot_name']}
            - **Industry**: {self.bot_data['industry']}
            - **Tone of Voice**: {self.bot_data['tone']}
            - **Purpose**: {self.bot_data['purpose']}

            ## **BOT INSTRUCTIONS**  
            {bot_instructions}

            ## **AGENT INSTRUCTIONS**  
            {agent_data['instructions']} 

            ## **AGENT Examples**  
            {agent_data['examples']} 

            ---

            **User Query:** "{user_query}"  
            **Agent Response:** "{agent_response}"  

            Summarize the agent response in a {self.bot_data['tone']} tone, tailored to the {self.bot_data['industry']} industry. Provide specific, actionable details, avoiding generic phrases like "reach out to the company." If the response is incomplete, suggest a relevant next step (e.g., "Please specify a location for more details").
        """
        return prompt_template





# import json
# from app.models import BaseAgent, CustomBot
# from app.database.DatabaseOperationPostgreSQL import db_session

# class DynamicPromptGenerator:
#     def __init__(self, tenant_id, bot_id=None, industry="Real Estate and Property Management", tone="Friendly, Professional, and Clear"):
#         self.tenant_id = tenant_id
#         self.bot_id = bot_id
#         self.industry = industry
#         self.tone = tone
#         self.bot_data = self._fetch_bot_data()

#     def _fetch_bot_data(self):
#         """Fetch bot data from the database."""
#         if not self.bot_id or not self.tenant_id:
#             print("Bot ID or Tenant ID missing, using fallback configuration.")
#             return {
#                 "bot_name": "Default Bot",
#                 "purpose": "General-purpose chatbot assistance.",
#                 "core_features": ["General conversation support"],
#                 "tone": self.tone,
#                 "industry": self.industry,
#                 "instructions": ["Follow general conversational guidelines."]
#             }

#         session = next(db_session())
#         try:
#             bot = session.query(CustomBot).filter_by(
#                 bot_id=self.bot_id,
#                 tenant_id=self.tenant_id,
#                 del_flg=False
#             ).first()

#             if not bot:
#                 print(f"No bot found for bot_id {self.bot_id} and tenant_id {self.tenant_id}")
#                 return {
#                     "bot_name": "Unknown Bot",
#                     "purpose": "No purpose defined.",
#                     "core_features": [],
#                     "tone": self.tone,
#                     "industry": self.industry,
#                     "instructions": []
#                 }

#             core_features = bot.core_features if isinstance(bot.core_features, list) else eval(bot.core_features) if bot.core_features else []
#             instructions = bot.instructions if isinstance(bot.instructions, list) else eval(bot.instructions) if bot.instructions else []
#             processed_instructions = [
#                 instr["question"] if isinstance(instr, dict) and "question" in instr else str(instr)
#                 for instr in instructions
#             ]

#             bot_data = {
#                 "bot_name": bot.bot_name,
#                 "purpose": bot.purpose or "No purpose defined.",
#                 "core_features": core_features,
#                 "tone": bot.tone_of_voice.value if bot.tone_of_voice else self.tone,
#                 "industry": bot.industry.value if bot.industry else self.industry,
#                 "instructions": processed_instructions
#             }
#             return bot_data
#         except Exception as e:
#             print(f"Error fetching bot data: {str(e)}")
#             return {
#                 "bot_name": "Error Bot",
#                 "purpose": "Error retrieving bot data.",
#                 "core_features": [],
#                 "tone": self.tone,
#                 "industry": self.industry,
#                 "instructions": []
#             }
#         finally:
#             session.close()

#     def _fetch_agent_data(self, agent):
#         """Helper method to ensure agent data is valid."""
#         if not isinstance(agent, BaseAgent):
#             raise ValueError("Agent must be an instance of BaseAgent")
#         return {
#             "role": agent.agent_role or "Unknown Role",
#             "description": agent.agent_description or "No description provided",
#             "instructions": agent.agent_instructions or "No instructions provided",
#             "examples": agent.Examples or "No examples provided"
#         }

#     def generate_decision_agent_prompt(self, user_query, agent_response, decision_agent, history_text, query, available_agents=None):
#         """Generate prompt for decision agent."""
#         agent_data = self._fetch_agent_data(decision_agent)
#         bot_features = "\n- " + "\n- ".join(self.bot_data["core_features"]) if self.bot_data["core_features"] else "No specific features defined."
#         bot_instructions = "\n- " + "\n- ".join(self.bot_data["instructions"]) if self.bot_data["instructions"] else "Follow general conversational guidelines."
#         available_agents_str = "\n- " + "\n- ".join(available_agents or ["greeting", "kb", "nearby_facilities", "calendar", "commute", "rental_income", "sales_lead"])

#         prompt_template = f"""
#             Act As DecisionAgent, {agent_data['role']}

#             ## **Agent Description**
#             {agent_data['description']}

#             ## **BOT CONFIGURATION**  
#             - **Bot Name**: {self.bot_data['bot_name']}
#             - **Industry**: {self.bot_data['industry']}
#             - **Tone of Voice**: {self.bot_data['tone']}
#             - **Purpose**: {self.bot_data['purpose']}

#             ## **BOT INSTRUCTIONS**  
#             {bot_instructions}

#             ## **AGENT INSTRUCTIONS**  
#             {agent_data['instructions']}

#             ## **CHAT CONTEXT**  
#             {history_text}  

#             ## **CURRENT QUERY**  
#             "{query}"  

#             ## **AVAILABLE AGENTS**  
#             {available_agents_str}

#             Based on the query and context, select the most appropriate agent to handle the request. Return only the agent name as a single word or phrase (e.g., kb, nearby_facilities).
#         """
#         return prompt_template

#     def generate_response_agent_prompt(self, user_query, agent_response, response_agent):
#         """Generate prompt for response agent."""
#         agent_data = self._fetch_agent_data(response_agent)
#         bot_features = "\n- " + "\n- ".join(self.bot_data["core_features"]) if self.bot_data["core_features"] else "No specific features defined."
#         bot_instructions = "\n- " + "\n- ".join(self.bot_data["instructions"]) if self.bot_data["instructions"] else "Follow general conversational guidelines."

#         prompt_template = f"""
#             Act As ResponseAgent, {agent_data['role']}

#             ## **Agent Description**
#             {agent_data['description']}

#             ## **BOT CONFIGURATION**  
#             - **Bot Name**: {self.bot_data['bot_name']}
#             - **Industry**: {self.bot_data['industry']}
#             - **Tone of Voice**: {self.bot_data['tone']}
#             - **Purpose**: {self.bot_data['purpose']}

#             ## **BOT INSTRUCTIONS**  
#             {bot_instructions}

#             ## **AGENT INSTRUCTIONS**  
#             {agent_data['instructions']} 

#             ## **AGENT Examples**  
#             {agent_data['examples']} 

#             ---

#             **User Query:** "{user_query}"  
#             **Agent Response:** "{agent_response}"  

#             Summarize the agent response in a {self.bot_data['tone']} tone, tailored to the {self.bot_data['industry']} industry. Provide specific, actionable details, avoiding generic phrases like "reach out to the company." If the response is incomplete, suggest a relevant next step (e.g., "Please specify a location for more details").
#         """
#         return prompt_template

#     def generate_agent_prompt(self, agent_name, query, context, agent_data):
#         """Generate prompt for specific agent behavior."""
#         bot_features = "\n- " + "\n- ".join(self.bot_data["core_features"]) if self.bot_data["core_features"] else "No specific features defined."
#         bot_instructions = "\n- " + "\n- ".join(self.bot_data["instructions"]) if self.bot_data["instructions"] else "Follow general conversational guidelines."

#         prompt_template = f"""
#             You are {agent_name} in a {self.bot_data['industry']} chatbot named {self.bot_data['bot_name']}.
#             Tone: {self.bot_data['tone']}
#             Purpose: {self.bot_data['purpose']}
#             Query: {query}
#             Context: {context}
#             Instructions: {agent_data['instructions']}
#             Respond concisely, stay focused on the task, and ensure responses align with the {self.bot_data['industry']} industry.
#         """
#         return prompt_template   
        
        
#     def generate_greeting_prompt(self, user_input=""):
#         """Generate prompt for a dynamic greeting based on the directive."""
#         greeting_prompt_template = f"""                
#         You are a {tone} assistant for a {industry} chatbot named {bot_name}. 
#                  The bot's purpose is: "{purpose}".
#                  Generate a concise, engaging greeting message that:
#                  - Welcomes the user in a {tone} tone, using emojis if appropriate for a friendly tone.
#                  - Clearly reflects the bot's purpose and goals.
#                  - Only requests personal information (e.g., email, phone, name) if the purpose explicitly mentions collecting personal data (e.g., 'contact details', 'email', 'phone', 'name', 'lead').First ask to enter the email or name.
#                  - If the purpose does not involve personal information, focus on the specific preferences or actions mentioned in the purpose (e.g., commute preferences, property preferences) without asking for contact details.
#                  - Includes a specific call-to-action or follow-up question to guide the conversation toward achieving the purpose.
#                  - Avoids generic phrases like 'How can I help you today?' unless the purpose is truly general.
#                  - Keeps the message under 50 words.
#                  - Don't use instructions into the greeting message like "Remember to keep the tone polite, provide specific details, and prompt the user for necessary information to proceed" or "Remember to engage the user and guide them towards providing more specific information for a personalized response" or "If the response is incomplete, suggest a relevant next step such as "Please specify a location for more details". Only show the greeting message. Do NOT ADD OR USE ANY EXTRA INSTRUCTIONS.
#                  - Does not include any static links or URLs.
#                  - Does not include "what type of response is?" into greeting message like "
# This response is confident, welcoming, and prompts the user to take action by providing their contact information for personalized assistance. If the user doesn't respond, a relevant next step could be to ask for their location to narrow down property options."
#                  - Does not show any extra text. Just only show exact response.
#                  Example for purpose "capture user commute preferences (starting point, destination, travel mode) to provide personalized commute time assistance":
#                  "Hi! 👋 I'm {bot_name}, your {tone} {industry} assistant. Let's plan your commute! 🚗 Please share your starting point, destination, and preferred travel mode to get personalized commute time assistance."
#                  Example for purpose "capture user contact details and property preferences to generate leads":
#                  "Hi! 👋 I'm {bot_name}, your {tone} {industry} assistant. Let's find your dream property! 📧 Please share your email or phone, then tell me your property preferences."
#                  """       
#         return greeting_prompt_template.strip()