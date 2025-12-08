import asyncio
import argparse
from framework.lifecycle import FeatureLifecycle


async def main():
    parser = argparse.ArgumentParser(description="Feature Management Framework CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start Feature
    start_parser = subparsers.add_parser("start", help="Start a new feature")
    start_parser.add_argument("name", help="Name of the feature")
    start_parser.add_argument("--team-id", help="Linear Team ID (optional)")

    # Plan Template
    plan_parser = subparsers.add_parser("plan", help="Generate implementation plan")
    plan_parser.add_argument("name", help="Name of the feature")

    args = parser.parse_args()
    lifecycle = FeatureLifecycle()

    if args.command == "start":
        result = await lifecycle.start_feature(args.name, args.team_id)
        print(result)
    elif args.command == "plan":
        result = await lifecycle.generate_plan_template(args.name)
        print(result)
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
