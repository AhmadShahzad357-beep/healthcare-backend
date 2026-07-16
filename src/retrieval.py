# src/retrieval.py (UPGRADED)
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import CHROMA_DIR, TOP_K, SIMILARITY_THRESHOLD, EMBEDDING_MODEL

import chromadb
from chromadb.utils import embedding_functions

class MedicalRetriever:
    _instance = None
    _collection = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        print("🔄 Initializing MedicalRetriever (once)...")
        self.client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        # Use medical_knowledge (since we switched to word-based ingestion)
        self.collection = self.client.get_collection("medical_knowledge")
        self.threshold = SIMILARITY_THRESHOLD
        print(f"✅ Retriever ready. Collection: medical_knowledge (Threshold={self.threshold})")

    def search(self, query: str) -> list:
        results = self.collection.query(
            query_texts=[query],
            n_results=TOP_K  # now TOP_K=1 (set in config)
        )
        if not results or not results['documents']:
            return []
        docs = []
        for i, chunk in enumerate(results['documents'][0]):
            similarity = round(1 - results['distances'][0][i], 3)
            if similarity >= self.threshold:
                docs.append({
                    "text": chunk,
                    "source": results['metadatas'][0][i].get("source", "unknown"),
                    "similarity_score": similarity
                })
        return docs[:TOP_K]  # already top K

    def search_with_context(self, query: str) -> str:
        results = self.search(query)
        if not results:
            return ""
        context_text = ""
        for item in results:
            context_text += f"Source: {item['source']} (Score: {item['similarity_score']:.3f})\n{item['text']}\n\n"
        return context_text.strip()
