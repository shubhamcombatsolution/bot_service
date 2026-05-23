from Tools.CalendarTool import CalendarTool
tool = CalendarTool(
    credentials_file="client_secret.json",
    token_file="token.json",
    auth_mode="manual",
    redirect_uri="https://api.jnanic.com/multi_agents/oauth2callback"
    
)

print(tool.get_auth_url())
