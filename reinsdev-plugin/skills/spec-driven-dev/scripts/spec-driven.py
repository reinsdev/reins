#!/usr/bin/env python3
"""Reins spec-driven CLI entry."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib'))

from spec_driven.cli import main  # noqa: E402

sys.exit(main())
