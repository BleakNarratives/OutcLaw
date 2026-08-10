import argparse
from pathlib import Path
import outclaw_unified as unified
import sys
from outclaw_cli import _read_text

def run_case_audit(case_dir: str):
    case_path = Path(case_dir)
    if not case_path.is_dir():
        print(f"Error: {case_dir} is not a directory.")
        return

    print(f"--- Scanning case directory: {case_dir} ---\n")
    
    extensions = ['*.txt', '*.pdf']
    all_files = []
    for ext in extensions:
        all_files.extend(list(case_path.glob(ext)))
    
    if not all_files:
        print("No readable files found in directory.")
        return

    # Aggregate findings
    for file in all_files:
        print(f"Processing: {file.name}")
        try:
            text = _read_text(file)
            report = unified.audit_text(text)
            print(f"  Findings: {len(report.findings)}")
            # Real implementation would aggregate findings into a case-wide report
        except Exception as e:
            print(f"  Error processing {file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="Path to the case directory")
    args = parser.parse_args()
    run_case_audit(args.directory)
