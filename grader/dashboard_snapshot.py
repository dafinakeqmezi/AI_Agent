"""Collect a dashboard in a separate process with its professor data root.

Only the server sets GRADER_DATA_ROOT. No mutable module paths are shared
between concurrent professors; academic rules remain in the application tree.
"""
import json
from .common import DATA_ROOT
from .dashboard import collect

if __name__ == "__main__":
    print(json.dumps(collect(DATA_ROOT), ensure_ascii=False))
