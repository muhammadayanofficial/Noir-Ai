import csv
import io
import os
from datetime import date

from dotenv import load_dotenv
from flask import Flask, flash, jsonify, make_response, redirect, render_template, request, url_for

load_dotenv()

import database
from database import get_db, init_db, log_activity

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "local-dev-key-change-before-sharing")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024

ALLOWED_VIEWS = {"overview", "projects", "tasks", "calendar", "focus", "notes", "clients"}
TASK_STATUSES = {"todo", "in_progress", "done"}
PROJECT_STATUSES = {"Active", "On hold", "Completed"}
PRIORITIES = {"Low", "Normal", "High", "Urgent"}


def clean_text(value, max_length=5000):
    return (value or "").strip()[:max_length]


def optional_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def normalize_date(value):
    raw = clean_text(value, 10)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def rows_as_dicts(rows):
    return [dict(row) for row in rows]


def page_data():
    with get_db() as db:
        clients = rows_as_dicts(db.execute("SELECT * FROM clients ORDER BY name COLLATE NOCASE").fetchall())
        projects = rows_as_dicts(db.execute(
            """SELECT p.*, c.name AS client_name,
                   (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id) AS task_count,
                   (SELECT COUNT(*) FROM tasks t WHERE t.project_id=p.id AND t.status='done') AS completed_count
               FROM projects p LEFT JOIN clients c ON c.id=p.client_id
               ORDER BY CASE p.status WHEN 'Active' THEN 0 WHEN 'On hold' THEN 1 ELSE 2 END, p.due_date IS NULL, p.due_date""").fetchall())
        tasks = rows_as_dicts(db.execute(
            """SELECT t.*, p.name AS project_name, p.color AS project_color
               FROM tasks t LEFT JOIN projects p ON p.id=t.project_id
               ORDER BY CASE t.status WHEN 'in_progress' THEN 0 WHEN 'todo' THEN 1 ELSE 2 END,
                        CASE t.priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Normal' THEN 2 ELSE 3 END,
                        t.due_date IS NULL, t.due_date, t.id DESC""").fetchall())
        notes = rows_as_dicts(db.execute("SELECT * FROM notes ORDER BY created_at DESC, id DESC LIMIT 12").fetchall())
        activity = rows_as_dicts(db.execute("SELECT * FROM activity ORDER BY id DESC LIMIT 7").fetchall())
        focus = db.execute("SELECT COALESCE(SUM(duration_minutes),0) AS minutes FROM focus_sessions WHERE date(completed_at)=date('now','localtime')").fetchone()["minutes"]
        week_focus = db.execute("SELECT COALESCE(SUM(duration_minutes),0) AS minutes FROM focus_sessions WHERE completed_at >= datetime('now','-7 days','localtime')").fetchone()["minutes"]
        focus_sessions = rows_as_dicts(db.execute(
            """SELECT f.*, p.name AS project_name FROM focus_sessions f
               LEFT JOIN projects p ON p.id=f.project_id ORDER BY f.id DESC LIMIT 6""").fetchall())
    today = date.today().isoformat()
    open_tasks = [t for t in tasks if t["status"] != "done"]
    overdue = [t for t in open_tasks if t.get("due_date") and t["due_date"] < today]
    due_soon = [t for t in open_tasks if t.get("due_date") and today <= t["due_date"] <= date.fromordinal(date.today().toordinal() + 7).isoformat()]
    for project in projects:
        project["progress"] = int((project["completed_count"] / project["task_count"]) * 100) if project["task_count"] else 0
    return {
        "clients": clients, "projects": projects, "tasks": tasks, "notes": notes,
        "activity": activity, "focus_today": focus, "focus_week": week_focus,
        "focus_sessions": focus_sessions, "open_tasks": open_tasks, "overdue": overdue,
        "due_soon": due_soon,
        "stats": {
            "active_projects": sum(1 for p in projects if p["status"] == "Active"),
            "open_tasks": len(open_tasks),
            "done_tasks": sum(1 for t in tasks if t["status"] == "done"),
            "overdue_tasks": len(overdue),
        },
    }


@app.route("/")
def index():
    view = request.args.get("view", "overview")
    if view not in ALLOWED_VIEWS:
        view = "overview"
    data = page_data()
    return render_template("index.html", current_view=view, today=date.today(), **data)


@app.route("/health")
def health():
    return jsonify({"status": "ok", "app": "NoirFlow Studio OS"})


@app.post("/projects/new")
def create_project():
    name = clean_text(request.form.get("name"), 120)
    if not name:
        flash("A project name is required.", "error")
        return redirect(url_for("index", view="projects"))
    client_id = optional_int(request.form.get("client_id"))
    raw_due_date = clean_text(request.form.get("due_date"), 10)
    due_date = normalize_date(raw_due_date)
    if raw_due_date and not due_date:
        flash("Please enter a valid project due date.", "error")
        return redirect(url_for("index", view="projects"))
    try:
        budget = max(0, float(request.form.get("budget") or 0))
    except ValueError:
        budget = 0
    priority = request.form.get("priority", "Normal")
    if priority not in PRIORITIES:
        priority = "Normal"
    description = clean_text(request.form.get("description"), 2000)
    color = request.form.get("color", "#d5b77b")
    if color not in {"#d5b77b", "#7db6a0", "#9c91d9", "#d98c7b", "#8fa9d6"}:
        color = "#d5b77b"
    with get_db() as db:
        if client_id and not db.execute("SELECT id FROM clients WHERE id=?", (client_id,)).fetchone():
            client_id = None
        db.execute("INSERT INTO projects(name,client_id,description,priority,due_date,budget,color) VALUES(?,?,?,?,?,?,?)",
                    (name, client_id, description, priority, due_date, budget, color))
        db.commit()
    log_activity("Project created", name)
    flash("Project created.", "success")
    return redirect(url_for("index", view="projects"))


@app.post("/projects/<int:project_id>/status")
def update_project_status(project_id):
    status = request.form.get("status", "Active")
    if status not in PROJECT_STATUSES:
        flash("Invalid project status.", "error")
        return redirect(url_for("index", view="projects"))
    with get_db() as db:
        changed = db.execute("UPDATE projects SET status=? WHERE id=?", (status, project_id)).rowcount
        db.commit()
    if changed:
        log_activity("Project status changed", f"Project #{project_id}: {status}")
        flash("Project status updated.", "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("index", view="projects"))


@app.post("/projects/<int:project_id>/delete")
def delete_project(project_id):
    with get_db() as db:
        row = db.execute("SELECT name FROM projects WHERE id=?", (project_id,)).fetchone()
        if row:
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            db.commit()
    if row:
        log_activity("Project deleted", row["name"])
        flash("Project deleted. Its tasks are now unassigned.", "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("index", view="projects"))


@app.post("/tasks/new")
def create_task():
    title = clean_text(request.form.get("title"), 180)
    if not title:
        flash("A task title is required.", "error")
        return redirect(url_for("index", view="tasks"))
    project_id = optional_int(request.form.get("project_id"))
    status = request.form.get("status", "todo")
    priority = request.form.get("priority", "Normal")
    if status not in TASK_STATUSES:
        status = "todo"
    if priority not in PRIORITIES:
        priority = "Normal"
    raw_due_date = clean_text(request.form.get("due_date"), 10)
    due_date = normalize_date(raw_due_date)
    if raw_due_date and not due_date:
        flash("Please enter a valid task due date.", "error")
        return redirect(url_for("index", view="tasks"))
    description = clean_text(request.form.get("description"), 2000)
    with get_db() as db:
        if project_id and not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            project_id = None
        db.execute("INSERT INTO tasks(project_id,title,description,status,priority,due_date) VALUES(?,?,?,?,?,?)",
                    (project_id, title, description, status, priority, due_date))
        db.commit()
    log_activity("Task added", title)
    flash("Task added to your workspace.", "success")
    return redirect(url_for("index", view="tasks"))


@app.post("/tasks/<int:task_id>/delete")
def delete_task(task_id):
    with get_db() as db:
        row = db.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row:
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            db.commit()
    if row:
        log_activity("Task deleted", row["title"])
        flash("Task deleted.", "success")
    return redirect(url_for("index", view="tasks"))


@app.post("/api/tasks/<int:task_id>/status")
def api_update_task_status(task_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = request.form
    status = payload.get("status")
    if not isinstance(status, str) or status not in TASK_STATUSES:
        return jsonify({"ok": False, "error": "Unsupported task status."}), 400
    with get_db() as db:
        row = db.execute("SELECT title FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Task not found."}), 404
        db.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        db.commit()
    log_activity("Task moved", f"{row['title']} → {status.replace('_', ' ')}")
    return jsonify({"ok": True, "status": status})


@app.post("/clients/new")
def create_client():
    name = clean_text(request.form.get("name"), 120)
    if not name:
        flash("A client name is required.", "error")
        return redirect(url_for("index", view="clients"))
    company = clean_text(request.form.get("company"), 160)
    email = clean_text(request.form.get("email"), 180)
    with get_db() as db:
        db.execute("INSERT INTO clients(name,company,email) VALUES(?,?,?)", (name, company, email))
        db.commit()
    log_activity("Client added", name)
    flash("Client added.", "success")
    return redirect(url_for("index", view="clients"))


@app.post("/clients/<int:client_id>/delete")
def delete_client(client_id):
    with get_db() as db:
        row = db.execute("SELECT name FROM clients WHERE id=?", (client_id,)).fetchone()
        if row:
            db.execute("DELETE FROM clients WHERE id=?", (client_id,))
            db.commit()
    if row:
        log_activity("Client removed", row["name"])
        flash("Client removed. Linked projects remain in the workspace.", "success")
    return redirect(url_for("index", view="clients"))


@app.post("/notes/new")
def create_note():
    title = clean_text(request.form.get("title"), 160)
    body = clean_text(request.form.get("body"), 6000)
    tag = clean_text(request.form.get("tag"), 50) or "Studio note"
    if not title:
        flash("A note title is required.", "error")
        return redirect(url_for("index", view="notes"))
    with get_db() as db:
        db.execute("INSERT INTO notes(title,body,tag) VALUES(?,?,?)", (title, body, tag))
        db.commit()
    log_activity("Note saved", title)
    flash("Note saved.", "success")
    return redirect(url_for("index", view="notes"))


@app.post("/notes/<int:note_id>/delete")
def delete_note(note_id):
    with get_db() as db:
        row = db.execute("SELECT title FROM notes WHERE id=?", (note_id,)).fetchone()
        if row:
            db.execute("DELETE FROM notes WHERE id=?", (note_id,))
            db.commit()
    if row:
        log_activity("Note deleted", row["title"])
        flash("Note deleted.", "success")
    return redirect(url_for("index", view="notes"))


@app.post("/api/focus")
def save_focus_session():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = request.form
    try:
        minutes = int(payload.get("duration_minutes", 0))
    except (ValueError, TypeError):
        minutes = 0
    if minutes < 1 or minutes > 600:
        return jsonify({"ok": False, "error": "Focus duration must be between 1 and 600 minutes."}), 400
    project_id = optional_int(payload.get("project_id"))
    note = clean_text(payload.get("note", "Focus session"), 300)
    with get_db() as db:
        if project_id and not db.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            project_id = None
        db.execute("INSERT INTO focus_sessions(project_id,duration_minutes,note) VALUES(?,?,?)", (project_id, minutes, note))
        db.commit()
    log_activity("Focus session logged", f"{minutes} min · {note or 'Deep work'}")
    return jsonify({"ok": True, "duration_minutes": minutes})


@app.post("/api/ai/plan")
def ai_project_plan():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return jsonify({"ok": False, "error": "Gemini is not configured yet. Add GEMINI_API_KEY to your .env file to enable project planning."}), 503
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        payload = {}
    project_id = optional_int(payload.get("project_id"))
    goal = clean_text(payload.get("goal"), 1200)
    with get_db() as db:
        project = db.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone() if project_id else None
    context = f"Project: {project['name']}\nDescription: {project['description']}\nDue date: {project['due_date']}\nPriority: {project['priority']}" if project else "No saved project selected."
    prompt = (
        "You are a practical project operations partner. Create a concise, realistic project plan. "
        "Return: 1) outcome, 2) milestones in sequence, 3) actionable tasks, 4) risks and dependencies, "
        "5) three clarifying questions. Do not invent client facts. Use Markdown and be specific.\n\n"
        f"{context}\nAdditional goal from user: {goal or 'Create a sensible next-step plan.'}"
    )
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        response = client.models.generate_content(model=model, contents=prompt)
        text = (getattr(response, "text", None) or "").strip()
        if not text:
            return jsonify({"ok": False, "error": "The model returned an empty response. Try a more specific goal."}), 502
        return jsonify({"ok": True, "text": text})
    except Exception:
        app.logger.exception("Gemini project planning failed")
        return jsonify({"ok": False, "error": "The AI request failed. Check the API key, model name, network connection and terminal log."}), 502


@app.get("/export/tasks.csv")
def export_tasks():
    with get_db() as db:
        rows = db.execute(
            """SELECT t.title,t.description,t.status,t.priority,t.due_date,p.name AS project
               FROM tasks t LEFT JOIN projects p ON p.id=t.project_id ORDER BY t.id"""
        ).fetchall()
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["Task", "Description", "Status", "Priority", "Due date", "Project"])
    writer.writerows([row[key] or "" for key in row.keys()] for row in rows)
    response = make_response("\ufeff" + output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=noirflow-tasks.csv"
    return response


init_db(seed=True)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
