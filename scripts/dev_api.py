"""
Development Runner for FaceSentry API
"""

import os
import sys
import uvicorn

# Ensure project root is in Python module path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from apps.api.config import api_settings

if __name__ == "__main__":
    print(f"[*] Launching FaceSentry API on http://{api_settings.host}:{api_settings.port}")
    uvicorn.run(
        "apps.api.main:app",
        host=api_settings.host,
        port=api_settings.port,
        reload=True,
    )
