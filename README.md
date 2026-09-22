# Farm Management System (FarmOS)

A desktop farm-management application built with Python and CustomTkinter. It tracks
crops, inventory, sales and expenses, visualizes performance, pulls live weather and a
5-day forecast, and uses Google Gemini AI for farm advice, a tool-calling assistant that
can update records, bill scanning, leaf-disease diagnosis and automatic crop calendars.

The app works fully offline: every AI feature has a deterministic fallback, so it stays
useful even without an API key or internet connection.

## Features

### Core
- **Dashboard** - live stat cards (Active Crops, Inventory, Sales, Expenses, Net Profit),
  alert banner, weather card, AI recommended actions, upcoming tasks, profit by crop and
  recent activity.
- **Crops** - add, edit and delete crops with area, planting date, status
  (Planted / Growing / Ready / Harvested), expected harvest date with countdown and
  per-crop profit.
- **Inventory** - track supplies and equipment with reorder thresholds and automatic
  low-stock flags.
- **Sales** - record revenue linked to a crop, with search, date-range filters, sorting
  and CSV / PDF export.
- **Expenses** - record costs by category linked to a crop, with the same filtering,
  sorting and export options.
- **Dashboard charts** - Matplotlib visualizations of monthly sales vs expenses,
  expense-category mix and profit by crop, shown alongside the farm summary.

### AI-powered
- **Tool-calling agent** - the assistant can read your farm (sales, crops, per-crop profit)
  and act on it. Write requests (add sale / expense / crop) are shown as a confirmation
  card and are only saved after you approve them. Natural-language entry works too:
  "sold 40 kg onions at 22 yesterday" is parsed into a sale.
- **Persistent chat history** - conversations are stored per user in the database and
  reloaded on the next visit, with the last turns fed back as context.
- **Multilingual replies and voice input** - pick English, Hindi, Marathi or Telugu for
  replies and dictate messages with the microphone button (SpeechRecognition).
- **Forecast-aware alerts** - the 5-day forecast is combined with crop stage and calendar
  tasks, e.g. "Rain on Thursday, postpone the fertilizer task for tomatoes", and
  rain-affected task chips are flagged on the dashboard.
- **Bill / receipt scanning** - photograph a purchase bill and Gemini vision extracts the
  category, amount, date and description into the Expenses form.
- **Crop disease diagnosis** - upload a leaf photo to get the likely problem, severity,
  treatment and confidence. Results are logged against the crop. Uncertain cases return a
  "not sure, consult an agronomist" fallback instead of overclaiming.
- **Auto crop calendar** - adding a crop with a planting date generates a dated schedule
  of irrigation, fertilizer, pest-check and harvest tasks, stored and surfaced on the
  dashboard.

### Platform
- Login and registration with bcrypt-hashed passwords.
- Live weather with rule-based farming advice (irrigation, spraying, heat, cold, humidity).

## Tech Stack

| Concern | Choice |
|---|---|
| Language | Python 3.10+ (developed on 3.14) |
| GUI | CustomTkinter (`customtkinter`), Tkinter file dialogs |
| Database | SQLite (stdlib `sqlite3`), single file `farm.db` |
| AI | `google-generativeai` (Gemini) |
| Images | Pillow |
| Dashboard charts | Matplotlib |
| Export | stdlib `csv`, ReportLab (PDF) |
| Weather | OpenWeatherMap REST via `requests` |
| Voice | `SpeechRecognition` (Google Web Speech); PyAudio or `sounddevice` + `numpy` for mic capture |
| Auth | `bcrypt` |

## Project Structure

```
FarmMangementSystem/
├── ui.py          Presentation layer: window, pages, dialogs, widgets
├── ai_engine.py   AI/domain layer: agent, chat, insights, vision, calendars, forecast alerts
├── db.py          Data layer: schema, migrations, CRUD, analytics
├── weather.py     Integration: OpenWeatherMap fetch and farming tips
├── seed_db.py     Demo data seeder
├── farm.db        SQLite database (created on first run)
└── README.md
```

Dependencies flow one way: `ui.py` -> `ai_engine.py` -> `db.py` / `weather.py`. The data
and AI layers can be used and tested without the GUI.

## Architecture

```
ui.py (Presentation)
  |-- global app window + login screen
  |-- one build_*_page() per screen, shared widget helpers
  |-- network work on background threads, app.after() returns to UI
        |
        v
ai_engine.py (AI / domain)          weather.py (integration)
  agent, chat, insights, vision,      OpenWeatherMap current + forecast,
  calendar, forecast alerts          rule-based advice
        |
        v
db.py (data access)
  SQLite schema, migrations, CRUD, analytics
```

- Pages are built once and stacked; navigation raises the selected page.
- Each page registers a refresh callback so other pages can trigger updates.
- Schema changes are applied through non-destructive migrations, so existing data is
  preserved when the app is upgraded.

## Database Schema

| Table | Key columns | Purpose |
|---|---|---|
| `crops` | name, area, planting_date, status, expected_harvest_date | Crop records |
| `inventory` | item_name, quantity, unit, reorder_threshold | Supplies and equipment |
| `sales` | crop_name, quantity, price, sale_date, crop_id | Revenue |
| `expenses` | category, amount, expense_date, description, crop_id | Costs |
| `users` | username, password_hash | Authentication |
| `crop_tasks` | crop_id, crop_name, task_type, title, due_date, notes, done | AI crop calendar |
| `diagnoses` | crop_id, crop_name, image_path, problem, severity, treatment, consult_agronomist | Leaf-photo diagnoses |
| `chat_messages` | username, role, text, created_at | Per-user AI chat history |

`crop_id` links sales and expenses to crops, which powers the per-crop profit figures.
Low stock is derived from `quantity <= reorder_threshold`.

## Getting Started

### Prerequisites
- Python 3.10 or newer
- pip

### Install

```bash
pip install customtkinter google-generativeai pillow matplotlib reportlab requests bcrypt SpeechRecognition sounddevice numpy
```

Voice input needs a working microphone. `PyAudio` is used when installed; otherwise the
app falls back to `sounddevice`. Both are optional - the rest of the app works without them.

### Optional: sample data

```bash
python seed_db.py
```

This creates a demo user and sample crops, inventory, sales and expenses.

### Run

```bash
python ui.py
```

The database file `farm.db` is created automatically on first launch.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | No | Enables Gemini chat, the tool-calling agent, bill scanning and photo diagnosis. Without it, the app uses offline fallbacks. |
| `GEMINI_MODEL` | No | Overrides the default model (`gemini-1.5-flash`). |

Windows (PowerShell):

```powershell
$env:GEMINI_API_KEY = "your-key-here"
python ui.py
```

The weather module uses OpenWeatherMap and currently reads its key from `weather.py`.

## Usage

1. Launch the app and log in or create an account. The seeded demo account is
   `yaswanth` / `12345678`.
2. Add crops, inventory, sales and expenses from their pages.
3. Link sales and expenses to a crop to get accurate per-crop profit.
4. Open **AI Assistant** to ask questions, type requests like "sold 40 kg onions at 22
   yesterday", or tap the microphone. When the assistant proposes a change, review the
   confirmation card and approve or cancel it. Use the language selector for
   Hindi / Marathi / Telugu replies.
5. Use the camera actions on a crop row for diagnosis and calendar management.
6. Use the export buttons on the Sales and Expenses pages to save CSV or PDF reports.

## How It Works

- **Startup** - `db.init_db()` creates or migrates the schema, then the login screen is
  shown.
- **Navigation** - selecting a menu item refreshes the page and raises it; all pages
  share a `refresh_callbacks` registry.
- **AI requests** - input is collected, the button is disabled, and a worker thread calls
  `ai_engine`; the result is delivered back to the UI thread with `app.after`.
- **Agent** - `agent_reply()` runs a Gemini function-calling loop. Read tools are executed
  inline; write tools are returned as pending actions that the UI renders as a
  confirmation card, and `execute_pending_action()` runs only after approval.
- **Chat history** - messages are stored in `chat_messages` and the last turns are passed
  back into the agent as context.
- **Voice** - the microphone button records audio (PyAudio or `sounddevice`) and
  `transcribe_speech()` recognises it with `recognize_google` in the selected language.
- **Forecast** - the 5-day forecast is cached for 15 minutes; `build_forecast_alerts()`
  cross-references it with crop stage and calendar tasks for the dashboard and insights.
- **Bill scan** - file picker -> `scan_receipt()` -> parsed fields written into the
  Expenses form for confirmation.
- **Diagnosis** - file picker -> `diagnose_crop_disease()` -> result card, then logged to
  the `diagnoses` table.
- **Calendar** - on crop creation (or regenerate), `generate_crop_calendar()` runs in the
  background and stores tasks; the dashboard shows tasks due within 14 days.
- **Weather** - fetched from OpenWeatherMap and cached for 15 minutes.

## Offline Behavior

Without `GEMINI_API_KEY` or a network connection:

- Chat and insights use a local rule-based analysis engine.
- The agent falls back to a lightweight parser, so phrases like "sold 40 kg onions at 22
  yesterday" still produce a confirmable sale card.
- Crop calendars use a deterministic template based on crop type and planting date.
- Disease diagnosis returns the "consult an agronomist" fallback.
- Bill scanning reports that a key is required, since OCR needs vision.
- Voice input requires an internet connection (Google Web Speech) and a microphone.

## Limitations

- The OpenWeatherMap API key is hard-coded in `weather.py` and should be moved to an
  environment variable.
- The Gemini function-calling loop is only exercised when `GEMINI_API_KEY` is set; offline
  it uses the parser fallback.
- Voice capture uses `sounddevice` when PyAudio is unavailable (PyAudio does not build on
  Python 3.14 yet).
- Diagnoses, crop tasks and chat history are not yet included in CSV / PDF export.
- Runs from source; there is no packaging or build script.
