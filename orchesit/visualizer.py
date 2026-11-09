"""
OrchesIt Light-Theme Visualizer and Dashboard Generator.
Builds an interactive, high-contrast light-mode HTML dashboard visualizing
the DAG execution state, jury deliberations, verification audits, and SHA-256 artifact hashes.
Strictly conforms to Light-Theme design guidelines (#FFFFFF / #F8FAFC, #0F172A, #E2E8F0).
"""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List
from orchesit.state import StateStore, TaskStatus, Verdict


class DashboardVisualizer:
    """Generates a responsive, clean light-mode HTML dashboard from OrchesIt state."""

    def __init__(self, state_store: StateStore):
        self.store = state_store

    def generate_html(self, project_id: str) -> str:
        project = self.store.get_project(project_id)
        if not project:
            return "<html><body><h1>Project Not Found</h1></body></html>"

        tasks = self.store.list_tasks(project_id)
        full_tasks = [self.store.get_full_task_summary(t["id"]) for t in tasks]

        total_tasks = len(tasks)
        completed = sum(1 for t in tasks if t["status"] == TaskStatus.COMPLETED.value)
        failed = sum(1 for t in tasks if t["status"] == TaskStatus.FAILED.value)
        running = sum(1 for t in tasks if t["status"] in (TaskStatus.RUNNING.value, TaskStatus.VERIFYING.value, TaskStatus.DELIBERATING.value))
        pending = sum(1 for t in tasks if t["status"] in (TaskStatus.PENDING.value, TaskStatus.READY.value))

        pct = int((completed / total_tasks * 100)) if total_tasks > 0 else 0

        # Build task cards HTML
        task_cards_html = []
        for t in full_tasks:
            status = t["status"]
            status_color_bg = "#DEF7EC" if status == "COMPLETED" else "#FDE8E8" if status == "FAILED" else "#E1EFFE" if status in ("RUNNING", "VERIFYING", "DELIBERATING") else "#F3F4F6"
            status_color_fg = "#03543F" if status == "COMPLETED" else "#9B1C1C" if status == "FAILED" else "#1E429F" if status in ("RUNNING", "VERIFYING", "DELIBERATING") else "#374151"

            deps = self.store.get_task_dependencies(t["id"])
            deps_str = ", ".join(deps) if deps else "None (Root)"

            # Acceptance criteria list
            criteria_items = "".join(f"<li>{html.escape(c)}</li>" for c in t["acceptance_criteria"])

            # Artifacts list
            artifacts_html = ""
            if t["artifacts"]:
                art_rows = []
                for a in t["artifacts"]:
                    art_rows.append(
                        f"""
                        <div class="artifact-row">
                            <span class="artifact-path">📄 {html.escape(a['file_path'])}</span>
                            <span class="artifact-hash" title="SHA-256">{html.escape(a['sha256_hash'][:16])}...</span>
                            <span class="artifact-size">{a['file_size']} B</span>
                        </div>
                        """
                    )
                artifacts_html = f"<div class='artifact-list'><strong>Deliverables & Artifacts (SHA-256):</strong>{''.join(art_rows)}</div>"

            # Verification details
            verif_html = ""
            if t["verification"]:
                v = t["verification"]
                v_badge_bg = "#DEF7EC" if "PASS" in v["verdict"] else "#FDE8E8"
                v_badge_fg = "#03543F" if "PASS" in v["verdict"] else "#9B1C1C"
                verif_html = f"""
                <div class="verif-box">
                    <div class="verif-header">
                        <strong>Independent Verifier:</strong> <span class="role-badge">{html.escape(v['verifier_role'])}</span>
                        <span class="status-pill" style="background:{v_badge_bg}; color:{v_badge_fg};">{v['verdict']}</span>
                    </div>
                    <p class="critique">"{html.escape(v['critique'])}"</p>
                </div>
                """

            # Jury details
            jury_html = ""
            if t["jury"]:
                jury_cards = []
                for j in t["jury"]:
                    j_vote_bg = "#DEF7EC" if j["vote"] == "PASS" else "#FDE8E8"
                    j_vote_fg = "#03543F" if j["vote"] == "PASS" else "#9B1C1C"
                    jury_cards.append(
                        f"""
                        <div class="juror-card">
                            <div class="juror-top">
                                <span class="juror-role">{html.escape(j['juror_role'])}</span>
                                <span class="status-pill" style="background:{j_vote_bg}; color:{j_vote_fg};">{j['vote']} (conf: {int(j['confidence']*100)}%)</span>
                            </div>
                            <div class="juror-reasoning">{html.escape(j['reasoning'])}</div>
                            {f'<div class="juror-rebuttal"><strong>Cross-Exam Rebuttal:</strong> {html.escape(j["rebuttal"])}</div>' if j.get('rebuttal') else ''}
                        </div>
                        """
                    )
                res_box = ""
                if t["resolution"]:
                    r = t["resolution"]
                    res_box = f"""
                    <div class="resolution-box">
                        <strong>Orchestrator Binding Resolution:</strong>
                        <span class="status-pill" style="background:#DEF7EC; color:#03543F;">{r['final_verdict']}</span>
                        <p>{html.escape(r['architectural_justification'])}</p>
                    </div>
                    """
                jury_html = f"""
                <div class="jury-section">
                    <h4>Adversarial Jury Deliberations (Round 1 & 2)</h4>
                    <div class="jurors-grid">{''.join(jury_cards)}</div>
                    {res_box}
                </div>
                """

            card = f"""
            <div class="task-card" id="task-{t['id']}">
                <div class="task-header">
                    <div class="task-title-group">
                        <span class="task-id">[{t['id']}]</span>
                        <h3 class="task-title">{html.escape(t['title'])}</h3>
                    </div>
                    <span class="status-pill" style="background:{status_color_bg}; color:{status_color_fg}; font-weight:600;">{status}</span>
                </div>

                <div class="task-meta-grid">
                    <div><span class="meta-label">Workstream:</span> <strong>{html.escape(t['workstream'])}</strong></div>
                    <div><span class="meta-label">Executor:</span> <span class="role-badge">{html.escape(t['executor_role'])}</span></div>
                    <div><span class="meta-label">Verifier:</span> <span class="role-badge">{html.escape(t['verifier_role'])}</span></div>
                    <div><span class="meta-label">Deliberation:</span> {html.escape(t['deliberation_type'])}</div>
                    <div><span class="meta-label">Dependencies:</span> {html.escape(deps_str)}</div>
                    <div><span class="meta-label">Retries:</span> {t['retry_count']}</div>
                </div>

                <div class="criteria-box">
                    <strong>Acceptance Criteria:</strong>
                    <ul>{criteria_items}</ul>
                </div>

                {artifacts_html}
                {verif_html}
                {jury_html}
            </div>
            """
            task_cards_html.append(card)

        all_cards_str = "\n".join(task_cards_html)

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OrchesIt Control Plane — {html.escape(project['name'])}</title>
    <style>
        :root {{
            --bg-canvas: #F8FAFC;
            --bg-card: #FFFFFF;
            --border-color: #E2E8F0;
            --text-primary: #0F172A;
            --text-secondary: #475569;
            --text-muted: #64748B;
            --accent-primary: #2563EB;
            --accent-hover: #1D4ED8;
            --success-bg: #DEF7EC;
            --success-fg: #03543F;
            --danger-bg: #FDE8E8;
            --danger-fg: #9B1C1C;
            --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
            --shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -1px rgba(0, 0, 0, 0.04);
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            background-color: var(--bg-canvas);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.5;
            padding: 2rem;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        header {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: var(--shadow-sm);
        }}

        .header-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}

        h1 {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .objective-text {{
            color: var(--text-secondary);
            font-size: 1rem;
            margin-top: 0.5rem;
            background: #F1F5F9;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border-left: 4px solid var(--accent-primary);
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 1rem;
            margin-top: 1.5rem;
        }}

        .stat-card {{
            background: var(--bg-canvas);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}

        .stat-value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--text-primary);
        }}

        .stat-label {{
            font-size: 0.85rem;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 600;
        }}

        .progress-bar-container {{
            margin-top: 1.5rem;
            background: #E2E8F0;
            border-radius: 9999px;
            height: 12px;
            overflow: hidden;
        }}

        .progress-bar-fill {{
            background: #10B981;
            height: 100%;
            transition: width 0.3s ease;
        }}

        .section-title {{
            font-size: 1.25rem;
            font-weight: 600;
            margin-bottom: 1rem;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .tasks-container {{
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }}

        .task-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: var(--shadow-sm);
            transition: transform 0.1s ease, box-shadow 0.1s ease;
        }}

        .task-card:hover {{
            box-shadow: var(--shadow-md);
        }}

        .task-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
            padding-bottom: 0.75rem;
            border-bottom: 1px solid var(--border-color);
        }}

        .task-title-group {{
            display: flex;
            align-items: baseline;
            gap: 0.5rem;
        }}

        .task-id {{
            font-weight: 700;
            color: var(--accent-primary);
            font-family: monospace;
        }}

        .task-title {{
            font-size: 1.15rem;
            font-weight: 600;
        }}

        .status-pill {{
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.8rem;
            letter-spacing: 0.025em;
        }}

        .task-meta-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 0.75rem;
            font-size: 0.9rem;
            margin-bottom: 1rem;
            background: #F8FAFC;
            padding: 0.75rem 1rem;
            border-radius: 8px;
            border: 1px solid var(--border-color);
        }}

        .meta-label {{
            color: var(--text-muted);
        }}

        .role-badge {{
            background: #E0E7FF;
            color: #3730A3;
            font-family: monospace;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-size: 0.85rem;
            font-weight: 600;
        }}

        .criteria-box {{
            background: #FFFFFF;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }}

        .criteria-box ul {{
            margin-left: 1.25rem;
            margin-top: 0.25rem;
            color: var(--text-secondary);
        }}

        .artifact-list {{
            background: #F8FAFC;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 0.75rem 1rem;
            margin-bottom: 1rem;
            font-size: 0.85rem;
        }}

        .artifact-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0.35rem 0;
            border-bottom: 1px dashed var(--border-color);
            font-family: monospace;
        }}

        .artifact-row:last-child {{
            border-bottom: none;
        }}

        .artifact-hash {{
            color: var(--accent-primary);
            background: #EEF2FF;
            padding: 0.1rem 0.3rem;
            border-radius: 4px;
        }}

        .verif-box {{
            background: #F9FAFB;
            border-left: 4px solid #10B981;
            padding: 0.75rem 1rem;
            border-radius: 0 8px 8px 0;
            margin-bottom: 1rem;
            font-size: 0.9rem;
        }}

        .verif-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.35rem;
        }}

        .critique {{
            color: var(--text-secondary);
            font-style: italic;
        }}

        .jury-section {{
            margin-top: 1rem;
            background: #F8FAFC;
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
        }}

        .jury-section h4 {{
            font-size: 0.95rem;
            margin-bottom: 0.75rem;
            color: var(--text-primary);
        }}

        .jurors-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}

        .juror-card {{
            background: #FFFFFF;
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.85rem;
        }}

        .juror-top {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.35rem;
        }}

        .juror-role {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .juror-reasoning {{
            color: var(--text-secondary);
            margin-top: 0.25rem;
        }}

        .juror-rebuttal {{
            margin-top: 0.4rem;
            padding-top: 0.4rem;
            border-top: 1px dashed var(--border-color);
            color: #4338CA;
            font-size: 0.8rem;
        }}

        .resolution-box {{
            background: #EFF6FF;
            border: 1px solid #BFDBFE;
            border-radius: 6px;
            padding: 0.75rem;
            font-size: 0.85rem;
            color: #1E3A8A;
        }}

        footer {{
            text-align: center;
            margin-top: 3rem;
            font-size: 0.85rem;
            color: var(--text-muted);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-top">
                <div>
                    <h1>OrchesIt Autonomous Multi-Agent Control Plane</h1>
                    <div style="font-size:0.9rem; color:var(--text-muted); margin-top:0.25rem;">
                        Project ID: <code>{html.escape(project['id'])}</code> &bull; Status: <strong>{project['status']}</strong>
                    </div>
                </div>
                <span class="status-pill" style="background:#DEF7EC; color:#03543F; font-size: 0.9rem; font-weight: 700;">ACID PERSISTENT</span>
            </div>

            <div class="objective-text">
                <strong>User Objective:</strong> {html.escape(project['objective'])}
            </div>

            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{total_tasks}</div>
                    <div class="stat-label">Total DAG Tasks</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:#10B981;">{completed}</div>
                    <div class="stat-label">Verified Passing</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:#2563EB;">{running}</div>
                    <div class="stat-label">In Flight / Verifying</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" style="color:#EF4444;">{failed}</div>
                    <div class="stat-label">Defects / Failed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{pct}%</div>
                    <div class="stat-label">Completion Progress</div>
                </div>
            </div>

            <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: {pct}%;"></div>
            </div>
        </header>

        <div class="section-title">
            <span>Dependency Execution Stream & Deliberation Record</span>
        </div>

        <div class="tasks-container">
            {all_cards_str}
        </div>

        <footer>
            Built with OrchesIt Multi-Agent Control Plane &bull; SQLite ACID State &bull; High-Contrast Light Theme
        </footer>
    </div>
</body>
</html>
"""
        return html_content

    def export_dashboard(self, project_id: str, output_path: str | Path = "dashboard.html") -> Path:
        content = self.generate_html(project_id)
        out_p = Path(output_path)
        out_p.write_text(content, encoding="utf-8")
        return out_p
