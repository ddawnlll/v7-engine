"""V7 Engine CLI — entrypoint invoked by `python3 -m cli`."""

import sys
from cli.v7_engine import main

if __name__ == "__main__":
    sys.exit(main())
