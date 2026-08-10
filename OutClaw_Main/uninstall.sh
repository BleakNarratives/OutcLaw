#!/bin/bash
# uninstall.sh — Removes the OutClaw desktop/app icons (not OutClaw itself)
#
# Run it with one command:
#     bash uninstall.sh
#
# What it removes:
#   • the OutClaw entry in your app menu
#   • the OutClaw shortcut on your desktop
#   • the OutClaw icon picture
#   • the one-tap button on Android (Termux:Widget)
#
# What it does NOT remove (this is intentional and safe):
#   • the OutClaw program itself  — you keep using it from the terminal
#   • your papers and your audit history
#   • anything else on your computer

set -u

cd "$(dirname "$0")" || exit 1

if [ -t 1 ]; then
  GREEN=$'\033[32m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
else
  GREEN=""; CYAN=""; YELLOW=""; BOLD=""; DIM=""; RESET=""
fi

say()  { printf '%s\n' "  $*"; }
ok()   { printf '%s\n' "${GREEN}  ✓ $*${RESET}"; }
note() { printf '%s\n' "${YELLOW}  → $*${RESET}"; }
head() { printf '%s\n' "${CYAN}${BOLD}  $*${RESET}"; }

echo ""
head "══════════════════════════════════════════════════════"
head "  OUTCLAW — remove the desktop icon"
head "══════════════════════════════════════════════════════"
echo ""

# ── Ask for confirmation (this is the only thing it removes) ──────────────
read -r -p "  Remove the OutClaw app/desktop icons? [y/N] " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
  say "  Nothing was changed. OK."
  echo ""
  exit 0
fi

APP_DESKTOP="${HOME}/.local/share/applications/outclaw.desktop"
ICON_SVG="${HOME}/.local/share/icons/hicolor/scalable/apps/outclaw.svg"

# Desktop shortcut — could be in ~/Desktop or the system's Desktop folder
DESKTOP_DIR="${HOME}/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
fi
DESKTOP_SHORTCUT="${DESKTOP_DIR}/OutClaw.desktop"

REMOVED_ANY=false

if [ -f "$APP_DESKTOP" ]; then
  rm -f "$APP_DESKTOP"
  ok "Removed app-menu entry."
  REMOVED_ANY=true
fi

if [ -f "$DESKTOP_SHORTCUT" ]; then
  rm -f "$DESKTOP_SHORTCUT"
  ok "Removed desktop shortcut."
  REMOVED_ANY=true
fi

if [ -f "$ICON_SVG" ]; then
  rm -f "$ICON_SVG"
  ok "Removed icon picture."
  REMOVED_ANY=true
fi

# Termux one-tap button (Android)
if [ -f "${HOME}/.shortcuts/OutClaw" ]; then
  rm -f "${HOME}/.shortcuts/OutClaw"
  ok "Removed the Android one-tap button."
  REMOVED_ANY=true
fi

# Refresh the app menu + icon cache so the icons disappear immediately
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${HOME}/.local/share/applications" >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -q "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

echo ""
if [ "$REMOVED_ANY" = true ]; then
  head "══════════════════════════════════════════════════════"
  head "  ✓ DONE — the OutClaw icons are gone"
  head "══════════════════════════════════════════════════════"
  say  ""
  say  "OutClaw itself is still here. You can still run it anytime:"
  say  "${BOLD}    python3 LAUNCH_ME.py${RESET}"
  say  ""
  say  "To put the icons back, run:  ${BOLD}bash install.sh${RESET}"
else
  note "Nothing to remove — no OutClaw icons were found."
  say  ""
  say  "OutClaw itself is still here. To create the icons, run:"
  say  "${BOLD}    bash install.sh${RESET}"
fi
echo ""
