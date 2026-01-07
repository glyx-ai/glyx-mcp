
from fastmcp import Context
import inspect

print("Context attributes:")
for name, _ in inspect.getmembers(Context):
    if not name.startswith("_"):
        print(name)
