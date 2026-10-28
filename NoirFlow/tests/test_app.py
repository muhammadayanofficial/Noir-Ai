import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import database
from app import app


class NoirFlowAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db = database.DATABASE_PATH
        database.DATABASE_PATH = str(Path(self.temp_dir.name) / "test_noirflow.db")
        database.init_db(seed=True)
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()

    def tearDown(self):
        database.DATABASE_PATH = self.original_db
        self.temp_dir.cleanup()

    def test_health_endpoint(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["status"], "ok")

    def test_overview_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Make room for", response.data)
        self.assertIn(b"task board", response.data)

    def test_create_project(self):
        response = self.client.post("/projects/new", data={
            "name": "Test launch", "priority": "High", "budget": "1200", "description": "Testing project creation"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with database.get_db() as db:
            row = db.execute("SELECT * FROM projects WHERE name='Test launch'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["priority"], "High")
        self.assertEqual(row["budget"], 1200)

    def test_create_task_and_change_status(self):
        with database.get_db() as db:
            project_id = db.execute("SELECT id FROM projects ORDER BY id LIMIT 1").fetchone()["id"]
        response = self.client.post("/tasks/new", data={
            "title": "Ship a test", "project_id": str(project_id), "priority": "Urgent", "status": "todo"
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        with database.get_db() as db:
            task = db.execute("SELECT id FROM tasks WHERE title='Ship a test'").fetchone()
        self.assertIsNotNone(task)
        update = self.client.post(f"/api/tasks/{task['id']}/status", json={"status": "in_progress"})
        self.assertEqual(update.status_code, 200)
        self.assertTrue(update.json["ok"])
        with database.get_db() as db:
            saved = db.execute("SELECT status FROM tasks WHERE id=?", (task["id"],)).fetchone()
        self.assertEqual(saved["status"], "in_progress")

    def test_invalid_task_status_rejected(self):
        with database.get_db() as db:
            task_id = db.execute("SELECT id FROM tasks ORDER BY id LIMIT 1").fetchone()["id"]
        response = self.client.post(f"/api/tasks/{task_id}/status", json={"status": "drop_database"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["ok"])

    def test_csv_export_contains_expected_columns(self):
        response = self.client.get("/export/tasks.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.content_type)
        self.assertIn(b"Task,Description,Status,Priority,Due date,Project", response.data)

    def test_ai_endpoint_explains_missing_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            response = self.client.post("/api/ai/plan", json={"goal": "Plan a launch"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("GEMINI_API_KEY", response.json["error"])


if __name__ == "__main__":
    unittest.main()
