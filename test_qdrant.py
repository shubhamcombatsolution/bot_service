import os
from openai import OpenAI
from qdrant_client import QdrantClient
from dotenv import load_dotenv
load_dotenv()

# ---------- ENV CHECK ----------
assert os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY not set"

# ---------- CLIENTS ----------
openai_client = OpenAI()

qdrant_client = QdrantClient(
    url="http://13.200.211.217:6333",
    check_compatibility=False
)

# ---------- QUERY ----------
query_text = "ProductName: AN14,  Manufacturer Name : AIRFASCO"

# ---------- EMBEDDING ----------
query_vector = openai_client.embeddings.create(
    model="text-embedding-ada-002",
    input=query_text
).data[0].embedding

# ---------- SEARCH (YOUR REQUIRED STYLE) ----------
search_results = qdrant_client.search(
    collection_name="tenant_46_new_product_and_make_mapping",
    query_vector=query_vector,
    limit=10,
    with_payload=True,
)

# ---------- RESULTS ----------
for i, hit in enumerate(search_results, 1):
    print(f"\nResult {i}")
    print("Score:", hit.score)
    print("Payload:", hit.payload)






# import os
# from qdrant_client import QdrantClient
# from qdrant_client.http import models
# from typing import Optional, List
# from openai import OpenAI

# # ---------- Your embedding setup ----------
# DEFAULT_EMBEDDING_MODEL = "text-embedding-ada-002"

# def get_embedding_model(provider: Optional[str] = None, model_name: Optional[str] = None, secret_key: Optional[str] = None) -> dict:
#     """Return the embedding model configuration and vector size based on user input or default."""
#     OPENAI_MODEL_DIMENSIONS = {
#         "text-embedding-ada-002": 1536,
#         "text-embedding-3-small": 1536,
#         "text-embedding-3-large": 3072
#     }

#     if provider and model_name and secret_key:
#         if provider.lower() == "openai":
#             client = OpenAI(api_key=secret_key)
#             vector_size = OPENAI_MODEL_DIMENSIONS.get(model_name, 1536)
#             return {
#                 "provider": "openai",
#                 "model_name": model_name,
#                 "client": client,
#                 "vector_size": vector_size
#             }

#     # fallback to env
#     openai_api_key = os.getenv("OPENAI_API_KEY")
#     if not openai_api_key:
#         raise ValueError("OPENAI_API_KEY environment variable not set.")

#     client = OpenAI(api_key=openai_api_key)
#     vector_size = OPENAI_MODEL_DIMENSIONS.get(DEFAULT_EMBEDDING_MODEL, 1536)
#     return {
#         "provider": "openai",
#         "model_name": DEFAULT_EMBEDDING_MODEL,
#         "client": client,
#         "vector_size": vector_size
#     }

# def get_embeddings(texts: List[str], embedding_config: dict) -> List[List[float]]:
#     """Generate embeddings for a list of texts using the specified embedding configuration."""
#     if embedding_config["provider"] == "openai":
#         response = embedding_config["client"].embeddings.create(
#             model=embedding_config["model_name"],
#             input=texts
#         )
#         return [item.embedding for item in response.data]
#     else:
#         raise ValueError(f"Unsupported provider: {embedding_config['provider']}")

# # ---------- Qdrant search ----------
# def search_qdrant(query: str, collection_name: str = "batra_kb"):
#     # Connect to Qdrant
#     client = QdrantClient(host="localhost", port=6333)

#     # Get number of points in collection
#     info = client.get_collection(collection_name)
#     num_points = info.points_count
#     print(f"Collection '{collection_name}' has {num_points} points.")

#     # Get embeddings for query
#     embedding_cfg = get_embedding_model()
#     query_vector = get_embeddings([query], embedding_cfg)[0]

#     # Search top 5
#     results = client.search(
#         collection_name=collection_name,
#         query_vector=query_vector,
#         limit=5,
#         search_params=models.SearchParams(hnsw_ef=128, exact=False)  # cosine similarity by default
#     )

#     print("\nTop 5 matches:")
#     for idx, r in enumerate(results, start=1):
#         print(f"{idx}. Score={r.score:.4f}, Payload={r.payload}")

# if __name__ == "__main__":
#     search_qdrant("what amenities dr batras colic provides")
