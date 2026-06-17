from __future__ import annotations

import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for

STAGE_FLOW = ["Backlog", "Build", "Test", "Release", "Deploy", "Monitor"]
STATUS_OPTIONS = ["Planned", "In Progress", "Blocked", "Healthy", "Done"]
DEFAULT_ENVIRONMENTS = ["development", "qa", "staging", "production"]

SEED_ITEMS = [
    {
        "service_name": "payments-api",
        "environment": "staging",
        "stage": "Test",
        "status": "In Progress",
        "owner": "sara",
        "reference_url": "http://localhost:8080/job/payments-api/",
        "notes": "Integration suite is running against the latest image.",
    },
    {
        "service_name": "web-frontend",
        "environment": "qa",
        "stage": "Release",
        "status": "Blocked",
        "owner": "lina",
        "reference_url": "http://localhost:8080/job/web-frontend/",
        "notes": "Waiting for approval after a visual regression in checkout.",
    },
    {
        "service_name": "billing-worker",
        "environment": "production",
        "stage": "Monitor",
        "status": "Healthy",
        "owner": "mohamed",
        "reference_url": "http://localhost:8080/job/billing-worker/",
        "notes": "Deploy completed and error rate stayed within threshold.",
    },
]


def utc_label() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")


def ensure_parent_dir(file_path: str) -> None:
    Path(file_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def connect_db(app: Flask) -> sqlite3.Connection:
    connection = sqlite3.connect(app.config["DATABASE_PATH"])
    connection.row_factory = sqlite3.Row
    return connection


def normalize_choice(value: str, allowed: list[str], fallback: str) -> str:
    cleaned = value.strip()
    return cleaned if cleaned in allowed else fallback


def init_db(app: Flask) -> None:
    ensure_parent_dir(app.config["DATABASE_PATH"])

    with connect_db(app) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS work_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_name TEXT NOT NULL,
                environment TEXT NOT NULL,
                stage TEXT NOT NULL,
                status TEXT NOT NULL,
                owner TEXT,
                reference_url TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

        item_count = connection.execute("SELECT COUNT(*) FROM work_items").fetchone()[0]
        if item_count == 0 and app.config["SEED_DEMO_DATA"]:
            now = utc_label()
            connection.executemany(
                """
                INSERT INTO work_items (
                    service_name,
                    environment,
                    stage,
                    status,
                    owner,
                    reference_url,
                    notes,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        item["service_name"],
                        item["environment"],
                        item["stage"],
                        item["status"],
                        item["owner"],
                        item["reference_url"],
                        item["notes"],
                        now,
                        now,
                    )
                    for item in SEED_ITEMS
                ],
            )


def fetch_items(app: Flask, filters: dict[str, str] | None = None) -> list[dict[str, Any]]:
    clauses: list[str] = []
    values: list[str] = []

    for field in ("environment", "stage", "status"):
        selected = (filters or {}).get(field, "").strip()
        if selected:
            clauses.append(f"{field} = ?")
            values.append(selected)

    query = "SELECT * FROM work_items"
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY CASE status WHEN 'Blocked' THEN 0 WHEN 'In Progress' THEN 1 ELSE 2 END, updated_at DESC"

    with connect_db(app) as connection:
        rows = connection.execute(query, values).fetchall()

    return [dict(row) for row in rows]


def fetch_item(app: Flask, item_id: int) -> dict[str, Any] | None:
    with connect_db(app) as connection:
        row = connection.execute("SELECT * FROM work_items WHERE id = ?", (item_id,)).fetchone()
    return dict(row) if row else None


def insert_item(app: Flask, payload: dict[str, str]) -> None:
    now = utc_label()
    with connect_db(app) as connection:
        connection.execute(
            """
            INSERT INTO work_items (
                service_name,
                environment,
                stage,
                status,
                owner,
                reference_url,
                notes,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["service_name"],
                payload["environment"],
                payload["stage"],
                payload["status"],
                payload["owner"],
                payload["reference_url"],
                payload["notes"],
                now,
                now,
            ),
        )


def update_item(app: Flask, item_id: int, **changes: str) -> None:
    if not changes:
        return

    assignments = [f"{field} = ?" for field in changes]
    values = list(changes.values())
    values.extend([utc_label(), item_id])

    with connect_db(app) as connection:
        connection.execute(
            f"UPDATE work_items SET {', '.join(assignments)}, updated_at = ? WHERE id = ?",
            values,
        )


def delete_item(app: Flask, item_id: int) -> None:
    with connect_db(app) as connection:
        connection.execute("DELETE FROM work_items WHERE id = ?", (item_id,))


def build_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    statuses = Counter(item["status"] for item in items)
    summary = {
        "total": len(items),
        "in_progress": statuses.get("In Progress", 0),
        "blocked": statuses.get("Blocked", 0),
        "healthy": statuses.get("Healthy", 0),
        "done": statuses.get("Done", 0),
    }
    healthy_total = summary["healthy"] + summary["done"]
    summary["delivery_health"] = round((healthy_total / len(items)) * 100) if items else 0
    return summary


def build_stage_totals(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stage_counts = Counter(item["stage"] for item in items)
    return [{"name": stage, "count": stage_counts.get(stage, 0)} for stage in STAGE_FLOW]


def environment_options(items: list[dict[str, Any]]) -> list[str]:
    discovered = {item["environment"] for item in items}
    return sorted(discovered.union(DEFAULT_ENVIRONMENTS))


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    base_dir = Path(__file__).resolve().parent
    default_db_path = base_dir / "data" / "devops-helper.db"

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.getenv("SECRET_KEY", "devops-helper-local-secret"),
        DATABASE_PATH=os.getenv("DATABASE_PATH", str(default_db_path)),
        DASHBOARD_NAME=os.getenv("DASHBOARD_NAME", "DevOps Cycle Helper"),
        JENKINS_URL=os.getenv("JENKINS_URL", "http://localhost:8080"),
        SEED_DEMO_DATA=os.getenv("SEED_DEMO_DATA", "true").lower() not in {"0", "false", "no"},
    )

    if test_config:
        app.config.update(test_config)

    init_db(app)

    @app.context_processor
    def inject_template_data() -> dict[str, Any]:
        return {"stage_flow": STAGE_FLOW, "status_options": STATUS_OPTIONS}

    @app.get("/")
    def index() -> str:
        filters = {
            "environment": request.args.get("environment", ""),
            "stage": request.args.get("stage", ""),
            "status": request.args.get("status", ""),
        }
        all_items = fetch_items(app)
        visible_items = fetch_items(app, filters)
        summary = build_summary(all_items)

        return render_template(
            "index.html",
            dashboard_name=app.config["DASHBOARD_NAME"],
            jenkins_url=app.config["JENKINS_URL"],
            all_items=all_items,
            items=visible_items,
            filters=filters,
            environments=environment_options(all_items),
            summary=summary,
            stage_totals=build_stage_totals(all_items),
            refreshed_at=utc_label(),
        )

    @app.post("/items")
    def add_item() -> Any:
        service_name = request.form.get("service_name", "").strip()
        environment = request.form.get("environment", "").strip()
        owner = request.form.get("owner", "").strip()
        reference_url = request.form.get("reference_url", "").strip()
        notes = request.form.get("notes", "").strip()
        stage = normalize_choice(request.form.get("stage", ""), STAGE_FLOW, STAGE_FLOW[0])
        status = normalize_choice(request.form.get("status", ""), STATUS_OPTIONS, STATUS_OPTIONS[0])

        if not service_name or not environment:
            flash("Service name and environment are required.", "error")
            return redirect(url_for("index"))

        insert_item(
            app,
            {
                "service_name": service_name,
                "environment": environment,
                "stage": stage,
                "status": status,
                "owner": owner,
                "reference_url": reference_url,
                "notes": notes,
            },
        )
        flash(f"Added {service_name} to the board.", "success")
        return redirect(url_for("index"))

    @app.post("/items/<int:item_id>/advance")
    def advance_item(item_id: int) -> Any:
        item = fetch_item(app, item_id)
        if not item:
            flash("That work item no longer exists.", "error")
            return redirect(url_for("index"))

        current_stage = item["stage"]
        current_index = STAGE_FLOW.index(current_stage) if current_stage in STAGE_FLOW else 0
        next_stage = STAGE_FLOW[min(current_index + 1, len(STAGE_FLOW) - 1)]
        next_status = item["status"]
        if next_stage == STAGE_FLOW[-1] and next_status == "In Progress":
            next_status = "Healthy"

        update_item(app, item_id, stage=next_stage, status=next_status)

        if next_stage == current_stage:
            flash(f"{item['service_name']} is already at the final stage.", "success")
        else:
            flash(f"Moved {item['service_name']} to {next_stage}.", "success")
        return redirect(url_for("index"))

    @app.post("/items/<int:item_id>/status")
    def update_item_status(item_id: int) -> Any:
        item = fetch_item(app, item_id)
        if not item:
            flash("That work item no longer exists.", "error")
            return redirect(url_for("index"))

        next_status = normalize_choice(request.form.get("status", ""), STATUS_OPTIONS, item["status"])
        update_item(app, item_id, status=next_status)
        flash(f"Updated {item['service_name']} to {next_status}.", "success")
        return redirect(url_for("index"))

    @app.post("/items/<int:item_id>/delete")
    def remove_item(item_id: int) -> Any:
        item = fetch_item(app, item_id)
        if item:
            delete_item(app, item_id)
            flash(f"Removed {item['service_name']} from the board.", "success")
        else:
            flash("That work item no longer exists.", "error")
        return redirect(url_for("index"))

    @app.get("/api/items")
    def api_items() -> Any:
        filters = {
            "environment": request.args.get("environment", ""),
            "stage": request.args.get("stage", ""),
            "status": request.args.get("status", ""),
        }
        items = fetch_items(app, filters)
        return jsonify({"items": items, "count": len(items), "refreshed_at": utc_label()})

    @app.get("/healthz")
    def healthz() -> Any:
        items = fetch_items(app)
        summary = build_summary(items)
        return jsonify(
            {
                "status": "ok",
                "tracked_services": summary["total"],
                "blocked": summary["blocked"],
                "in_progress": summary["in_progress"],
                "delivery_health": summary["delivery_health"],
                "time": utc_label(),
            }
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
