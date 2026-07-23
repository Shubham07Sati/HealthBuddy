import json
import os
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct

def seed_qdrant():
    qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=qdrant_url)
    collection_name = "lmis_knowledge"

    print(f"[+] Connecting to Qdrant at {qdrant_url}...")
    
    # Recreate collection for embedding vectors (384-dim sentence-transformers)
    client.recreate_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=384, distance=Distance.COSINE)
    )

    guidelines_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "knowledge_base", "guidelines", "monitoring_guidelines.json"
    )

    with open(guidelines_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    points = []
    idx = 1

    # Simple text embedding representation for indexing guidelines
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

    for condition_key, details in data.get("monitoring_guidelines", {}).items():
        disp_name = details.get("display_name", condition_key)
        for req in details.get("required_monitoring", []):
            text_snippet = f"Condition: {disp_name}. Metric: {req.get('metric_name')} (LOINC: {req.get('metric_code')}). Interval: {req.get('interval_description')}. Source: {req.get('evidence_source')}."
            vector = model.encode(text_snippet).tolist()
            
            points.append(
                PointStruct(
                    id=idx,
                    vector=vector,
                    payload={
                        "condition": condition_key,
                        "display_name": disp_name,
                        "metric_name": req.get("metric_name"),
                        "metric_code": req.get("metric_code"),
                        "interval_days": req.get("interval_days"),
                        "evidence_source": req.get("evidence_source"),
                        "text": text_snippet
                    }
                )
            )
            idx += 1

    client.upsert(collection_name=collection_name, points=points)
    print(f"[OK] Successfully seeded {len(points)} clinical guidelines into Qdrant vector database.")

if __name__ == "__main__":
    seed_qdrant()
