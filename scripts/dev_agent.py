"""
Development Runner for FaceSentry Agent Daemon
"""

import os
import sys

# Ensure project root is in Python module path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from apps.agent.main import main

if __name__ == "__main__":
    main()
