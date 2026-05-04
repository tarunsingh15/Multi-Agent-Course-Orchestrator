"""
Handle retrieval of relevant context from:
1. Internal vector store
2. External verified libraries 
"""
import os
import json
import logging
import requests
import numpy as np
import vertexai
from vertexai.language_models import TextEmbeddingInput, TextEmbeddingModel
from google.cloud import storage
from typing import List, Dict, Any
from urllib.parse import unquote

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "amazing-math-473517-f9")
LOCATION = "us-central1"

class RAGManager:
    """Manages the retrieval of context from internal and external sources."""
    def __init__(self):
        """Initializes the RAGManager by setting up the Vertex AI and GCS clients."""
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        self.storage_client = storage.Client()
        
    def _get_embedding(self, text: str) -> List[float]:
        """
        Generates embeddings for a single query string using the Vertex AI embedding model.
        """
        inputs = [TextEmbeddingInput(text=text, task_type = "RETRIEVAL_QUERY")]
        embeddings = self.embedding_model.get_embeddings(inputs)
        return embeddings[0].values
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculates the cosine similarity between two vectors."""
        return np.dot(a,b) / (np.linalg.norm(a) * np.linalg.norm(b))
    
    def retrieve_internal_context(self, query: str, chunks_uri: str, top_k: int= 5) -> str:
        """
        Retrieves the top-k relevant text chunks from GCS by embedding the query and
        comparing it to stored chunk embeddings using cosine similarity.
        """
        logger.info(f"Retrieving internal context for query: {query}")
        try:
            # 1. Download the chunks file from GCS.
            if chunks_uri.startswith("gs://"):
                bucket_name = chunks_uri.replace("gs://", "").split("/")[0]
                blob_name = "/".join(chunks_uri.replace("gs://", "")).split("/")[1:]
            else:
                bucket_name = chunks_uri.split("/")[3]
                blob_name = "/".join(chunks_uri.split("/"))[4:]
            
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blo(unquote(blob_name))
            
            if not blob.exists():
                logger.warning("Chunks file not found for RAG")
                return ""
            
            chunks_data = json.loads(blob.download_as_text())
            
            # 2. Generate an embedding for the input query.
            query_embedding = self._get_embedding(query)
            
            # 3. Score each chunk against the query using cosine similarity.
            scored_chunks = []
            for chunk in chunks_data:
                chunk_embedding = chunk.get("embedding")
                if not chunk_embedding:
                    continue
                
                score = self._cosine_similarity(query_embedding, chunk_embedding)
                scored_chunks.append((score, chunk.get("chunk_text", "")))
                
            # 4. Sort the chunks by score in descending order and select the top_k.
            scored_chunks.sort(key=lambda x : x[0], reverse=True)
            top_chunks = scored_chunks[:top_k]
            
            context_str = "/n".join([f"[Source: Uploaded Doc] {text}" for _, text in top_chunks])
            return context_str
        
        except Exception as e:
            logger.error(f"Error in internal retrieval: {e}")
            return ""

    def retrieve_external_context(self, topic: str) -> str:
        # Queries OpenLibrary API to verify book existence
        logger.info(f"Querying OpenLibrary for {topic}")
        try:
            url = f"https://openlibrary.org/search.json?q={topic}&limit=3"
            response = requests.get(url, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                docs = data.get("docs", [])
                
                # Format the book information into a readable string.
                external_info = []
                for doc in docs:
                    title = doc.get("title")
                    year = doc.get("first_publish_year")
                    author = ", ".join(doc.get("author_name", []))

                    external_info.append(f"- Book: '{title}' by {author} ({year})")
                if external_info:
                    return "Verified reference found in OpenLib: \n" + "\n".join(external_info)
            return ""
        except Exception as e:
            logger.warning(f"Failed ot fetch external data: {e}")
            return ""
    
    def get_combined_context(self, query: str, chunks_uri: str) -> str:
        """
        Combines context from both internal (document chunks) and external (OpenLibrary)
        sources into a single string to be used in the final prompt.
        """
        internal = self.retrieve_internal_context(query, chunks_uri)
        external = self. retrieve_external_context(query)
        
        combined = "### RAG Context \n"
        if internal:
            combined += f"#### From Uploaded materials:\n {internal}\n\n"
        if external:
            combined += f"#### From Verified External References:\n {external}\n"
            
        return combined
            
    
                    