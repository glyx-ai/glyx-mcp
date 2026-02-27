import asyncio
import os
import sys
from dotenv import load_dotenv

# Add src to path so we can import the agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

# Load environment variables
load_dotenv()

from agents.linear_agent import linear_agent, LinearTools  # noqa: E402


async def main():
    api_key = os.environ.get("LINEAR_API_KEY")
    if not api_key:
        print("Error: LINEAR_API_KEY not found in environment variables.")
        print("Please add it to your .env file or export it.")
        return

    print("Initializing Linear Agent...")
    deps = LinearTools(api_key=api_key)

    # Test 1: List Teams
    print("\n--- Test 1: Listing Teams ---")
    try:
        result = await linear_agent.run("List all teams available.", deps=deps)
        print(result.data)
    except Exception as e:
        print(f"Error: {e}")

    # Test 2: Interactive Mode
    print("\n--- Interactive Mode (type 'exit' to quit) ---")
    while True:
        user_input = input("\nUser: ")
        if user_input.lower() in ("exit", "quit"):
            break

        try:
            result = await linear_agent.run(user_input, deps=deps)
            print(f"Agent: {result.data}")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())
