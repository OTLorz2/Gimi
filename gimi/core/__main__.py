"""Allow running gimi.core as a module: python -m gimi.core"""

import sys
from gimi.core.cli import main

if __name__ == "__main__":
    sys.exit(main())
