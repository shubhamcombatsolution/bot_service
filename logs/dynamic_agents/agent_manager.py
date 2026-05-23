from agent import Agent

def create_agent(config):
    return Agent(
        name=config.get("name"),
        description=config.get("description"),
        provider=config.get("provider"),
        model=config.get("model"),
        role=config.get("role"),
        instructions=config.get("instructions"),
        tools=config.get("tools"),
        examples=config.get("examples"),
    )
