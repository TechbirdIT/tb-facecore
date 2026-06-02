"""
Edge Client

Client application for edge devices (kiosks, cameras) that:
- Captures frames from local camera
- Analyzes faces locally (facecore)
- Matches against embeddings from Frappe
- Posts check-ins to the attendance system
- Handles offline queuing via SQLite
"""

__version__ = "0.1.0"
