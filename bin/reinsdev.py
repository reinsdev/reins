#!/usr/bin/env python3
"""reinsdev entry: the Reins installer."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))

from reinsdev.cli import main  # noqa: E402

sys.exit(main())
