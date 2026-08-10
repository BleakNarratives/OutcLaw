#!/bin/bash
# OutClaw Legal Scouts Launcher
# Paralegal Superpowers: One-Click Intelligence Gathering

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCOUTS_DIR="$SCRIPT_DIR/scouts"

echo "================================================================================"
echo "OUTCLAW LEGAL SCOUTS"
echo "Paralegal Superpowers: Intelligence Gathering System"
echo "================================================================================"
echo ""

# Check if scouts directory exists
if [ ! -d "$SCOUTS_DIR" ]; then
    echo "❌ Error: Scouts directory not found at $SCOUTS_DIR"
    exit 1
fi

# Function to display menu
show_menu() {
    echo "Available Scouts:"
    echo ""
    echo "1. Legal Docket Scout"
    echo "   - Scout attorney litigation history"
    echo "   - Scout judge ruling patterns"
    echo "   - Detect sanctions and discipline"
    echo ""
    echo "2. Case Law Scout"
    echo "   - Research legal precedents"
    echo "   - Find winning arguments"
    echo "   - Generate brief outlines"
    echo ""
    echo "3. Run All Scouts (Custom Target)"
    echo ""
    echo "4. Exit"
    echo ""
}

# Function to run legal docket scout
run_docket_scout() {
    echo ""
    echo "=== LEGAL DOCKET SCOUT ==="
    echo ""
    read -p "Scout type (attorney/judge): " scout_type
    
    if [ "$scout_type" = "attorney" ]; then
        read -p "Attorney name: " attorney_name
        read -p "Bar number (optional): " bar_number
        read -p "Jurisdiction (optional): " jurisdiction
        
        cmd="python3 $SCOUTS_DIR/legal_docket_scout.py --attorney \"$attorney_name\""
        [ -n "$bar_number" ] && cmd="$cmd --bar-number \"$bar_number\""
        [ -n "$jurisdiction" ] && cmd="$cmd --jurisdiction \"$jurisdiction\""
        
        echo ""
        echo "Running: $cmd"
        echo ""
        eval $cmd
        
    elif [ "$scout_type" = "judge" ]; then
        read -p "Judge name: " judge_name
        read -p "Court (optional): " court
        
        cmd="python3 $SCOUTS_DIR/legal_docket_scout.py --judge \"$judge_name\""
        [ -n "$court" ] && cmd="$cmd --court \"$court\""
        
        echo ""
        echo "Running: $cmd"
        echo ""
        eval $cmd
    else
        echo "❌ Invalid scout type. Use 'attorney' or 'judge'"
    fi
}

# Function to run case law scout
run_caselaw_scout() {
    echo ""
    echo "=== CASE LAW SCOUT ==="
    echo ""
    read -p "Legal issue to research: " issue
    read -p "Jurisdiction (optional): " jurisdiction
    read -p "Generate brief outline? (y/n): " brief
    
    cmd="python3 $SCOUTS_DIR/case_law_scout.py --issue \"$issue\""
    [ -n "$jurisdiction" ] && cmd="$cmd --jurisdiction \"$jurisdiction\""
    [ "$brief" = "y" ] && cmd="$cmd --brief"
    
    echo ""
    echo "Running: $cmd"
    echo ""
    eval $cmd
}

# Function to run all scouts
run_all_scouts() {
    echo ""
    echo "=== RUN ALL SCOUTS ==="
    echo ""
    read -p "Target name (attorney/judge/company): " target
    read -p "Target type (attorney/judge/company): " target_type
    
    echo ""
    echo "Running comprehensive intelligence gathering on: $target"
    echo ""
    
    if [ "$target_type" = "attorney" ]; then
        python3 "$SCOUTS_DIR/legal_docket_scout.py" --attorney "$target"
    elif [ "$target_type" = "judge" ]; then
        python3 "$SCOUTS_DIR/legal_docket_scout.py" --judge "$target"
    fi
    
    echo ""
    echo "✅ All scouts complete!"
}

# Main loop
while true; do
    show_menu
    read -p "Select option (1-4): " choice
    
    case $choice in
        1)
            run_docket_scout
            ;;
        2)
            run_caselaw_scout
            ;;
        3)
            run_all_scouts
            ;;
        4)
            echo ""
            echo "Exiting OutClaw Legal Scouts"
            echo ""
            exit 0
            ;;
        *)
            echo "❌ Invalid option. Please select 1-4."
            ;;
    esac
    
    echo ""
    read -p "Press Enter to continue..."
    clear
done
