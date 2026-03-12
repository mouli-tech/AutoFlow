#!/usr/bin/env bash
# AutoFlow Installer — https://github.com/mouli-tech/AutoFlow
# Usage: curl -fsSL https://mouli-tech.github.io/AutoFlow/install.sh | bash

set -euo pipefail

AUTOFLOW_HOME="${HOME}/.local/share/autoflow"
AUTOFLOW_BIN="${HOME}/.local/bin"
REPO_URL="https://github.com/mouli-tech/AutoFlow.git"
MIN_PYTHON="3.9"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $1"; }
ok()    { echo -e "${GREEN}[  ok]${NC}  $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $1"; }
fail()  { echo -e "${RED}[fail]${NC}  $1"; exit 1; }

echo ""
echo -e "${PURPLE}${BOLD}  ⚡ AutoFlow Installer${NC}"
echo -e "  ${CYAN}Workflow automation for Linux${NC}"
echo ""

# --- Check OS ---
if [[ "$(uname -s)" != "Linux" ]]; then
    fail "AutoFlow currently only supports Linux."
fi

# --- Check Python ---
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        version=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || true)
        if [[ -n "$version" ]]; then
            major=$(echo "$version" | cut -d. -f1)
            minor=$(echo "$version" | cut -d. -f2)
            if [[ "$major" -ge 3 && "$minor" -ge 9 ]]; then
                PYTHON="$cmd"
                ok "Found $cmd ($version)"
                break
            fi
        fi
    fi
done

if [[ -z "$PYTHON" ]]; then
    warn "Python ${MIN_PYTHON}+ not found. Attempting to install..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y python3 python3-pip
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm python python-pip
    else
        fail "Could not install Python automatically. Please install Python ${MIN_PYTHON}+ and retry."
    fi
    PYTHON="python3"
    ok "Python installed"
fi

# --- Check pip & venv ---
"$PYTHON" -m pip --version &>/dev/null || {
    warn "pip not found. Installing..."
    "$PYTHON" -m ensurepip --upgrade 2>/dev/null || sudo apt-get install -y python3-pip 2>/dev/null || fail "Could not install pip."
}

"$PYTHON" -c "import venv" 2>/dev/null || {
    warn "venv module not found. Installing..."
    sudo apt-get install -y python3-venv 2>/dev/null || fail "Could not install python3-venv."
}

# --- Install AutoFlow ---
info "Installing AutoFlow to ${AUTOFLOW_HOME}..."

# Create directory
mkdir -p "$AUTOFLOW_HOME"
mkdir -p "$AUTOFLOW_BIN"

# Clone or update
if [[ -d "${AUTOFLOW_HOME}/repo" ]]; then
    info "Updating existing installation..."
    cd "${AUTOFLOW_HOME}/repo"
    git pull --quiet origin main
else
    info "Downloading AutoFlow..."
    git clone --quiet --depth 1 "$REPO_URL" "${AUTOFLOW_HOME}/repo"
fi

# Create virtual environment
if [[ ! -d "${AUTOFLOW_HOME}/venv" ]]; then
    info "Creating virtual environment..."
    "$PYTHON" -m venv "${AUTOFLOW_HOME}/venv"
fi

# Install into venv
info "Installing dependencies..."
"${AUTOFLOW_HOME}/venv/bin/pip" install --quiet --upgrade pip
"${AUTOFLOW_HOME}/venv/bin/pip" install --quiet -e "${AUTOFLOW_HOME}/repo"

# Create symlink
ln -sf "${AUTOFLOW_HOME}/venv/bin/autoflow" "${AUTOFLOW_BIN}/autoflow"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${AUTOFLOW_BIN}:"* ]]; then
    warn "${AUTOFLOW_BIN} is not in your PATH."
    for rc in "${HOME}/.bashrc" "${HOME}/.zshrc"; do
        if [[ -f "$rc" ]]; then
            echo 'export PATH="${HOME}/.local/bin:${PATH}"' >> "$rc"
            info "Added to $rc — restart your shell or run: source $rc"
        fi
    done
fi

echo ""
echo -e "${GREEN}${BOLD}  ✅ AutoFlow installed successfully!${NC}"
echo ""
echo -e "  Run ${CYAN}autoflow start${NC} to launch the dashboard"
echo -e "  Run ${CYAN}autoflow list${NC} to see your workflows"
echo -e "  Run ${CYAN}autoflow --help${NC} for all commands"
echo ""
echo -e "  ${PURPLE}Docs: ${NC}https://github.com/mouli-tech/AutoFlow"
echo ""
