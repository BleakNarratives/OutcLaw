#!/bin/bash
# install.sh — Puts OutClaw on your desktop (Linux & Chromebook)
#
# Run it with one double-click or one command:
#     bash install.sh
#
# What it does:
#   1. Makes the launcher files runnable.
#   2. Adds an OutClaw icon to your app menu (and desktop, if you have one).
#   3. Explains what to do next — in plain words.
#
# It is safe to run more than once. Nothing is removed.

set -u

cd "$(dirname "$0")" || exit 1

# ── Colors (only when the terminal can show them) ──────────────────────────
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

# ── Where are we? ──────────────────────────────────────────────────────────
INSTALL_DIR="$(pwd)"
INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"   # make sure it is absolute

# ── What kind of machine is this? ──────────────────────────────────────────
PLATFORM="linux"
if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then
  PLATFORM="termux"
elif [ -n "${SOMMELIER_VERSION:-}" ] || [ -d "/opt/google/cros-containers" ]; then
  PLATFORM="chromebook"
fi

# ── Android (Termux): no desktop, but we can make a one-tap button ───────
if [ "$PLATFORM" = "termux" ]; then
  head "══════════════════════════════════════════════════════"
  head "  OUTCLAW — set up your one-tap button"
  head "══════════════════════════════════════════════════════"
  echo ""

  # Warn if the folder is still inside Downloads (common first landing spot
  # on Android). The baked-in path will break if the user moves OutClaw later.
  if echo "${INSTALL_DIR}" | grep -qi '/storage/emulated/0/Download' || \
     echo "${INSTALL_DIR}" | grep -qi '/storage/downloads' || \
     echo "${INSTALL_DIR}" | grep -qi '/sdcard/Download'; then
    note "It looks like OutClaw is still inside your Downloads folder."
    say  "If you move the OutClaw folder somewhere else later, the one-tap"
    say  "button on your home screen will stop working. (The button has the"
    say  "current location baked into it.)"
    say  ""
    say  "Two ways to handle this:"
    say  "  1. ${BOLD}Best:${RESET} Move the OutClaw folder somewhere permanent first, then"
    say  "     go inside it and run this installer again."
    say  "     Example: move it inside ~/storage/shared/OutClaw"
    say  "  2. ${BOLD}Easy:${RESET} Run it now anyway, and just run the installer again if"
    say  "     you move OutClaw later. The button is recreated in one second."
    say  ""
  fi

  # Make the launcher runnable
  chmod +x LAUNCH_ME.py 2>/dev/null

  # Create the Termux:Widget shortcut file with the real folder path baked in
  SHORTCUTS_DIR="${HOME}/.shortcuts"
  mkdir -p "$SHORTCUTS_DIR"
  cat > "$SHORTCUTS_DIR/OutClaw" << EOF
#!/data/data/com.termux/files/usr/bin/bash
# OutClaw one-tap launcher (created by install.sh)
cd "${INSTALL_DIR}" && exec python3 LAUNCH_ME.py
EOF
  chmod +x "$SHORTCUTS_DIR/OutClaw" 2>/dev/null
  ok "One-tap button file created: ~/.shortcuts/OutClaw"
  echo ""

  say  "To put the button on your home screen:"
  say  "  1. Install the free app ${BOLD}Termux:Widget${RESET} from F-Droid."
  say  "  2. Long-press your home screen → Widgets → Termux:Widget."
  say  "  3. Choose the ${BOLD}OutClaw${RESET} button."
  say  ""
  say  "You can also start OutClaw right now with one command:"
  say  "${BOLD}    cd "${INSTALL_DIR}" && python3 LAUNCH_ME.py${RESET}"
  say  ""
  say  "Then open your browser and go to:  ${BOLD}http://localhost:8765${RESET}"
  say  ""
  say  "Full phone/tablet steps are in INSTALL_GUIDE.md."
  echo ""
  exit 0
fi

echo ""
head "══════════════════════════════════════════════════════"
head "  OUTCLAW — set up your desktop icon"
head "══════════════════════════════════════════════════════"
echo ""

# ── Step 1: make everything runnable ───────────────────────────────────────
note "Making the launcher runnable..."
chmod +x LAUNCH_ME.py launch_desktop.sh 2>/dev/null
ok "Ready."

# ── Step 2: install the icon ───────────────────────────────────────────────
ICON_DIR="${HOME}/.local/share/icons/hicolor/scalable/apps"
note "Adding the OutClaw icon..."
mkdir -p "$ICON_DIR"
if [ -f "outclaw-icon.svg" ]; then
  cp outclaw-icon.svg "$ICON_DIR/outclaw.svg" 2>/dev/null && ok "Icon installed."
else
  note "Icon file not found — the icon will be a generic one."
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -f -q "${HOME}/.local/share/icons/hicolor" >/dev/null 2>&1 || true
fi

# ── Step 3: add the app-menu entry ─────────────────────────────────────────
APP_DIR="${HOME}/.local/share/applications"
mkdir -p "$APP_DIR"

note "Creating the OutClaw app entry..."
cat > "$APP_DIR/outclaw.desktop" << EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=OutClaw
Comment=Check your court papers for problems before you file them
Exec=bash ${INSTALL_DIR}/launch_desktop.sh
Icon=outclaw
Terminal=true
Categories=Office;
Keywords=court;legal;papers;audit;self-help;
StartupNotify=true
EOF
ok "App entry added to your app menu."

# ── Step 4: also put it on the desktop, if you have one ────────────────────
DESKTOP_DIR="${HOME}/Desktop"
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
fi

if [ -d "$DESKTOP_DIR" ] && [ -w "$DESKTOP_DIR" ]; then
  note "Also placing a shortcut on your desktop..."
  cp "$APP_DIR/outclaw.desktop" "$DESKTOP_DIR/OutClaw.desktop"
  chmod +x "$DESKTOP_DIR/OutClaw.desktop" 2>/dev/null
  # Some desktops (GNOME) refuse to run launchers they do not trust.
  if command -v gio >/dev/null 2>&1; then
    gio set "$DESKTOP_DIR/OutClaw.desktop" metadata::trusted true 2>/dev/null || true
  fi
  ok "Shortcut placed on your desktop."
fi

# ── Step 5: refresh the app menu ───────────────────────────────────────────
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi

# ── Done — tell them what to do next, in plain words ──────────────────────
echo ""
head "══════════════════════════════════════════════════════"
head "  ✓ OUTCLAW IS SET UP!"
head "══════════════════════════════════════════════════════"
echo ""
say  "To open OutClaw, just:"
say  ""
if [ "$PLATFORM" = "chromebook" ]; then
  say  "  1. Press the circle of dots (the app launcher) at the bottom left."
  say  "  2. Look under ${BOLD}Linux apps${RESET} for ${BOLD}OutClaw${RESET}."
  say  "  3. Click it — or right-click it and choose ${BOLD}Pin to shelf${RESET}"
  say  "     so it always stays one click away."
else
  if [ -f "$DESKTOP_DIR/OutClaw.desktop" ]; then
    say  "  1. Double-click the ${BOLD}OutClaw${RESET} icon on your desktop."
  fi
  say  "  1. Open your app menu and look for ${BOLD}OutClaw${RESET}."
  say  "  2. Click it."
fi
say  ""
say  "A window will open showing OutClaw's welcome screen, and your"
say  "browser will open to the dashboard. Keep that window open while"
say  "you use OutClaw, and close it when you are done."
say  ""
say  "To undo all of this later:"
say  "    rm -f \"$APP_DIR/outclaw.desktop\" \"$DESKTOP_DIR/OutClaw.desktop\""
echo ""
