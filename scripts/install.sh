#!/bin/sh
# Install only this checkout's isolated runtime. Host registration is separate.
set -eu

case "${1:-}" in
    --help|-h)
        printf '%s\n' 'Usage: sh scripts/install.sh [--dev]' \
            'Installs pinned uv, Python and locked dependencies inside this checkout.' \
            'Does not change shell profiles, MCP registration or macOS permissions.'
        exit 0 ;;
    --dev) MCP_SYNC_MODE=--dev ;;
    '') MCP_SYNC_MODE=--no-dev ;;
    *) printf '%s\n' 'Unknown option. Use --help.' >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Too many arguments. Use --help.' >&2
    exit 2
fi
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    printf '%s\n' 'This release requires Apple Silicon macOS. See INSTALL.md.' >&2
    exit 1
fi
if ! xcrun --find clang >/dev/null 2>&1; then
    printf '%s\n' "Install Apple's Command Line Tools with: xcode-select --install" \
        'Finish the system installer, then run this script again.' >&2
    exit 1
fi

MCP_PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)
cd "$MCP_PROJECT_DIR"
if [ ! -f uv.lock ] || [ ! -f pyproject.toml ]; then
    printf '%s\n' 'Run this script from an intact macos-personal-mcp checkout.' >&2
    exit 1
fi
umask 077
mkdir -p .local
MCP_INSTALLER=''
trap '[ -z "$MCP_INSTALLER" ] || rm -f "$MCP_INSTALLER"' 0
MCP_UV="$MCP_PROJECT_DIR/.local/uv/bin/uv"
MCP_UV_READY=false
if [ -x "$MCP_UV" ]; then
    case "$("$MCP_UV" --version)" in
        'uv 0.13.5'|'uv 0.13.5 '*) MCP_UV_READY=true ;;
    esac
fi
if [ "$MCP_UV_READY" = false ]; then
    MCP_INSTALLER=$(mktemp "$MCP_PROJECT_DIR/.local/uv-installer.XXXXXX")
    printf '%s\n' 'Installing project-local uv 0.13.5…'
    curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
        https://astral.sh/uv/0.13.5/install.sh --output "$MCP_INSTALLER"
    UV_UNMANAGED_INSTALL="$MCP_PROJECT_DIR/.local/uv/bin" sh "$MCP_INSTALLER"
    rm -f "$MCP_INSTALLER"
    MCP_INSTALLER=''
fi

# Some Python 3.15 dependency wheels are not published for this target yet.
# Supply their build compiler locally when the Mac has no usable Rust compiler.
if ! cargo --version >/dev/null 2>&1 || ! rustc --version >/dev/null 2>&1; then
    export CARGO_HOME="$MCP_PROJECT_DIR/.local/cargo"
    export RUSTUP_HOME="$MCP_PROJECT_DIR/.local/rustup"
    export RUSTUP_TOOLCHAIN=1.99.1
    export PATH="$CARGO_HOME/bin:$PATH"
    if ! cargo --version >/dev/null 2>&1 || ! rustc --version >/dev/null 2>&1; then
        MCP_INSTALLER=$(mktemp "$MCP_PROJECT_DIR/.local/rustup-installer.XXXXXX")
        printf '%s\n' 'Installing project-local Rust 1.99.1 for dependency builds…'
        curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
            https://sh.rustup.rs --output "$MCP_INSTALLER"
        sh "$MCP_INSTALLER" -y --profile minimal --no-modify-path --default-toolchain 1.99.1
        rm -f "$MCP_INSTALLER"
        MCP_INSTALLER=''
    fi
fi

# Keep both managed interpreters and executables local, including during first
# installation. These variables affect this script's children, not the shell.
export UV_PYTHON_INSTALL_DIR="$MCP_PROJECT_DIR/.local/python"
export UV_PYTHON_BIN_DIR="$MCP_PROJECT_DIR/.local/python-bin"
export UV_PYTHON_INSTALL_BIN=0
export UV_PROJECT_ENVIRONMENT="$MCP_PROJECT_DIR/.venv"
export UV_CACHE_DIR="$MCP_PROJECT_DIR/.local/uv-cache"
"$MCP_UV" python install --no-bin 3.15.1
"$MCP_UV" sync --locked --managed-python --python 3.15.1 "$MCP_SYNC_MODE"

"$MCP_PROJECT_DIR/.venv/bin/python" - "$MCP_PROJECT_DIR" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
command = str(root / ".venv/bin/macos-personal-mcp")
snippet = (
    '[mcp_servers.macos-personal]\n'
    'enabled = true\n'
    f'command = {json.dumps(command, ensure_ascii=False)}\n'
    'args = ["serve", "--read-only"]\n'
    'startup_timeout_sec = 10\n'
    'tool_timeout_sec = 240\n'
    'default_tools_approval_mode = "writes"\n'
)
target = root / ".local/chatgpt-mcp.toml"
target.write_text(snippet)
target.chmod(0o600)
print("\nRuntime installed. Connect it in ChatGPT → Settings → MCP servers:")
print("  Name: macos-personal")
print("  Transport: STDIO")
print("  Command: " + command)
print("  Arguments: serve --read-only")
print("  Tool timeout: 240 seconds (if offered)")
print("\nOr merge this one server table into the local host configuration:")
print(str(target))
print("\nSave and restart that MCP connection, then follow INSTALL.md → Verify.")
PY
