import os
import sys


SRC_DIR = os.path.join(os.path.dirname(__file__), "src")
if os.path.isdir(SRC_DIR) and SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import main


if __name__ == "__main__":
    raise SystemExit(main.main())
