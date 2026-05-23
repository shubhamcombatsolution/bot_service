class Agent:
    def __init__(self, name, description, provider, model, role, instructions, tools=None, examples=None):
        self.name = name
        self.description = description
        self.provider = provider
        self.model = model
        self.role = role
        self.instructions = instructions
        self.tools = tools or []
        self.examples = examples or []

    def process(self, query):
        return f"Processing '{query}' with {self.name} ({self.provider} - {self.model})"

    def __repr__(self):
        return f"<Agent: {self.name} ({self.provider}/{self.model})>"
