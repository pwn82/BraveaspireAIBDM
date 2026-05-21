"""
ChromaDB vector service for company similarity search and lead recommendations.
Uses ChromaDB's built-in embedding function (no PyTorch required).
"""
import os
import logging
from typing import Optional

logger = logging.getLogger("vector")

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VECTOR_DIR = os.path.join(BASE_DIR, "vector_db")


class VectorService:
    def __init__(self):
        self._client     = None
        self._collection = None
        self._available  = None   # lazy-check

    def _init(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import chromadb
            from chromadb.utils import embedding_functions
            os.makedirs(VECTOR_DIR, exist_ok=True)
            self._client = chromadb.PersistentClient(path=VECTOR_DIR)
            ef = embedding_functions.DefaultEmbeddingFunction()
            self._collection = self._client.get_or_create_collection(
                name="companies",
                embedding_function=ef,
                metadata={"hnsw:space": "cosine"},
            )
            self._available = True
            logger.info("ChromaDB initialised.")
        except Exception as e:
            logger.warning(f"ChromaDB not available: {e}")
            self._available = False
        return self._available

    # ── Indexing ──────────────────────────────────────────────────────────────

    def index_company(self, company: dict):
        if not self._init():
            return
        doc_id = str(company["id"])
        text   = self._company_to_text(company)
        meta   = {
            "name":     company.get("name", ""),
            "industry": company.get("industry", ""),
            "score":    str(company.get("score", 0)),
            "status":   company.get("status", ""),
        }
        try:
            self._collection.upsert(ids=[doc_id], documents=[text], metadatas=[meta])
        except Exception as e:
            logger.warning(f"index_company error: {e}")

    def index_all(self, companies: list[dict]):
        if not self._init():
            return
        if not companies:
            return
        ids   = [str(c["id"]) for c in companies]
        docs  = [self._company_to_text(c) for c in companies]
        metas = [{"name": c.get("name",""), "industry": c.get("industry",""),
                  "score": str(c.get("score",0)), "status": c.get("status","")}
                 for c in companies]
        try:
            self._collection.upsert(ids=ids, documents=docs, metadatas=metas)
            logger.info(f"Indexed {len(companies)} companies in ChromaDB.")
        except Exception as e:
            logger.warning(f"index_all error: {e}")

    # ── Search ────────────────────────────────────────────────────────────────

    def find_similar(self, query: str, n: int = 5) -> list[dict]:
        """Find companies semantically similar to the query text."""
        if not self._init():
            return []
        try:
            results = self._collection.query(query_texts=[query], n_results=min(n, 10))
            output = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta = results["metadatas"][0][i]
                dist = results["distances"][0][i]
                output.append({
                    "id":         doc_id,
                    "name":       meta.get("name", ""),
                    "industry":   meta.get("industry", ""),
                    "score":      meta.get("score", "0"),
                    "status":     meta.get("status", ""),
                    "similarity": round(1 - dist, 3),
                })
            return output
        except Exception as e:
            logger.warning(f"find_similar error: {e}")
            return []

    def recommend_leads(self, won_company_ids: list[int], n: int = 5) -> list[dict]:
        """Recommend leads similar to already-won companies."""
        if not self._init() or not won_company_ids:
            return []
        try:
            # Build combined query from won companies' docs
            results = self._collection.get(ids=[str(i) for i in won_company_ids])
            docs    = results.get("documents", [])
            if not docs:
                return []
            combined_query = " ".join(docs)
            return self.find_similar(combined_query, n=n)
        except Exception as e:
            logger.warning(f"recommend_leads error: {e}")
            return []

    def is_available(self) -> bool:
        return self._init()

    @staticmethod
    def _company_to_text(c: dict) -> str:
        return (
            f"{c.get('name','')} {c.get('industry','')} {c.get('location','')} "
            f"{c.get('tech_stack','')} {c.get('pain_points','')} "
            f"employees:{c.get('employee_size','')} score:{c.get('score','')}"
        )
