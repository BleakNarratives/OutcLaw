#!/bin/bash
# OutClaw Dashboard Installation Script
# Cross-platform setup for Termux, Windows (Git Bash), Linux, and Chromebook

echo "════════════════════════════════════════════════════════════"
echo "  OutClaw Dashboard Installation"
echo "════════════════════════════════════════════════════════════"
echo ""

# Detect platform
if [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
    PLATFORM="termux"
    echo "→ Platform: Termux (Android)"
elif [ -n "$SOMMELIER_VERSION" ] || [ -d "/opt/google/cros-containers" ]; then
    PLATFORM="chromebook"
    echo "→ Platform: Chromebook (Crostini)"
elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    PLATFORM="windows"
    echo "→ Platform: Windows (Git Bash/MSYS)"
else
    PLATFORM="linux"
    echo "→ Platform: Linux"
fi

# Check Python version
echo "→ Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo "  Found: Python $PYTHON_VERSION"
else
    echo "✗ Python 3 not found."
    if [ "$PLATFORM" = "termux" ]; then
        echo "  Install with: pkg install python"
    else
        echo "  Please install Python 3.8 or higher."
    fi
    exit 1
fi

# Check pip
echo "→ Checking pip..."
if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
    echo "✗ pip not found."
    if [ "$PLATFORM" = "termux" ]; then
        echo "  Install with: pkg install python-pip"
    else
        echo "  Please install pip."
    fi
    exit 1
fi

# Determine if we need a virtual environment
USE_VENV=false
if [ "$PLATFORM" = "chromebook" ] || [ "$PLATFORM" = "linux" ]; then
    # Check if pip install would fail due to externally-managed environment
    if pip3 install --dry-run --no-deps pyyaml 2>&1 | grep -q "externally-managed-environment"; then
        USE_VENV=true
        echo "→ Detected externally-managed Python environment"
    fi
fi

# Install dependencies
echo "→ Installing dependencies..."

if [ "$USE_VENV" = true ]; then
    echo "  Creating virtual environment..."
    
    VENV_DIR=".venv"
    
    # Create venv if it doesn't exist
    if [ ! -d "$VENV_DIR" ]; then
        if ! python3 -m venv "$VENV_DIR" 2>/dev/null; then
            echo "✗ Failed to create virtual environment."
            echo "  Installing python3-venv..."
            sudo apt update && sudo apt install -y python3-venv python3-full || {
                echo "✗ Could not install python3-venv. Please run:"
                echo "    sudo apt install python3-venv python3-full"
                exit 1
            }
            python3 -m venv "$VENV_DIR" || {
                echo "✗ Failed to create virtual environment after installing dependencies."
                exit 1
            }
        fi
    fi
    
    echo "  Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    
    echo "  Installing packages in virtual environment..."
    pip install -r requirements-dashboard.txt || {
        echo "✗ Failed to install dependencies in virtual environment."
        exit 1
    }
    
    echo "  ✓ Dependencies installed in virtual environment"
    
    # Create wrapper script
    cat > run_dashboard.sh << 'WRAPPER'
#!/bin/bash
# OutClaw Dashboard Launcher (with venv activation)
cd "$(dirname "$0")"
source .venv/bin/activate
python3 outclaw_dashboard.py "$@"
WRAPPER
    chmod +x run_dashboard.sh
    echo "  ✓ Created launcher script: ./run_dashboard.sh"
    
else
    # Install system-wide (Termux, older Linux, Windows)
    if command -v pip3 &> /dev/null; then
        pip3 install -r requirements-dashboard.txt || {
            echo "✗ Failed to install dependencies."
            exit 1
        }
    else
        pip install -r requirements-dashboard.txt || {
            echo "✗ Failed to install dependencies."
            exit 1
        }
    fi
fi

# Make dashboard executable
echo "→ Making dashboard executable..."
chmod +x outclaw_dashboard.py

# Create config directory
echo "→ Creating config directory..."
if [ "$PLATFORM" = "termux" ]; then
    CONFIG_DIR="$HOME/.outclaw"
elif [ "$PLATFORM" = "windows" ]; then
    CONFIG_DIR="$APPDATA/OutClaw"
else
    CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/outclaw"
fi

mkdir -p "$CONFIG_DIR"
echo "  Config directory: $CONFIG_DIR"

# Create test file
echo "→ Creating test file..."
if [ "$PLATFORM" = "termux" ]; then
    TEST_FILE="$HOME/outclaw_test.txt"
else
    TEST_FILE="/tmp/outclaw_test.txt"
fi

cat > "$TEST_FILE" << 'EOF'
This motion cites Miranda v. Arizona, 384 U.S. 436 (1966), which established
the requirement for police to inform suspects of their rights before custodial
interrogation.

We also reference 42 U.S.C. § 1983, the civil rights statute that provides
a cause of action for constitutional violations by state actors.

The Supreme Court in Brady v. Maryland, 373 U.S. 83 (1963), held that the
prosecution must disclose material exculpatory evidence to the defense.
EOF

echo "  Test file: $TEST_FILE"

# Platform-specific notes
echo ""
if [ "$PLATFORM" = "termux" ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  Termux-Specific Setup"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Optional packages for full functionality:"
    echo "  • Storage access:  termux-setup-storage"
    echo "  • File sharing:    pkg install termux-api"
    echo "  • Cloud sync:      pkg install rclone"
    echo "  • Remote access:   pkg install openssh"
    echo ""
elif [ "$PLATFORM" = "chromebook" ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  Chromebook-Specific Setup"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Notes:"
    echo "  • Virtual environment created in .venv/"
    echo "  • Use ./run_dashboard.sh to launch (auto-activates venv)"
    echo "  • Or manually: source .venv/bin/activate && python3 outclaw_dashboard.py"
    echo "  • Files are in Linux container only"
    echo "  • Use Chrome OS file manager to access"
    echo ""
elif [ "$PLATFORM" = "windows" ]; then
    echo "════════════════════════════════════════════════════════════"
    echo "  Windows-Specific Setup"
    echo "════════════════════════════════════════════════════════════"
    echo ""
    echo "Notes:"
    echo "  • Use PowerShell or Git Bash"
    echo "  • ANSI colors enabled automatically"
    echo "  • Config in: %APPDATA%\\OutClaw"
    echo ""
fi

echo "════════════════════════════════════════════════════════════"
echo "  ✓ Installation Complete!"
echo "════════════════════════════════════════════════════════════"
echo ""
echo "Quick Start:"
if [ "$USE_VENV" = true ]; then
    echo "  1. Run setup wizard:  source .venv/bin/activate && python3 -m dashboard.setup_wizard"
    echo "  2. Or run dashboard:  ./run_dashboard.sh"
    echo "  3. Or manually:       source .venv/bin/activate && python3 outclaw_dashboard.py"
else
    echo "  1. Run setup wizard:  python3 -m dashboard.setup_wizard"
    echo "  2. Or run dashboard:  python3 outclaw_dashboard.py"
fi
echo "  4. Press '1' to audit file"
echo "  5. Enter path:        $TEST_FILE"
echo "  6. Press 'H' for help, 'Q' to quit"
echo ""
echo "Test file created at: $TEST_FILE"
echo ""
echo "For more info, see: DASHBOARD_QUICKSTART.md"
echo ""