from langchain_community.tools import TavilySearchResults
from tavily import TavilyClient
from .BaseTool import BaseTool

class TavilyRentalIncomeTool(BaseTool):
    """
    Tool to search rental income data for a specified location and property type using Tavily search.
    """
    def __init__(self, api_key: str = "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"):
        super().__init__(
            name="Tavily Rental Income Tool",
            description="Search rental income data for a specified location and property type using Tavily."
        )
        try:
            self.client = TavilyClient(api_key=api_key)
            '''self.tavily_search_tool = TavilySearchResults(
                tavily_api_key="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", 
                max_results=5,
                search_depth="advanced", 
                include_answer=True,      
                include_raw_content=True, 
                include_images=True       
                
            )'''
        except Exception as e:
            raise ValueError(f"Failed to initialize Tavily Client: {str(e)}")

    def process(self, location: str, property_type: str):
        """
        Fetch rental income data based on location and property type.
        """
        query = f"What is the rental income for {property_type} in {location}?"
        try:
            content = self.client.search(query, search_depth="advanced")["results"]
            '''search_results = self.tavily_search_tool.run(query)
        
        print(f"search_results  {search_results}")
        if search_results:
            rental_info = ""
            for result in search_results:
                title = result.get("title", "No title")
                link = result.get("link", "No link")
                snippet = result.get("snippet", "No description")
                rental_info += f"Title: {title}\nLink: {link}\nDescription: {snippet}\n\n"

            return f"Rental income search results:\n{rental_info}"
        else:
            return "No rental income information found."
        '''
        
            return f"Rental income search results:\n{content}"
        except Exception as e:
            return f"Error fetching rental income data: {str(e)}"
