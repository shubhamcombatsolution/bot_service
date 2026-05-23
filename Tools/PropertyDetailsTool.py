import openai
from typing import List, Dict

class PropertyDetailsTool:
    def __init__(self, qdrant_client, openai_api_key: str):
        """
        Initializes the Property Details Tool.
        
        :param qdrant_client: Instance of QdrantIntegration for vector database operations.
        :param openai_api_key: OpenAI API key for generating embeddings.
        """
        self.qdrant_client = qdrant_client
        self.openai_api_key = openai_api_key
        openai.api_key = self.openai_api_key  # Set API key globally
    
    def _generate_embedding(self, text: str) -> List[float]:
        """
        Generates an embedding for a given text using OpenAI.
        
        :param text: Input text to embed.
        :return: Embedding vector as a list of floats.
        """
        response = openai.embeddings.create(
            input=text,
            model="text-embedding-ada-002"
        )
        return response.data[0].embedding
    
    def retrieve_chunks(self, query: str, top_k: int = 5) -> List[Dict]:
        """
        Retrieves the most relevant chunks of property details from Qdrant.
        
        :param query: User query about properties.
        :param top_k: Number of top results to fetch.
        :return: List of dictionaries containing relevant chunks.
        """
        query_embedding = self._generate_embedding(query)
        search_results = self.qdrant_client.search_properties(query_embedding, top_k)
        
        return [
            {"text": result.payload.get("text"), "relevance_score": result.score}
            for result in search_results
        ]
    
    def generate_response(self, query: str, chunks: List[Dict]) -> str:
        """
        Generates a response using LLM based on the retrieved chunks and user query.
        
        :param query: User query about properties.
        :param chunks: Relevant property detail chunks retrieved from Qdrant.
        :return: Generated response.
        """
        context = "\n\n".join(chunk["text"] for chunk in chunks)
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a real estate assistant providing property information."},
                {"role": "user", "content": f"Based on the following context, answer the user's question:\n\nContext:\n{context}\n\nQuestion: {query}\nAnswer:"}
            ],
            max_tokens=300
        )
        return response.choices[0].message["content"].strip()
    
    def get_property_response(self, query: str) -> str:
        """
        Handles the full flow: retrieve relevant chunks and generate a response.
        
        :param query: User query about properties.
        :return: User-friendly response about properties.
        """
        chunks = self.retrieve_chunks(query)
        
        if not chunks:
            return "I'm sorry, I couldn't find any relevant information about that."
        
        return self.generate_response(query, chunks)
