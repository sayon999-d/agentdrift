#!/usr/bin/env sh
# ==============================================================================
# AgentDrift Official Bootstrap Installer (macOS & Linux)
# Usage:
#   curl -fsSL https://agentdrift.io/install.sh | bash
#   or:
#   sh install.sh [OPTIONS]
# ==============================================================================

set -eu

# Terminal color formatting (respecting NO_COLOR)
setup_colors() {
  if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    COLOR_RESET="\033[0m"
    COLOR_BOLD="\033[1m"
    COLOR_DIM="\033[2m"
    COLOR_CYAN="\033[36m"
    COLOR_GREEN="\033[32m"
    COLOR_YELLOW="\033[33m"
    COLOR_RED="\033[31m"
    COLOR_MAGENTA="\033[35m"
  else
    COLOR_RESET=""
    COLOR_BOLD=""
    COLOR_DIM=""
    COLOR_CYAN=""
    COLOR_GREEN=""
    COLOR_YELLOW=""
    COLOR_RED=""
    COLOR_MAGENTA=""
  fi
}

info() {
  printf "${COLOR_CYAN}[info]${COLOR_RESET} %s\n" "$*"
}

step() {
  printf "${COLOR_BOLD}${COLOR_MAGENTA}==>${COLOR_RESET} ${COLOR_BOLD}%s${COLOR_RESET}\n" "$*"
}

success() {
  printf "${COLOR_GREEN}[ok]${COLOR_RESET} %s\n" "$*"
}

warn() {
  printf "${COLOR_YELLOW}[warn]${COLOR_RESET} %s\n" "$*" >&2
}

error() {
  printf "${COLOR_RED}[error]${COLOR_RESET} %s\n" "$*" >&2
  exit 1
}

print_banner() {
  printf "${COLOR_CYAN}"
  cat << 'EOF'
     ___                    __   ____       _  ______ 
    /   | ____ ____  ____  / /__/ __ \_____(_)/ __/ /_
   / /| |/ __ `/ _ \/ __ \/ __/ / / / ___/ / / /_/ __/
  / ___ / /_/ /  __/ / / / /_/ /_/ / /  / / / __/ /_  
 /_/  |_\__, /\___/_/ /_/\__/_____/_/  /_/_/_/  \__/  
       /____/                                         
EOF
  printf "${COLOR_RESET}"
  printf "${COLOR_DIM} Runtime supervisor and circuit breaker for autonomous coding agents${COLOR_RESET}\n\n"
}

usage() {
  cat << EOF
AgentDrift CLI Bootstrap Installer

USAGE:
    curl -fsSL https://agentdrift.io/install.sh | bash
    or:
    sh install.sh [OPTIONS]

OPTIONS:
    -v, --version <VERSION>     Install a specific version of AgentDrift (e.g. 0.1.0)
    -b, --bin-dir <PATH>        Directory where executable symlinks are placed (default: ~/.local/bin)
    -d, --install-dir <PATH>    Directory for the dedicated virtual environment (default: ~/.local/share/agentdrift)
        --no-modify-path        Do not attempt to update PATH in your shell configuration
    -f, --force                 Overwrite existing installation or virtual environment
        --dry-run               Simulate installation actions without executing changes
    -h, --help                  Show this help message and exit

ENVIRONMENT VARIABLES:
    AGENTDRIFT_VERSION          Equivalent to --version
    AGENTDRIFT_BIN_DIR          Equivalent to --bin-dir
    AGENTDRIFT_INSTALL_DIR      Equivalent to --install-dir
    AGENTDRIFT_NO_MODIFY_PATH   Set to 1 to disable modifying PATH
    AGENTDRIFT_FORCE            Set to 1 to force reinstallation
    NO_COLOR                    Set to 1 to disable colorized terminal output

EOF
}

detect_os_arch() {
  OS="$(uname -s)"
  ARCH="$(uname -m)"

  case "$OS" in
    Darwin)
      OS_NAME="macOS"
      ;;
    Linux)
      OS_NAME="Linux"
      ;;
    CYGWIN*|MINGW*|MSYS*)
      warn "Detected Windows POSIX emulation environment ($OS)."
      warn "For native Windows PowerShell installation, run:"
      warn "  irm https://agentdrift.io/install.ps1 | iex"
      OS_NAME="Windows-Emulated"
      ;;
    *)
      OS_NAME="$OS"
      ;;
  esac

  info "Detected platform: ${OS_NAME} (${ARCH})"
}

# Finds an eligible Python >= 3.12 interpreter
find_python() {
  for candidate in python3.13 python3.12 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY_VER="$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
      if [ -n "$PY_VER" ]; then
        MAJOR="$(echo "$PY_VER" | cut -d. -f1)"
        MINOR="$(echo "$PY_VER" | cut -d. -f2)"
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 12 ]; then
          PYTHON_CMD="$candidate"
          PYTHON_VERSION="$PY_VER"
          return 0
        fi
      fi
    fi
  done
  return 1
}

# Check if a directory is in PATH
path_contains() {
  case ":$PATH:" in
    *:"$1":*) return 0 ;;
    *) return 1 ;;
  esac
}

# Determine candidate shell config file
detect_shell_rc() {
  USER_SHELL="$(basename "${SHELL:-bash}")"
  case "$USER_SHELL" in
    zsh)
      echo "$HOME/.zshrc"
      ;;
    bash)
      if [ "$OS" = "Darwin" ] && [ -f "$HOME/.zprofile" ]; then
        echo "$HOME/.zprofile"
      elif [ -f "$HOME/.bashrc" ]; then
        echo "$HOME/.bashrc"
      elif [ -f "$HOME/.bash_profile" ]; then
        echo "$HOME/.bash_profile"
      else
        echo "$HOME/.profile"
      fi
      ;;
    fish)
      echo "$HOME/.config/fish/config.fish"
      ;;
    *)
      echo "$HOME/.profile"
      ;;
  esac
}

main() {
  setup_colors

  # Defaults
  VERSION="${AGENTDRIFT_VERSION:-}"
  BIN_DIR="${AGENTDRIFT_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
  INSTALL_DIR="${AGENTDRIFT_INSTALL_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/agentdrift}"
  NO_MODIFY_PATH="${AGENTDRIFT_NO_MODIFY_PATH:-0}"
  FORCE="${AGENTDRIFT_FORCE:-0}"
  DRY_RUN=0

  # Argument parsing
  while [ $# -gt 0 ]; do
    case "$1" in
      -v|--version)
        VERSION="$2"
        shift 2
        ;;
      -b|--bin-dir)
        BIN_DIR="$2"
        shift 2
        ;;
      -d|--install-dir)
        INSTALL_DIR="$2"
        shift 2
        ;;
      --no-modify-path)
        NO_MODIFY_PATH=1
        shift 1
        ;;
      -f|--force)
        FORCE=1
        shift 1
        ;;
      --dry-run)
        DRY_RUN=1
        shift 1
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        error "Unknown argument: $1. Run with --help for usage."
        ;;
    esac
  done

  print_banner
  detect_os_arch

  PKG_SPEC="agentdrift"
  if [ -n "$VERSION" ] && [ "$VERSION" != "latest" ]; then
    PKG_SPEC="agentdrift==$VERSION"
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    info "DRY-RUN mode enabled. No changes will be applied."
    info "Target package: $PKG_SPEC"
    info "Target bin directory: $BIN_DIR"
    info "Target install directory: $INSTALL_DIR"
    exit 0
  fi

  # Strategy 1: astral-sh/uv tool install (fastest, isolated)
  if command -v uv >/dev/null 2>&1; then
    step "Installing agentdrift CLI via 'uv tool'..."
    UV_FLAGS=""
    if [ "$FORCE" -eq 1 ]; then
      UV_FLAGS="--force"
    fi
    # shellcheck disable=SC2086
    if uv tool install $UV_FLAGS "$PKG_SPEC"; then
      success "Successfully installed $PKG_SPEC via uv!"
      INSTALL_METHOD="uv"
    else
      warn "'uv tool install' encountered an issue, falling back to isolated virtualenv..."
      INSTALL_METHOD=""
    fi
  # Strategy 2: pipx install (standard isolated CLI runner)
  elif command -v pipx >/dev/null 2>&1; then
    step "Installing agentdrift CLI via 'pipx'..."
    PIPX_FLAGS=""
    if [ "$FORCE" -eq 1 ]; then
      PIPX_FLAGS="--force"
    fi
    # shellcheck disable=SC2086
    if pipx install $PIPX_FLAGS "$PKG_SPEC"; then
      success "Successfully installed $PKG_SPEC via pipx!"
      INSTALL_METHOD="pipx"
    else
      warn "'pipx install' encountered an issue, falling back to isolated virtualenv..."
      INSTALL_METHOD=""
    fi
  else
    INSTALL_METHOD=""
  fi

  # Strategy 3: Dedicated isolated virtual environment fallback
  if [ -z "${INSTALL_METHOD:-}" ]; then
    step "Checking Python requirements..."
    if ! find_python; then
      printf "\n"
      error "AgentDrift requires Python >= 3.12.\n" \
            "No suitable Python 3.12+ interpreter was found in your PATH.\n\n" \
            "To install Python 3.12 or uv:\n" \
            "  - macOS:   brew install python@3.12   (or: brew install uv)\n" \
            "  - Ubuntu:  sudo apt install python3.12 python3.12-venv\n" \
            "  - Fedora:  sudo dnf install python3.12\n" \
            "  - Universal uv installer: curl -LsSf https://astral.sh/uv/install.sh | sh"
    fi

    info "Using Python interpreter: $PYTHON_CMD (v$PYTHON_VERSION)"

    # Verify venv module availability (e.g. Debian/Ubuntu python3-venv separation)
    if ! "$PYTHON_CMD" -m venv --help >/dev/null 2>&1; then
      error "Python interpreter $PYTHON_CMD lacks the 'venv' module.\n" \
            "On Debian/Ubuntu systems, run: sudo apt install python3-venv (or python3.12-venv)."
    fi

    VENV_DIR="$INSTALL_DIR/venv"
    if [ -d "$VENV_DIR" ]; then
      if [ "$FORCE" -eq 1 ]; then
        info "Overwriting existing virtualenv at $VENV_DIR..."
        rm -rf "$VENV_DIR"
      else
        info "Existing environment detected at $VENV_DIR (use --force to recreate)."
      fi
    fi

    step "Creating isolated virtual environment in $VENV_DIR..."
    mkdir -p "$INSTALL_DIR"
    "$PYTHON_CMD" -m venv "$VENV_DIR"

    step "Installing $PKG_SPEC into isolated environment..."
    "$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
    "$VENV_DIR/bin/python" -m pip install --quiet "$PKG_SPEC"

    step "Creating executable wrappers in $BIN_DIR..."
    mkdir -p "$BIN_DIR"

    for tool in agentdrift agentdrift-mcp; do
      if [ -f "$VENV_DIR/bin/$tool" ]; then
        WRAPPER="$BIN_DIR/$tool"
        cat << WRAPPER_EOF > "$WRAPPER"
#!/usr/bin/env sh
exec "$VENV_DIR/bin/$tool" "\$@"
WRAPPER_EOF
        chmod +x "$WRAPPER"
        success "Created wrapper: $WRAPPER"
      fi
    done
    INSTALL_METHOD="venv"
  fi

  # Verify PATH
  TARGET_CHECK_DIR="$BIN_DIR"
  if [ "$INSTALL_METHOD" = "uv" ]; then
    TARGET_CHECK_DIR="${XDG_BIN_HOME:-$HOME/.local/bin}"
  elif [ "$INSTALL_METHOD" = "pipx" ]; then
    TARGET_CHECK_DIR="${PIPX_BIN_DIR:-$HOME/.local/bin}"
  fi

  PATH_UPDATED=0
  if ! path_contains "$TARGET_CHECK_DIR"; then
    warn "$TARGET_CHECK_DIR is not currently in your PATH."
    SHELL_RC="$(detect_shell_rc)"

    if [ "$NO_MODIFY_PATH" -eq 0 ] && [ -w "$(dirname "$SHELL_RC")" ]; then
      EXPORT_LINE="export PATH=\"$TARGET_CHECK_DIR:\$PATH\""
      if [ -f "$SHELL_RC" ] && grep -Fqs "$TARGET_CHECK_DIR" "$SHELL_RC"; then
        info "PATH export already present in $SHELL_RC."
      else
        step "Appending PATH export to $SHELL_RC..."
        printf "\n# Added by AgentDrift installer\n%s\n" "$EXPORT_LINE" >> "$SHELL_RC"
        success "Updated $SHELL_RC with $TARGET_CHECK_DIR"
        PATH_UPDATED=1
      fi
    else
      warn "Add the following line to your shell profile manually:"
      warn "  export PATH=\"$TARGET_CHECK_DIR:\$PATH\""
    fi
  fi

  # Final Verification
  step "Verifying installation..."
  AGENTDRIFT_BIN="$TARGET_CHECK_DIR/agentdrift"
  if command -v agentdrift >/dev/null 2>&1; then
    AGENTDRIFT_BIN="$(command -v agentdrift)"
  fi

  if [ -x "$AGENTDRIFT_BIN" ] || command -v agentdrift >/dev/null 2>&1; then
    success "AgentDrift CLI installed successfully!"
  else
    warn "Executable installed at $AGENTDRIFT_BIN, but not found in active PATH."
  fi

  printf "\n"
  printf "${COLOR_BOLD}${COLOR_GREEN}✓ Installation complete!${COLOR_RESET}\n\n"
  printf "To verify and start using AgentDrift:\n"
  if [ "$PATH_UPDATED" -eq 1 ]; then
    printf "  ${COLOR_CYAN}source %s${COLOR_RESET}  # reload shell environment\n" "$SHELL_RC"
  fi
  printf "  ${COLOR_CYAN}agentdrift --help${COLOR_RESET}\n"
  printf "  ${COLOR_CYAN}agentdrift health${COLOR_RESET}     # check sentinel & daemon connectivity\n"
  printf "  ${COLOR_CYAN}agentdrift watch${COLOR_RESET}      # stream local agent executions\n\n"
}

# Trap signals for clean exit
trap 'echo "\nInstallation aborted." >&2; exit 1' INT TERM

# Execute main entry point
main "$@"
