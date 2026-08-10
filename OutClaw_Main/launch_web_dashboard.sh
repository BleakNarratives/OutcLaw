#!/bin/bash
# OutClaw Web Dashboard Launcher
# One-click launch script - installs dependencies and opens browser

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║   🚀 OutClaw Web Dashboard Launcher                        ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Change to OutClaw directory
cd "$(dirname "$0")"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "→ Virtual environment not found"
    echo "→ Running installer first..."
    echo ""
    bash install_dashboard.sh || {
        echo "✗ Installation failed"
        exit 1
    }
    echo ""
fi

# Activate virtual environment
echo "→ Activating virtual environment..."
source .venv/bin/activate

# Check if Flask is installed
if ! python3 -c "import flask" 2>/dev/null; then
    echo "→ Installing Flask..."
    pip install -q flask
    echo "  ✓ Flask installed"
fi

# Get available port (default 5000, try 5001-5010 if busy)
PORT=5000
while lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; do
    PORT=$((PORT + 1))
    if [ $PORT -gt 5010 ]; then
        echo "✗ No available ports found (5000-5010 all busy)"
        exit 1
    fi
done

echo "→ Starting web dashboard on port $PORT..."
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║                                                            ║"
echo "║   ✓ Dashboard Ready!                                       ║"
echo "║                                                            ║"
echo "║   🌐 Open in browser: http://localhost:$PORT                ║"
echo "║                                                            ║"
echo "║   📁 Drag & drop files to audit                            ║"
echo "║   🔍 Click buttons to analyze                              ║"
echo "║   ⚡ Results appear instantly                              ║"
echo "║                                                            ║"
echo "║   Press Ctrl+C to stop                                     ║"
echo "║                                                            ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Launch web dashboard (will auto-open browser)
python3 -c "
from dashboard.web_app import run_web_dashboard
run_web_dashboard(port=$PORT, debug=False, open_browser_on_start=True)
"
