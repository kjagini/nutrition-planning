# Nutrition Planning App

A local web app for nutrition planning with an LLM-generated meal plan, live quantity balancing, and daily progress reporting.

## What it does

- Captures profile inputs: **height, weight, workout level**
- Lets you type the ingredients you currently have for **breakfast, lunch, dinner**
- Calls a backend LLM to generate ingredient quantities that target your daily calories and macros
- Supports live ingredient edits:
  - Example: change oats from 100g to 120g
  - Other ingredients in that meal auto-adjust to keep the meal and daily totals in-range
- Logs meals by date
- Builds a daily report showing:
  - goals met/unmet
  - completion score
  - improvement suggestions

## Project structure

- `nutrition_planner.py`: nutrition logic, plan generation, rebalancing, reporting
- `llm_planner.py`: backend LLM prompt + response parsing for ingredient quantity generation
- `app_server.py`: local API + static web server
- `web/index.html`: app shell
- `web/app.css`: modern responsive UI styling
- `web/app.js`: frontend state + API integration
- `tests/`: unit tests

## Configure LLM

Set your API key before starting the server:

```powershell
$env:OPENAI_API_KEY="your_api_key_here"
```

Optional model override:

```powershell
$env:OPENAI_MODEL="gpt-4.1-mini"
```

## Run the app

```bash
python app_server.py --port 8000
```

Then open: `http://127.0.0.1:8000`

## Run tests

```bash
python -m pytest -q
```

