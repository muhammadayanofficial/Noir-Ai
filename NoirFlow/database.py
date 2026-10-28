import os
import sqlite3
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = os.environ.get("NOIRFLOW_DATABASE", str(BASE_DIR / "noirflow.db"))


@contextmanager
def get_db():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(seed=True):
    with get_db() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                company TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                client_id INTEGER,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','On hold','Completed')),
                priority TEXT NOT NULL DEFAULT 'Normal' CHECK(priority IN ('Low','Normal','High','Urgent')),
                due_date TEXT,
                budget REAL NOT NULL DEFAULT 0,
                color TEXT NOT NULL DEFAULT '#c9a873',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo','in_progress','done')),
                priority TEXT NOT NULL DEFAULT 'Normal' CHECK(priority IN ('Low','Normal','High','Urgent')),
                due_date TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tag TEXT NOT NULL DEFAULT 'Personal',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS focus_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                duration_minutes INTEGER NOT NULL CHECK(duration_minutes > 0),
                note TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                entity TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        if seed and db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
            today = date.today()
            db.execute("INSERT INTO clients(name, company, email) VALUES (?, ?, ?)", ("Mira Khan", "Northstar Studio", "mira@example.com"))
            db.execute("INSERT INTO clients(name, company, email) VALUES (?, ?, ?)", ("Ethan Cole", "Fieldwork Goods", "ethan@example.com"))
            clients = db.execute("SELECT id FROM clients ORDER BY id").fetchall()
            c1, c2 = clients[0]["id"], clients[1]["id"]
            projects = [
                ("Northstar rebrand", c1, "A considered identity system for a growing digital studio.", "Active", "High", (today + timedelta(days=8)).isoformat(), 4800, "#d5b77b"),
                ("Fieldwork storefront", c2, "A calm, conversion-focused commerce experience.", "Active", "Urgent", (today + timedelta(days=4)).isoformat(), 6200, "#7db6a0"),
                ("Personal site refresh", None, "Portfolio and writing space refresh.", "On hold", "Normal", (today + timedelta(days=18)).isoformat(), 0, "#9c91d9"),
            ]
            db.executemany(
                "INSERT INTO projects(name,client_id,description,status,priority,due_date,budget,color) VALUES (?,?,?,?,?,?,?,?)",
                projects,
            )
            project_rows = db.execute("SELECT id, name FROM projects ORDER BY id").fetchall()
            p1, p2, p3 = [p["id"] for p in project_rows]
            tasks = [
                (p1, "Collect references and positioning notes", "Align on audience, category and visual territory.", "done", "Normal", (today - timedelta(days=1)).isoformat()),
                (p1, "Explore initial wordmark directions", "Create three directions before selecting a route.", "in_progress", "High", (today + timedelta(days=1)).isoformat()),
                (p1, "Prepare identity presentation", "Package the direction and rationale for review.", "todo", "Normal", (today + timedelta(days=5)).isoformat()),
                (p2, "Map storefront journeys", "Document the main collection and product flows.", "done", "High", (today - timedelta(days=2)).isoformat()),
                (p2, "Build product page concept", "Create a polished product page and mobile state.", "in_progress", "Urgent", (today + timedelta(days=2)).isoformat()),
                (p2, "Check checkout edge cases", "Review shipping, empty states and validation.", "todo", "High", (today + timedelta(days=3)).isoformat()),
                (p3, "Audit existing pages", "List content to keep, revise and remove.", "todo", "Low", (today + timedelta(days=14)).isoformat()),
            ]
            db.executemany(
                "INSERT INTO tasks(project_id,title,description,status,priority,due_date) VALUES (?,?,?,?,?,?)",
                tasks,
            )
            db.execute("INSERT INTO notes(title,body,tag) VALUES (?,?,?)", ("Design principle", "If every element is loud, nothing is important. Give the work room to breathe.", "Studio note"))
            db.execute("INSERT INTO notes(title,body,tag) VALUES (?,?,?)", ("Client handoff checklist", "Final files\nUsage notes\nExport sizes\nEditable source\nNext steps", "Checklist"))
            db.execute("INSERT INTO focus_sessions(project_id,duration_minutes,note) VALUES (?,?,?)", (p1, 25, "Reference research"))
            db.execute("INSERT INTO activity(action,entity) VALUES (?,?)", ("Workspace initialized", "NoirFlow"))
        db.commit()


def log_activity(action, entity):
    with get_db() as db:
        db.execute("INSERT INTO activity(action, entity) VALUES (?, ?)", (action, entity))
        db.commit()
