"""Unit test module for individual pipeline steps.

This module provides standalone test functions for each pipeline step,
allowing you to run individual steps with inputs loaded from checkpoint files.

Usage:
    from unit_test import test_step1_structure
    result = test_step1_structure("output/pdf")

Or run from command line:
    python -m unit_test.step1_structure --checkpoint output/pdf/step1_bundle.json
"""

from __future__ import annotations

__version__ = "1.0.0"
__all__ = []
