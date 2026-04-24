#!/usr/bin/env bash
# install.sh — slow-ai setup
# Run from the root of the repository after cloning.
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# colours
# ──────────────────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  RED='\033[0;31m' GRN='\033[0;32m' YLW='\033[1;33m'
  BLU='\033[0;34m' PRP='\033[0;35m' CYN='\033[0;36m'
  BLD='\033[1m'    DIM='\033[2m'    NC='\033[0m'
else
  RED='' GRN='' YLW='' BLU='' PRP='' CYN='' BLD='' DIM='' NC=''
fi

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────
ok()   { printf "${GRN}  ✓${NC}  %s\n"     "$*"; }
info() { printf "${BLU}  →${NC}  %s\n"     "$*"; }
warn() { printf "${YLW}  ⚠${NC}  %s\n"     "$*"; }
die()  { printf "${RED}  ✗${NC}  %s\n" "$*" >&2; exit 1; }
dim()  { printf "     ${DIM}%s${NC}\n"      "$*"; }
sep()  { printf "\n${PRP}${BLD}  ─── %s ${NC}\n\n" "$*"; }

# ──────────────────────────────────────────────────────────────────────────────
# spinner
# ──────────────────────────────────────────────────────────────────────────────
_spin_pid=
_spin_msg=

spin_start() {
  _spin_msg="$1"
  printf "  ${BLU}◌${NC}  %s" "$_spin_msg"
  (
    frames=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')
    while true; do
      for f in "${frames[@]}"; do
        printf "\r  ${BLU}%s${NC}  %s   " "$f" "$_spin_msg"
        sleep 0.08
      done
    done
  ) &
  _spin_pid=$!
}

spin_ok() {
  [[ -n "$_spin_pid" ]] && kill "$_spin_pid" 2>/dev/null && wait "$_spin_pid" 2>/dev/null
  _spin_pid=
  printf "\r${GRN}  ✓${NC}  %-55s\n" "$1"
}

spin_err() {
  [[ -n "$_spin_pid" ]] && kill "$_spin_pid" 2>/dev/null && wait "$_spin_pid" 2>/dev/null
  _spin_pid=
  printf "\r${RED}  ✗${NC}  %-55s\n" "$1"
}

_cleanup() {
  [[ -n "${_spin_pid:-}" ]] && kill "$_spin_pid" 2>/dev/null
  printf "${NC}"
}
trap '_cleanup; echo' EXIT
trap '_cleanup; printf "\n"; warn "Interrupted."; exit 130' INT TERM

# ──────────────────────────────────────────────────────────────────────────────
# logo
# ──────────────────────────────────────────────────────────────────────────────
print_logo() {
  printf "\n${PRP}${BLD}"
  printf " ██████  ██       ██████  ██     ██      █████  ██\n"
  printf "██        ██      ██    ██ ██     ██    ██   ██  ██\n"
  printf " █████    ██      ██    ██ ██  █  ██    ███████  ██\n"
  printf "     ██   ██      ██    ██ ██ ███ ██    ██   ██  ██\n"
  printf " ██████   ███████  ██████   ███ ███     ██   ██  ██\n"
  printf "${NC}"
  printf "\n  ${DIM}agentic work orchestration · built like a distributed system${NC}\n"
}

# ──────────────────────────────────────────────────────────────────────────────
# step 1 — sanity checks
# ──────────────────────────────────────────────────────────────────────────────
check_location() {
  [[ -f "pyproject.toml" && -f "main.py" ]] || \
    die "Run this script from the root of the slow-ai repository."
  ok "Repository root confirmed"
}

check_python() {
  command -v python3 &>/dev/null || \
    die "Python 3 not found. Install Python 3.11+ and try again."

  local maj min ver
  maj=$(python3 -c 'import sys; print(sys.version_info.major)')
  min=$(python3 -c 'import sys; print(sys.version_info.minor)')
  ver=$(python3 -c 'import sys; v=sys.version_info; print(f"{v.major}.{v.minor}.{v.micro}")')

  if [[ "$maj" -lt 3 || ( "$maj" -eq 3 && "$min" -lt 11 ) ]]; then
    die "Python 3.11+ required. Found $ver — please upgrade and try again."
  fi

  ok "Python $ver"
}

# ──────────────────────────────────────────────────────────────────────────────
# step 2 — uv
# ──────────────────────────────────────────────────────────────────────────────
install_uv() {
  if command -v uv &>/dev/null; then
    ok "uv $(uv --version | awk '{print $2}') already installed"
    return
  fi

  spin_start "Installing uv"

  if command -v curl &>/dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh &>/dev/null
  elif command -v pip3 &>/dev/null; then
    pip3 install -q uv
  elif command -v pip &>/dev/null; then
    pip install -q uv
  else
    spin_err "Could not install uv"
    die "No curl or pip found. Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
  fi

  # uv installs to ~/.local/bin — make sure it's on PATH for this session
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

  if ! command -v uv &>/dev/null; then
    spin_err "uv installed but not found in PATH"
    die "Open a new shell and re-run this script, or add ~/.local/bin to your PATH."
  fi

  spin_ok "uv $(uv --version | awk '{print $2}') installed"
}

# ──────────────────────────────────────────────────────────────────────────────
# step 3 — dependencies
# ──────────────────────────────────────────────────────────────────────────────
sync_deps() {
  spin_start "Installing dependencies via uv sync"
  uv sync --quiet 2>&1 | tail -1 >/dev/null || true
  spin_ok "Dependencies installed"
}

# ──────────────────────────────────────────────────────────────────────────────
# step 4 — api keys
# ──────────────────────────────────────────────────────────────────────────────
ask_key() {
  local label="$1" varname="$2" hint="$3"
  printf "\n  ${BLD}${CYN}%s${NC}\n" "$label"
  dim "$hint"
  printf "  ${DIM}Press Enter to skip — you can add it to .env later.${NC}\n"
  printf "  ${CYN}›${NC} "
  local val=""
  IFS= read -r -s val || true
  echo
  if [[ -n "$val" ]]; then
    ok "$label configured"
  else
    warn "$label skipped"
  fi
  printf -v "$varname" '%s' "$val"
}

configure_env() {
  if [[ -f ".env" ]]; then
    # Only skip if both keys are already present and non-empty
    local existing_gemini existing_perplexity
    existing_gemini=$(grep -E '^GEMINI_API_KEY=.+' .env || true)
    existing_perplexity=$(grep -E '^PERPLEXITY_KEY=.+' .env || true)
    if [[ -n "$existing_gemini" && -n "$existing_perplexity" ]]; then
      ok ".env already configured — skipping"
      dim "To reconfigure, delete .env and re-run this script."
      return
    fi
    # Keys missing or empty — ask whether to update
    printf "\n  ${YLW}⚠${NC}  ${BLD}.env exists but one or more keys are missing.${NC}\n"
    printf "  Add missing keys now? ${DIM}[Y/n]${NC} "
    local yn=""
    read -r yn || true
    if [[ "$yn" =~ ^[Nn]$ ]]; then
      info "Keeping existing .env"
      return
    fi
  fi

  local GEMINI_KEY="" PERPLEXITY_KEY=""

  ask_key \
    "Gemini API Key" \
    GEMINI_KEY \
    "Get yours → aistudio.google.com/app/apikey"

  ask_key \
    "Perplexity API Key" \
    PERPLEXITY_KEY \
    "Get yours → perplexity.ai/settings/api"

  printf 'GEMINI_API_KEY=%s\nPERPLEXITY_KEY=%s\n' \
    "$GEMINI_KEY" "$PERPLEXITY_KEY" > .env

  ok ".env written"
  dim "Keys are stored locally and never leave your machine."
}

# ──────────────────────────────────────────────────────────────────────────────
# done
# ──────────────────────────────────────────────────────────────────────────────
print_done() {
  printf "\n${PRP}${BLD}"
  printf "  ╔══════════════════════════════════════════════════════════╗\n"
  printf "  ║                     you're ready                        ║\n"
  printf "  ╚══════════════════════════════════════════════════════════╝${NC}\n"
  printf "\n"
  printf "  ${BLD}Run the app${NC}\n"
  printf "  ${CYN}  uv run streamlit run main.py${NC}\n"
  printf "\n"
  printf "  ${BLD}Bring your own models${NC}   ${DIM}src/slow_ai/llm/registry.json${NC}\n"
  printf "  ${BLD}Add or edit skills${NC}      ${DIM}src/slow_ai/skills/catalog/${NC}\n"
  printf "  ${BLD}Edit API keys${NC}           ${DIM}.env${NC}\n"
  printf "\n"
  printf "  ${DIM}Trust no node. Trust is built. Trust is designed.${NC}\n"
  printf "\n"
}

# ──────────────────────────────────────────────────────────────────────────────
# main
# ──────────────────────────────────────────────────────────────────────────────
main() {
  print_logo

  sep "1 / 4  Environment"
  check_location
  check_python

  sep "2 / 4  uv"
  install_uv

  sep "3 / 4  Dependencies"
  sync_deps

  sep "4 / 4  API Keys"
  configure_env

  print_done
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"
