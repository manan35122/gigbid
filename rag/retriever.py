import importlib

VARIANTS = {"v0": "rag.variants.v0_naive"}  # add v1, v2, v3... here as they are built


def get_retriever(name: str = "v0"):
    return importlib.import_module(VARIANTS[name]).retrieve