#!/usr/bin/env python3
"""Entry point: python3 scripts/issue or python3 -m issue"""

import sys
import os

# When run as `python3 scripts/issue`, Python doesn't recognise the
# parent package, so relative imports fail.  Fix by adding the scripts
# directory to sys.path and importing absolutely.
_here = os.path.dirname(os.path.abspath(__file__))
_scripts = os.path.dirname(_here)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

try:
    from .cli import main          # works when run as `python3 -m issue`
except ImportError:
    from issue.cli import main     # works when run as `python3 scripts/issue`

if __name__ == "__main__":
    main()
