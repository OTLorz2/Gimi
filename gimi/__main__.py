"""Allow running gimi as a module: python -m gimi"""

import sys
from gimi.core.cli import main

if __name__ == "__main__":
    sys.exit(main())
