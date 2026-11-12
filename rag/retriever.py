import importlib

VARIANTS = {
    "v0": ("rag.variants.v0_naive", "retrieve"),
    "v1": ("rag.variants.v1_decompose", "retrieve_v0"),
    "v2": ("rag.variants.v2_hybrid", "retrieve"),
    "v1_v2": ("rag.variants.v1_decompose", "retrieve_v2"),
}


def get_retriever(name: str = "v0"):
    mod, fn = VARIANTS[name]
    return getattr(importlib.import_module(mod), fn)