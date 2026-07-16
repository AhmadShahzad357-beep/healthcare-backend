import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3"):
        print(f"🔄 Loading Reranker: {model_name}...")
        self.model = CrossEncoder(model_name, max_length=512)
        print("✅ Reranker loaded.")

    def rerank(self, query: str, documents: list, top_k: int = 3) -> list:
        if not documents:
            return []
        pairs = [[query, doc['text']] for doc in documents]
        scores = self.model.predict(pairs)
        for i, doc in enumerate(documents):
            doc['rerank_score'] = float(scores[i])
        sorted_docs = sorted(documents, key=lambda x: x['rerank_score'], reverse=True)
        return sorted_docs[:top_k]
