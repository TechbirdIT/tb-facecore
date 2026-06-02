"""
Embedding Service

FastAPI microservice for computing face embeddings from images.
The decoupling boundary between Frappe (which never imports InsightFace)
and the AI stack.
"""

__version__ = "0.1.0"
