import sys

# manimlib parses sys.argv at import time and chokes on pytest's flags
sys.argv = sys.argv[:1]
