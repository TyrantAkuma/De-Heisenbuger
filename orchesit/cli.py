"""
OrchesIt Command-Line Interface (CLI).
Provides commands to initialize projects, run DAGs, inspect status, and export dashboards.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from orchesit.orchestrator import Orchestrator
from orchesit.state import DeliberationType, StateStore, TaskStatus, Verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="OrchesIt Autonomous Multi-Agent Control Plane CLI")
    parser.add_argument("--db", default="orchesit_state.db", help="Path to SQLite state database")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a new project")
    init_parser.add_argument("objective", help="Project goal or prompt")
    init_parser.add_argument("--id", default="heisenbug-v1", help="Project ID")
    init_parser.add_argument("--name", default="Heisenbug", help="Project Name")

    # status
    status_parser = subparsers.add_parser("status", help="Inspect project state")
    status_parser.add_argument("project_id", help="Project ID to inspect")

    # dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Generate HTML dashboard")
    dash_parser.add_argument("project_id", help="Project ID")
    dash_parser.add_argument("--output", default="dashboard.html", help="HTML output path")

    args = parser.parse_args()
    orch = Orchestrator(db_path=args.db)

    if args.command == "init":
        orch.init_project(args.id, args.name, args.objective)
        print(f"Project '{args.name}' [{args.id}] initialized in {args.db}")

    elif args.command == "status":
        summary = orch.get_project_summary(args.project_id)
        print(json.dumps(summary, indent=2))

    elif args.command == "dashboard":
        path = orch.export_dashboard(args.project_id, args.output)
        print(f"Interactive light-theme dashboard generated at: {path}")


if __name__ == "__main__":
    main()
