# NoirFlow Studio OS

NoirFlow is a local-first project and creative-work management workspace built with Python, Flask, SQLite, HTML, CSS and vanilla JavaScript. It uses an obsidian-and-champagne visual system with editorial serif and script typography accents.

## Features

- **Studio overview:** current workload, project progress, task board, upcoming dates and recent focus time.
- **Projects:** create projects, associate clients, set priority and deadlines, track task completion, update status and delete projects.
- **Kanban tasks:** drag tasks between To do, In progress and Completed; task status is persisted to SQLite. Search and filter tasks, set due dates and priorities, and export task data to CSV.
- **Deadline calendar:** monthly calendar with task and project deadline markers plus a sorted upcoming-deadlines list.
- **Focus room:** 25-, 50- and 90-minute timer options, optional project selection, automatic focus-session logging and recent session history.
- **Notebook:** create and delete studio notes, ideas, checklists and reminders.
- **Client directory:** save contacts and link them to projects.
- **Optional Gemini planning:** ask Gemini for project milestones, task breakdowns, dependencies, risks and clarifying questions. This feature requires an API key; the app does not fabricate an AI response if it is not configured.
- **Seeded sample workspace:** first run includes sample projects, tasks, contacts and notes to help you explore the UI. Replace these with your own information.

## Run on Windows / VS Code

1. Extract the ZIP and open the `NoirFlow` folder in VS Code.
2. Open the VS Code terminal in that folder.
3. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   If PowerShell blocks activation, use Command Prompt and run `.venv\Scripts\activate.bat`, or run `.venv\Scripts\python.exe` directly.

4. Install the dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

5. Copy `.env.example` to `.env`. Generate a unique local secret key:

   ```powershell
   py -c "import secrets; print(secrets.token_hex(32))"
   ```

   Paste the result after `SECRET_KEY=` in `.env`.

6. Start the app:

   ```powershell
   python app.py
   ```

7. Open `http://127.0.0.1:5000` in your browser.

The SQLite database is created as `noirflow.db` in the project folder on first run. Keep that file if you want to keep your workspace data; back it up before moving or upgrading the project.

## Enable Gemini planning (optional)

1. Add your Gemini API key to the `GEMINI_API_KEY` value in `.env`.
2. You can change `GEMINI_MODEL` there if your account supports a different model.
3. Restart the Flask server, open **Projects**, choose a project in the AI planning area and generate a plan.

The AI endpoint sends project details and your planning prompt to Gemini. Do not submit confidential client information unless you are comfortable sending it to your configured model provider. The browser never receives the API key.

## Run tests

```powershell
python -m unittest discover -s tests -v
```

Tests use a temporary SQLite database and do not change your local workspace database.

## Notes and limitations

- NoirFlow is a local prototype intended for a portfolio and individual use, not a secured multi-user SaaS deployment. Do not expose the development server to the public internet as-is.
- The demo does not include authentication, online sync, calendar-provider integration, email delivery or invoicing.
- Focus time is stored when a timed session completes. Closing the browser or stopping the server mid-session will not log that interrupted session.
- Fonts are loaded from Google Fonts when internet access is available; local fallback fonts keep the app readable if they cannot be loaded.
- The seeded client and project details are fictional demo data.
