"""Pytest configuration and test fixtures."""
import pytest
import os
import sys

# Ensure backend root is on Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Tests should not download/load the reranker model or contact MCP servers at startup
os.environ.setdefault("WARMUP_ON_STARTUP", "false")
