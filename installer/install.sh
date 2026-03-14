#!/bin/bash
# Lead Machine — Bootstrap installer
# Handles: Homebrew (macOS), Python 3.11+, then hands off to wizard.py
set -e

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
UNAME="$(uname -s 2>/dev/null || echo Windows)"

_green()  { printf '\033[92m✓\033[0m  %s\n' "$1"; }
_yellow() { printf '\033[93m⚠\033[0m  %s\n' "$1"; }
_blue()   { printf '\033[94mℹ\033[0m  %s\n' "$1"; }
_red()    { printf '\033[91m✗\033[0m  %s\n' "$1"; }

echo ""
echo "  ██╗     ███╗   ███╗  "
echo "  ██║     ████╗ ████║  Lead Machine"
echo "  ██║     ██╔████╔██║  Bootstrap v2.0"
echo "  ██║     ██║╚██╔╝██║  "
echo "  ███████╗██║ ╚═╝ ██║  "
echo "  ╚══════╝╚═╝     ╚═╝  "
echo ""
echo "  ╔══════════════════════════════════════════════════════╗"
echo "  ║  Estimated time on a fresh machine: 15–20 minutes   ║"
echo "  ╚══════════════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# macOS bootstrap
# ─────────────────────────────────────────────────────────────────────────────
if [ "$UNAME" = "Darwin" ]; then

    # ── Step 0a: Homebrew ────────────────────────────────────────────────────
    if ! command -v brew &>/dev/null; then
        _yellow "Homebrew not found — installing now (5–10 min)."
        echo ""
        echo "  ┌─────────────────────────────────────────────────────────┐"
        echo "  │  A macOS system dialog may appear asking to install     │"
        echo "  │  Xcode Command Line Tools.  Click 'Install' to proceed. │"
        echo "  └─────────────────────────────────────────────────────────┘"
        echo ""
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

        # Add Homebrew to PATH for this session
        if   [ -f /opt/homebrew/bin/brew ];  then eval "$(/opt/homebrew/bin/brew shellenv)"
        elif [ -f /usr/local/bin/brew ];     then eval "$(/usr/local/bin/brew shellenv)"
        fi
        _green "Homebrew installed."
    else
        eval "$(brew shellenv 2>/dev/null || true)"
        _green "Homebrew already present."
    fi

    # ── Step 0b: Python 3.11+ ────────────────────────────────────────────────
    PYTHON=""
    for _p in python3.13 python3.12 python3.11; do
        if command -v "$_p" &>/dev/null; then
            if "$_p" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null; then
                PYTHON="$_p"; break
            fi
        fi
    done

    # Try Homebrew explicit paths if not found in PATH yet
    if [ -z "$PYTHON" ]; then
        for _p in \
            /opt/homebrew/bin/python3.13 \
            /opt/homebrew/bin/python3.12 \
            /opt/homebrew/bin/python3.11 \
            /usr/local/bin/python3.13 \
            /usr/local/bin/python3.12 \
            /usr/local/bin/python3.11 \
            "$(brew --prefix python@3.11 2>/dev/null)/bin/python3.11"
        do
            if [ -f "$_p" ] && "$_p" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null; then
                PYTHON="$_p"; break
            fi
        done
    fi

    if [ -z "$PYTHON" ]; then
        _yellow "Python 3.11+ not found — installing via Homebrew…"
        brew install python@3.11
        # Re-scan
        for _p in \
            "$(brew --prefix python@3.11 2>/dev/null)/bin/python3.11" \
            /opt/homebrew/bin/python3.11 \
            /usr/local/bin/python3.11
        do
            if [ -f "$_p" ]; then PYTHON="$_p"; break; fi
        done
        # Final fallback
        [ -z "$PYTHON" ] && PYTHON="$(brew --prefix)/bin/python3.11"
        _green "Python 3.11 installed."
    fi

# ─────────────────────────────────────────────────────────────────────────────
# Linux bootstrap
# ─────────────────────────────────────────────────────────────────────────────
elif [ "$UNAME" = "Linux" ]; then
    PYTHON=""
    for _p in python3.13 python3.12 python3.11; do
        if command -v "$_p" &>/dev/null; then
            if "$_p" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null; then
                PYTHON="$_p"; break
            fi
        fi
    done

    if [ -z "$PYTHON" ]; then
        _yellow "Python 3.11+ not found — installing via apt…"
        sudo apt-get update -qq
        sudo apt-get install -y python3.11 python3.11-venv python3-pip
        PYTHON="python3.11"
        _green "Python 3.11 installed."
    fi

# ─────────────────────────────────────────────────────────────────────────────
# Fallback (WSL, etc.)
# ─────────────────────────────────────────────────────────────────────────────
else
    PYTHON="python3"
fi

# ─────────────────────────────────────────────────────────────────────────────
# Verify we have a good Python
# ─────────────────────────────────────────────────────────────────────────────
if ! "$PYTHON" -c "import sys; sys.exit(0 if sys.version_info>=(3,11) else 1)" 2>/dev/null; then
    _red "Python 3.11+ is required but was not found or could not be installed."
    echo ""
    echo "  Found: $("$PYTHON" --version 2>&1)"
    echo ""
    echo "  macOS:  brew install python@3.11"
    echo "  Ubuntu: sudo apt-get install python3.11"
    echo "  Any:    https://www.python.org/downloads/"
    exit 1
fi

_green "Using Python: $("$PYTHON" --version 2>&1) at $PYTHON"
echo ""

# ─────────────────────────────────────────────────────────────────────────────
# Hand off to the wizard
# ─────────────────────────────────────────────────────────────────────────────
exec "$PYTHON" "$ROOT/installer/wizard.py" "$@"
