"""Does V8 refuse to return evidence for a requirement the persona cannot prove?"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from rag.variants.v8_corrective import retrieve_one  # noqa: E402

CASES = [  # (persona, requirement, should the persona have evidence?)
    ("ai_engineer", "Build a RAG chatbot with reranking", True),
    ("ai_engineer", "Train a churn prediction model with XGBoost", True),
    ("ai_engineer", "Run Celery workers and Kubernetes autoscaling", False),
    ("ai_engineer", "Design a Power BI dashboard with DAX", False),
    ("ai_engineer", "Run Stripe checkout and Shopify store setup", False),
    ("data_analyst", "Build dbt models in BigQuery", True),
    ("data_analyst", "Fine-tune a 7B LLM with LoRA", False),
    ("fullstack_dev", "Build a Next.js storefront with Stripe", True),
    ("fullstack_dev", "Train a CNN for defect detection", False),
]
right = 0
for pid, req, expect in CASES:
    r = retrieve_one(pid, req, 3)
    got = not r["no_evidence"]
    right += got == expect
    print("OK " if got == expect else "MISS", pid, "|", req, "| evidence:", got, "| tries:", len(r["log"]))
print(f"{right}/{len(CASES)} correct")