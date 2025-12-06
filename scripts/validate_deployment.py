#!/usr/bin/env python3
"""Validate deployment configuration and readiness."""

import importlib.util
import os
import sys
from pathlib import Path

if importlib.util.find_spec("pydantic_settings") is None:
    print("❌ pydantic-settings not installed. Run: uv pip install pydantic-settings")
    sys.exit(1)


class Colors:
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    NC = "\033[0m"


def print_success(msg: str) -> None:
    print(f"{Colors.GREEN}✓{Colors.NC} {msg}")


def print_error(msg: str) -> None:
    print(f"{Colors.RED}✗{Colors.NC} {msg}")


def print_warning(msg: str) -> None:
    print(f"{Colors.YELLOW}⚠{Colors.NC} {msg}")


def print_info(msg: str) -> None:
    print(f"{Colors.BLUE}→{Colors.NC} {msg}")


def check_file_exists(filepath: str, required: bool = True) -> bool:
    """Check if a file exists."""
    path = Path(filepath)
    if path.exists():
        print_success(f"Found: {filepath}")
        return True
    elif required:
        print_error(f"Missing: {filepath}")
        return False
    else:
        print_warning(f"Optional file not found: {filepath}")
        return True


def check_env_vars(env_file: str) -> dict[str, bool]:
    """Check environment variables."""
    required_vars = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENROUTER_API_KEY",
    ]

    recommended_vars = [
        "JWT_SECRET_KEY",
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
    ]

    results: dict[str, bool] = {}

    if not Path(env_file).exists():
        print_error(f"Environment file not found: {env_file}")
        return {"file_exists": False}

    # Read env file
    env_vars: dict[str, str] = {}
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

    # Check required vars
    print_info("Checking required environment variables...")
    all_required_set = True
    for var in required_vars:
        if var in env_vars and env_vars[var]:
            print_success(f"{var} is set")
            results[var] = True
        else:
            print_error(f"{var} is not set or empty")
            results[var] = False
            all_required_set = False

    # Check recommended vars
    print_info("Checking recommended environment variables...")
    for var in recommended_vars:
        if var in env_vars and env_vars[var]:
            print_success(f"{var} is set")
            results[var] = True
        else:
            print_warning(f"{var} is not set (optional but recommended)")
            results[var] = False

    # Check JWT secret
    if "JWT_SECRET_KEY" in env_vars:
        if env_vars["JWT_SECRET_KEY"] == "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_STRING":
            print_error("JWT_SECRET_KEY must be changed from default!")
            results["jwt_secure"] = False
        elif len(env_vars["JWT_SECRET_KEY"]) < 32:
            print_warning("JWT_SECRET_KEY should be at least 32 characters")
            results["jwt_secure"] = False
        else:
            print_success("JWT_SECRET_KEY looks secure")
            results["jwt_secure"] = True

    results["all_required_set"] = all_required_set
    return results


def check_docker_files() -> bool:
    """Check Docker-related files."""
    print_info("Checking Docker configuration...")

    files_ok = True
    files_ok &= check_file_exists("Dockerfile")
    files_ok &= check_file_exists("compose.yml")
    files_ok &= check_file_exists("fly.toml")

    return files_ok


def check_agent_configs() -> bool:
    """Check agent configuration files."""
    print_info("Checking agent configurations...")

    agents_dir = Path("agents")
    if not agents_dir.exists():
        print_error("agents/ directory not found")
        return False

    agent_files = list(agents_dir.glob("*.json"))
    if not agent_files:
        print_error("No agent configuration files found in agents/")
        return False

    print_success(f"Found {len(agent_files)} agent configurations:")
    for agent_file in sorted(agent_files):
        print(f"  - {agent_file.name}")

    return True


def check_scripts() -> bool:
    """Check deployment scripts."""
    print_info("Checking deployment scripts...")

    scripts_ok = True
    scripts_ok &= check_file_exists("deploy.sh")
    scripts_ok &= check_file_exists("install.sh")

    # Check if scripts are executable
    for script in ["deploy.sh", "install.sh"]:
        path = Path(script)
        if path.exists():
            if os.access(path, os.X_OK):
                print_success(f"{script} is executable")
            else:
                print_warning(f"{script} is not executable (run: chmod +x {script})")

    return scripts_ok


def main() -> None:
    """Run all validation checks."""
    print("=" * 60)
    print("  glyx-mcp Deployment Validation")
    print("=" * 60)
    print()

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    all_checks_passed = True

    # Check files
    print("\n📁 File Structure Checks")
    print("-" * 60)
    all_checks_passed &= check_docker_files()
    all_checks_passed &= check_agent_configs()
    all_checks_passed &= check_scripts()

    # Check documentation
    print("\n📚 Documentation Checks")
    print("-" * 60)
    check_file_exists("README.md")
    check_file_exists("QUICKSTART.md")
    check_file_exists("docs/DEPLOYMENT.md")
    check_file_exists("AGENTS.md")

    # Check environment
    print("\n🔐 Environment Configuration")
    print("-" * 60)

    # Check for .env file
    if Path(".env").exists():
        env_results = check_env_vars(".env")
        if not env_results.get("all_required_set", False):
            print_warning("Development .env file incomplete")
    else:
        print_warning(".env file not found (create from .env.example)")

    # Check for .env.production
    if Path(".env.production").exists():
        print()
        print_info("Checking production environment...")
        prod_env_results = check_env_vars(".env.production")
        if not prod_env_results.get("all_required_set", False):
            print_error("Production environment is not ready!")
            all_checks_passed = False
    else:
        print_warning(".env.production not found (required for deployment)")

    # Summary
    print("\n" + "=" * 60)
    if all_checks_passed:
        print_success("All critical checks passed! ✨")
        print()
        print("Next steps:")
        print("  1. Review and set environment variables in .env.production")
        print("  2. Test locally: docker compose up")
        print("  3. Deploy to production: ./deploy.sh")
    else:
        print_error("Some checks failed. Please fix issues before deploying.")
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    main()
