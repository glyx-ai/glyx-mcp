#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored messages
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_info() {
    echo -e "${YELLOW}→${NC} $1"
}

echo "========================================="
echo "  glyx-mcp Installation Script"
echo "========================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

# Check Python version
python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    print_error "Python $required_version or higher is required. Found: $python_version"
    exit 1
fi

print_success "Python $python_version found"

# Install uv if not present
if ! command -v uv &> /dev/null; then
    print_info "uv not found. Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    print_success "uv installed"
else
    print_success "uv found"
fi

# Install Aider using the official installer
print_info "Installing Aider..."
if python3 -m pip install aider-install && aider-install; then
    print_success "Aider installed successfully"
else
    print_error "Failed to install Aider"
    exit 1
fi

# Install OpenCode CLI using uv
print_info "Installing OpenCode CLI with uv..."
if uv tool install opencode; then
    print_success "OpenCode CLI installed successfully"
else
    print_error "Failed to install OpenCode CLI"
    exit 1
fi

# Install glyx-mcp package
print_info "Installing glyx-mcp package..."
uv pip install -e .
print_success "glyx-mcp installed successfully"

echo ""
echo "========================================="
echo "  Installation Complete!"
echo "========================================="
echo ""
echo "Installed tools:"
echo "  • aider - AI coding assistant"
echo "  • opencode - Multi-provider AI CLI"
echo "  • glyx-mcp - FastMCP server for composable agents"
echo ""
echo "Next steps:"
echo "  1. Ensure uv's tool bin directory is in your PATH:"
echo "     export PATH=\"\$HOME/.local/bin:\$PATH\""
echo ""
echo "  2. Configure your API keys:"
echo "     • OpenRouter API key for Grok: export OPENROUTER_API_KEY=your_key"
echo "     • Or configure in ~/.config/opencode/config.yaml"
echo ""
echo "  3. Run the MCP server: glyx-mcp"
echo ""
echo "  4. Configure your MCP client to connect to glyx-mcp"
echo ""
echo "For more information, see README.md"
echo ""
