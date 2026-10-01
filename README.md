# Student Expense & Budget Planner

## Overview
A Flask web app where students record income and expenses, set monthly category budgets, track savings goals, and see charts, alerts and rule-based insights on a responsive finance dashboard.

## Problem Statement
Students live on limited, irregular money (allowance, scholarship, part-time pay) and often do not know where it goes until it runs out. This app makes spending visible and gives early warnings before budgets are broken.

## Objectives
- Record and categorize income and expenses
- Plan monthly budgets and monitor usage
- Track savings goals
- Visualize habits with charts and simple analysis
- Demonstrate practical data structures, CRUD, authentication and SQL

## Features
- **Authentication**: register, login, logout, hashed passwords (Werkzeug), Flask sessions, protected routes.
- **Dashboard**: six summary cards, latest 5 transactions, alerts.
- **Transactions**: add, edit, delete (with confirmation modal), search, filter (type, category, date, month), sort, undo.
- **Budget Planner**: per-category monthly budgets with spent, remaining, % used, progress bars, status (Safe under 75%, Warning 75-99%, Exceeded 100%+). Spending is calculated automatically from expenses.
- **Savings Goals**: add, edit, delete, add savings, progress bars.
- **Financial Analysis**: savings rate, expense ratio, budget utilization, top category, health score, recommendations.
- **Alerts**: budget at 75%, 90%, exceeded; goal nearly complete (90%+); month expenses above total monthly budget.
- **Charts** (Chart.js): expenses by category (doughnut), income vs expense (bar), monthly spending trend (line), all from database data.
- **Profile**: update name, change password.

## Data Structures Used
Search the code for `DATA STRUCTURE USAGE` (in `app.py`).

| Structure | Where and why |
|---|---|
| List | `get_transactions()` returns a list of dicts; budgets, goals and months are lists too. |
| Dictionary / Hash Map | `category_totals()` gives `{"Food": 3500, ...}` for O(1) budget lookup; `monthly_summary()` feeds the charts; `SORTS` maps sort names to fields. |
| Queue | `deque(maxlen=5)` keeps the 5 most recent transactions; `build_alerts()` enqueues alerts and dequeues them first-in-first-out. |
| Stack | `undo_stacks[user_id]` stores add/edit/delete actions; Undo pops the latest (LIFO). Held in server memory, so it resets when the server restarts. |
| Sorting | `sort_transactions()` sorts by date, amount or category. |
| Searching | `search_transactions()` linearly scans the list by text, type, category, date, month. |

## Technology Stack
Python, Flask, SQLite3, Jinja2, HTML5, CSS3, JavaScript, Bootstrap 5, Bootstrap Icons, Chart.js (Bootstrap and Chart.js load from a CDN, so an internet connection is needed).

## Folder Structure
```
student-expense-budget-planner/
├── app.py            routes, logic, data structures
├── database.py       schema, connection, demo data
├── requirements.txt
├── README.md
├── .gitignore
├── instance/         finance.db is created here on first run
├── screenshots/      add your screenshots here
├── static/css/style.css
├── static/js/main.js, charts.js
└── templates/
    base, login, register, dashboard, transactions, form,
    budget, goals, analysis, profile, 404, 500 (.html)
```
`form.html` is one shared form used for adding and editing transactions, budgets and goals.

## Database Schema
- **users**: id, full_name, email (unique), password_hash, created_at
- **transactions**: id, user_id (FK), description, amount (> 0), transaction_type (Income/Expense), category, transaction_date, notes, created_at
- **budgets**: id, user_id (FK), category, amount (> 0), month (1-12), year, created_at; unique per user/category/month/year
- **savings_goals**: id, user_id (FK), goal_name, target_amount, saved_amount, target_date, created_at

Indexes: transactions(user_id, date), budgets(user_id, year, month), savings_goals(user_id). All SQL is parameterized. Every read or write of user data filters by `user_id`, so changing a URL id returns 404.

## Financial Health Score (0-100, rule-based)
- Savings rate = (Income - Expenses) / Income x 100; Expense ratio = Expenses / Income x 100; Budget utilization = Spent / Budget x 100
- Score = Savings (40: full at 30%+, linear below) + Expense ratio (20: full at 70% or less, zero at 100%+) + Budget usage (20: full at average 75% or less, zero at 125%+) + Overspending (20 minus 10 per exceeded budget)
- With no budgets set, the two budget parts score 10 each.
- This is an educational formula, not financial advice. No AI/ML is used.

## Installation
```
git clone <repository-url>
cd student-expense-budget-planner
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Linux/macOS
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. Optional demo data: `python database.py --demo`, then log in as `demo@student.com` / `demo1234`. Demo data is never added to new accounts. Set the `SECRET_KEY` environment variable for anything beyond local use.

## Usage
1. Register, then 2. Log in.
3. Add income (Transactions > Add Transaction, type Income).
4. Add expenses the same way.
5. Budget Planner > Add budget, and watch progress bars update.
6. Savings Goals > Add goal, then add savings.
7. Open Analysis for scores and tips.

## Screenshots
Not generated yet. Add your own files to `screenshots/`:
- Login: `screenshots/login.png`
- Dashboard: `screenshots/dashboard.png`
- Transactions: `screenshots/transactions.png`
- Budget: `screenshots/budget.png`
- Goals: `screenshots/goals.png`
- Analysis: `screenshots/analysis.png`

## Future Enhancements
Expense prediction, receipt scanning, CSV/PDF export, recurring transactions, email notifications, advanced analytics, PWA/mobile support, CSRF tokens, persistent undo history.

## Academic Concepts Demonstrated
Data structures, CRUD, database management, authentication, backend and frontend development, data visualization, search and sorting.

## License
MIT License. Free to use, modify and share for learning.
