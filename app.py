"""Student Expense & Budget Planner - Flask application."""
import math
import os
import re
import sqlite3
from collections import deque
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import database as db

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

CATEGORIES = ["Food", "Travel", "Education", "Shopping", "Entertainment", "Rent / Hostel",
              "Bills", "Health", "Personal", "Scholarship", "Part-Time Income", "Other"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# DATA STRUCTURE USAGE (Stack): last actions per user, popped by Undo (LIFO).
undo_stacks = {}


# ---------------------------------------------------------------- helpers
def query(sql, args=(), one=False):
    conn = db.get_db()
    rows = conn.execute(sql, args).fetchall()
    conn.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    conn = db.get_db()
    with conn:
        cur = conn.execute(sql, args)
    conn.close()
    return cur.lastrowid


def login_required(view):
    @wraps(view)
    def wrapped(*a, **kw):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*a, **kw)
    return wrapped


@app.template_filter("inr")
def inr(v):
    return "₹{:,.2f}".format(v or 0)


@app.context_processor
def inject_globals():
    return {"today": date.today().isoformat(), "undo_available": bool(undo_stacks.get(session.get("user_id")))}


def to_amount(v, errs, label="Amount", allow_zero=False):
    try:
        a = float(v)
    except (TypeError, ValueError):
        errs.append(f"{label} must be a number.")
        return None
    if not math.isfinite(a) or a < 0 or (a == 0 and not allow_zero):
        errs.append(f"{label} must be {'zero or more' if allow_zero else 'greater than zero'}.")
        return None
    return round(a, 2)


def valid_date(v, errs, label="Date"):
    try:
        datetime.strptime(v or "", "%Y-%m-%d")
        return v
    except ValueError:
        errs.append(f"{label} must be a valid date.")


def month_key(d=None):
    d = d or date.today()
    return f"{d.year}-{d.month:02d}"


def last_months(n=6):
    y, m, out = date.today().year, date.today().month, []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out[::-1]


def owned(table, row_id):
    """Fetch a row only if it belongs to the logged-in user, else 404 (authorization)."""
    row = query(f"SELECT * FROM {table} WHERE id=? AND user_id=?", (row_id, session["user_id"]), one=True)
    if row is None:
        abort(404)
    return row


# ------------------------------------------------- data-structure helpers
def get_transactions(uid):
    # DATA STRUCTURE USAGE (List): transactions are a list of dictionaries.
    return [dict(r) for r in query("SELECT * FROM transactions WHERE user_id=?", (uid,))]


# DATA STRUCTURE USAGE (Dictionary): sort option -> (field, reverse) lookup table.
SORTS = {"latest": ("transaction_date", True), "oldest": ("transaction_date", False),
         "high": ("amount", True), "low": ("amount", False), "category": ("category", False)}


def sort_transactions(txs, key):
    """DATA STRUCTURE USAGE (Sorting): sort the list by date, amount or category."""
    field, rev = SORTS.get(key, SORTS["latest"])
    return sorted(txs, key=lambda t: (t[field], t["id"]), reverse=rev)


def search_transactions(txs, text="", ttype="", cat="", day="", month=""):
    """DATA STRUCTURE USAGE (Searching): linear search through the list."""
    text, found = text.lower().strip(), []
    for t in txs:
        if text and text not in t["description"].lower() and text not in (t["notes"] or "").lower():
            continue
        if ttype and t["transaction_type"] != ttype:
            continue
        if cat and t["category"] != cat:
            continue
        if day and t["transaction_date"] != day:
            continue
        if month and not t["transaction_date"].startswith(month):
            continue
        found.append(t)
    return found


def category_totals(txs, month=None):
    """DATA STRUCTURE USAGE (Hash Map): {"Food": 3500, "Travel": 1200}."""
    totals = {}
    for t in txs:
        if t["transaction_type"] == "Expense" and (not month or t["transaction_date"].startswith(month)):
            totals[t["category"]] = totals.get(t["category"], 0) + t["amount"]
    return totals


def monthly_summary(txs, months):
    """DATA STRUCTURE USAGE (Hash Map): {"2025-01": {"Income": x, "Expense": y}}."""
    summary = {m: {"Income": 0, "Expense": 0} for m in months}
    for t in txs:
        ym = t["transaction_date"][:7]
        if ym in summary:
            summary[ym][t["transaction_type"]] += t["amount"]
    return summary


def budget_rows(uid, year, month, spent):
    """Budgets with spending looked up from the category_totals dictionary."""
    rows = []
    for b in query("SELECT * FROM budgets WHERE user_id=? AND year=? AND month=? ORDER BY category", (uid, year, month)):
        b = dict(b)
        b["spent"] = spent.get(b["category"], 0)
        b["remaining"] = b["amount"] - b["spent"]
        b["pct"] = round(b["spent"] / b["amount"] * 100, 1)
        b["status"], b["color"] = (("Exceeded", "danger") if b["pct"] >= 100 else
                                   ("Warning", "warning") if b["pct"] >= 75 else ("Safe", "success"))
        rows.append(b)
    return rows


def goal_rows(uid):
    goals = []
    for g in query("SELECT * FROM savings_goals WHERE user_id=? ORDER BY target_date", (uid,)):
        g = dict(g)
        g["pct"] = round(min(100, g["saved_amount"] / g["target_amount"] * 100), 1)
        goals.append(g)
    return goals


def build_alerts(budgets, goals, month_expense):
    """DATA STRUCTURE USAGE (Queue): alerts are enqueued, then processed first-in-first-out."""
    pending = deque()
    for b in budgets:
        if b["pct"] >= 100:
            pending.append(("danger", f"{b['category']} budget exceeded ({b['pct']:.0f}% used)."))
        elif b["pct"] >= 90:
            pending.append(("warning", f"{b['category']} budget reached 90% ({b['pct']:.0f}% used)."))
        elif b["pct"] >= 75:
            pending.append(("info", f"{b['category']} budget reached 75% ({b['pct']:.0f}% used)."))
    for g in goals:
        if 90 <= g["pct"] < 100:
            pending.append(("success", f"Savings goal '{g['goal_name']}' is nearly complete ({g['pct']:.0f}%)."))
    total_budget = sum(b["amount"] for b in budgets)
    if total_budget and month_expense > total_budget:
        pending.append(("danger", f"This month's expenses ({inr(month_expense)}) are above your total monthly budget ({inr(total_budget)})."))
    processed = []
    while pending:
        processed.append(pending.popleft())
    return processed


def push_undo(uid, action):
    stack = undo_stacks.setdefault(uid, [])
    stack.append(action)  # push
    del stack[:-20]


# ------------------------------------------------------------------- auth
@app.route("/")
def index():
    return redirect(url_for("dashboard" if "user_id" in session else "login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        name, email = f.get("full_name", "").strip(), f.get("email", "").strip().lower()
        pw, pw2 = f.get("password", ""), f.get("confirm_password", "")
        errs = []
        if not name:
            errs.append("Full name is required.")
        if not EMAIL_RE.match(email):
            errs.append("Enter a valid email address.")
        if len(pw) < 6:
            errs.append("Password must be at least 6 characters.")
        if pw != pw2:
            errs.append("Passwords do not match.")
        if not errs and query("SELECT 1 FROM users WHERE email=?", (email,), one=True):
            errs.append("An account with this email already exists.")
        if errs:
            for e in errs:
                flash(e, "danger")
            return render_template("register.html", form=f)
        execute("INSERT INTO users (full_name,email,password_hash) VALUES (?,?,?)",
                (name, email, generate_password_hash(pw)))
        flash("Account created. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        user = query("SELECT * FROM users WHERE email=?", (email,), one=True)
        if user and check_password_hash(user["password_hash"], request.form.get("password", "")):
            session.clear()
            session["user_id"], session["user_name"] = user["id"], user["full_name"]
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# -------------------------------------------------------------- dashboard
@app.route("/dashboard")
@login_required
def dashboard():
    uid, today_ = session["user_id"], date.today()
    txs = get_transactions(uid)
    income = sum(t["amount"] for t in txs if t["transaction_type"] == "Income")
    expense = sum(t["amount"] for t in txs if t["transaction_type"] == "Expense")
    ym = month_key()
    cat_month = category_totals(txs, ym)
    month_expense = sum(cat_month.values())
    budgets = budget_rows(uid, today_.year, today_.month, cat_month)
    goals = goal_rows(uid)
    monthly_budget = sum(b["amount"] for b in budgets)

    # DATA STRUCTURE USAGE (Queue): bounded deque holds the 5 most recent transactions.
    recent = deque(maxlen=5)
    for t in sorted(txs, key=lambda t: (t["transaction_date"], t["id"])):
        recent.appendleft(t)

    months = last_months(6)
    summary = monthly_summary(txs, months)
    chart = {"categories": {"labels": list(cat_month), "values": [round(v, 2) for v in cat_month.values()]},
             "months": [MONTHS[int(m[5:]) - 1][:3] for m in months],
             "income": [summary[m]["Income"] for m in months],
             "expense": [summary[m]["Expense"] for m in months]}
    stats = {"income": income, "expense": expense, "balance": income - expense, "budget": monthly_budget,
             "remaining": monthly_budget - month_expense, "savings": sum(g["saved_amount"] for g in goals)}
    return render_template("dashboard.html", stats=stats, recent=list(recent), chart=chart,
                           alerts=build_alerts(budgets, goals, month_expense))


# ----------------------------------------------------------- transactions
def tx_fields():
    return [{"name": "description", "label": "Description", "type": "text"},
            {"name": "amount", "label": "Amount (₹)", "type": "number", "step": "0.01"},
            {"name": "transaction_type", "label": "Type", "type": "select", "options": [("Income", "Income"), ("Expense", "Expense")]},
            {"name": "category", "label": "Category", "type": "select", "options": [(c, c) for c in CATEGORIES]},
            {"name": "transaction_date", "label": "Date", "type": "date"},
            {"name": "notes", "label": "Notes (optional)", "type": "textarea", "optional": True}]


def parse_tx(f):
    errs, desc = [], f.get("description", "").strip()
    if not desc:
        errs.append("Description is required.")
    amount = to_amount(f.get("amount"), errs)
    if f.get("transaction_type") not in ("Income", "Expense"):
        errs.append("Choose Income or Expense.")
    if f.get("category") not in CATEGORIES:
        errs.append("Choose a valid category.")
    dt = valid_date(f.get("transaction_date"), errs)
    return (desc, amount, f.get("transaction_type"), f.get("category"), dt, f.get("notes", "").strip()), errs


@app.route("/transactions")
@login_required
def transactions():
    a = request.args
    txs = get_transactions(session["user_id"])
    shown = sort_transactions(search_transactions(txs, a.get("q", ""), a.get("type", ""), a.get("category", ""),
                                                  a.get("date", ""), a.get("month", "")), a.get("sort", "latest"))
    return render_template("transactions.html", txs=shown, args=a, categories=CATEGORIES, total=len(txs))


@app.route("/transactions/add", methods=["GET", "POST"])
@login_required
def add_transaction():
    if request.method == "POST":
        vals, errs = parse_tx(request.form)
        if not errs:
            tid = execute("INSERT INTO transactions (description,amount,transaction_type,category,transaction_date,notes,user_id) "
                          "VALUES (?,?,?,?,?,?,?)", vals + (session["user_id"],))
            push_undo(session["user_id"], ("add", tid))
            flash("Transaction added.", "success")
            return redirect(url_for("transactions"))
        for e in errs:
            flash(e, "danger")
        return render_template("form.html", title="Add transaction", fields=tx_fields(), vals=request.form, back=url_for("transactions"))
    return render_template("form.html", title="Add transaction", fields=tx_fields(),
                           vals={"transaction_type": "Expense", "transaction_date": date.today().isoformat()}, back=url_for("transactions"))


@app.route("/transactions/<int:tid>/edit", methods=["GET", "POST"])
@login_required
def edit_transaction(tid):
    row = owned("transactions", tid)
    if request.method == "POST":
        vals, errs = parse_tx(request.form)
        if not errs:
            push_undo(session["user_id"], ("edit", dict(row)))
            execute("UPDATE transactions SET description=?,amount=?,transaction_type=?,category=?,transaction_date=?,notes=? "
                    "WHERE id=? AND user_id=?", vals + (tid, session["user_id"]))
            flash("Transaction updated.", "success")
            return redirect(url_for("transactions"))
        for e in errs:
            flash(e, "danger")
        row = request.form
    return render_template("form.html", title="Edit transaction", fields=tx_fields(), vals=row, back=url_for("transactions"))


@app.route("/transactions/<int:tid>/delete", methods=["POST"])
@login_required
def delete_transaction(tid):
    row = owned("transactions", tid)
    execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tid, session["user_id"]))
    push_undo(session["user_id"], ("delete", dict(row)))
    flash("Transaction deleted. You can undo this.", "info")
    return redirect(url_for("transactions"))


@app.route("/transactions/undo", methods=["POST"])
@login_required
def undo():
    uid, stack = session["user_id"], undo_stacks.get(session["user_id"])
    if not stack:
        flash("Nothing to undo.", "warning")
        return redirect(url_for("transactions"))
    kind, data = stack.pop()  # DATA STRUCTURE USAGE (Stack): pop the most recent action
    if kind == "add":
        execute("DELETE FROM transactions WHERE id=? AND user_id=?", (data, uid))
    elif kind == "delete":
        execute("INSERT INTO transactions (id,user_id,description,amount,transaction_type,category,transaction_date,notes) "
                "VALUES (?,?,?,?,?,?,?,?)", (data["id"], uid, data["description"], data["amount"], data["transaction_type"],
                                             data["category"], data["transaction_date"], data["notes"]))
    else:
        execute("UPDATE transactions SET description=?,amount=?,transaction_type=?,category=?,transaction_date=?,notes=? "
                "WHERE id=? AND user_id=?", (data["description"], data["amount"], data["transaction_type"], data["category"],
                                             data["transaction_date"], data["notes"], data["id"], uid))
    flash(f"Undid last action ({kind}).", "success")
    return redirect(url_for("transactions"))


# ---------------------------------------------------------------- budgets
def budget_fields():
    return [{"name": "category", "label": "Category", "type": "select", "options": [(c, c) for c in CATEGORIES]},
            {"name": "amount", "label": "Budget amount (₹)", "type": "number", "step": "0.01"},
            {"name": "month", "label": "Month", "type": "select", "options": [(str(i + 1), m) for i, m in enumerate(MONTHS)]},
            {"name": "year", "label": "Year", "type": "number", "step": "1"}]


def parse_budget(f):
    errs = []
    amount = to_amount(f.get("amount"), errs, "Budget amount")
    if f.get("category") not in CATEGORIES:
        errs.append("Choose a valid category.")
    try:
        month, year = int(f.get("month")), int(f.get("year"))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except (TypeError, ValueError):
        errs.append("Enter a valid month and year.")
        month = year = None
    return (f.get("category"), amount, month, year), errs


@app.route("/budget")
@login_required
def budget():
    uid, t = session["user_id"], date.today()
    month = request.args.get("month", type=int) or t.month
    year = request.args.get("year", type=int) or t.year
    if not 1 <= month <= 12:
        month = t.month
    spent = category_totals(get_transactions(uid), f"{year}-{month:02d}")
    return render_template("budget.html", budgets=budget_rows(uid, year, month, spent), month=month, year=year, months=MONTHS)


def save_budget(bid=None, title=""):
    uid = session["user_id"]
    if request.method == "POST":
        vals, errs = parse_budget(request.form)
        if not errs:
            try:
                if bid:
                    execute("UPDATE budgets SET category=?,amount=?,month=?,year=? WHERE id=? AND user_id=?", vals + (bid, uid))
                else:
                    execute("INSERT INTO budgets (category,amount,month,year,user_id) VALUES (?,?,?,?,?)", vals + (uid,))
                flash("Budget saved.", "success")
                return redirect(url_for("budget", month=vals[2], year=vals[3]))
            except sqlite3.IntegrityError:
                errs.append("A budget for that category and month already exists. Edit it instead.")
        for e in errs:
            flash(e, "danger")
        vals = request.form
    else:
        vals = dict(owned("budgets", bid)) if bid else {"month": str(date.today().month), "year": date.today().year}
    return render_template("form.html", title=title, fields=budget_fields(), vals=vals, back=url_for("budget"))


@app.route("/budget/add", methods=["GET", "POST"])
@login_required
def add_budget():
    return save_budget(title="Add budget")


@app.route("/budget/<int:bid>/edit", methods=["GET", "POST"])
@login_required
def edit_budget(bid):
    owned("budgets", bid)
    return save_budget(bid, "Edit budget")


@app.route("/budget/<int:bid>/delete", methods=["POST"])
@login_required
def delete_budget(bid):
    owned("budgets", bid)
    execute("DELETE FROM budgets WHERE id=? AND user_id=?", (bid, session["user_id"]))
    flash("Budget deleted.", "info")
    return redirect(url_for("budget"))


# ------------------------------------------------------------------ goals
def goal_fields():
    return [{"name": "goal_name", "label": "Goal name", "type": "text"},
            {"name": "target_amount", "label": "Target amount (₹)", "type": "number", "step": "0.01"},
            {"name": "saved_amount", "label": "Saved so far (₹)", "type": "number", "step": "0.01"},
            {"name": "target_date", "label": "Target date", "type": "date"}]


def save_goal(gid=None, title=""):
    uid = session["user_id"]
    if request.method == "POST":
        f, errs = request.form, []
        name = f.get("goal_name", "").strip()
        if not name:
            errs.append("Goal name is required.")
        target = to_amount(f.get("target_amount"), errs, "Target amount")
        saved = to_amount(f.get("saved_amount") or 0, errs, "Saved amount", allow_zero=True)
        tdate = valid_date(f.get("target_date"), errs, "Target date")
        if not errs:
            vals = (name, target, saved, tdate)
            if gid:
                execute("UPDATE savings_goals SET goal_name=?,target_amount=?,saved_amount=?,target_date=? WHERE id=? AND user_id=?", vals + (gid, uid))
            else:
                execute("INSERT INTO savings_goals (goal_name,target_amount,saved_amount,target_date,user_id) VALUES (?,?,?,?,?)", vals + (uid,))
            flash("Goal saved.", "success")
            return redirect(url_for("goals"))
        for e in errs:
            flash(e, "danger")
        vals = f
    else:
        vals = dict(owned("savings_goals", gid)) if gid else {"saved_amount": 0}
    return render_template("form.html", title=title, fields=goal_fields(), vals=vals, back=url_for("goals"))


@app.route("/goals")
@login_required
def goals():
    return render_template("goals.html", goals=goal_rows(session["user_id"]))


@app.route("/goals/add", methods=["GET", "POST"])
@login_required
def add_goal():
    return save_goal(title="Add savings goal")


@app.route("/goals/<int:gid>/edit", methods=["GET", "POST"])
@login_required
def edit_goal(gid):
    owned("savings_goals", gid)
    return save_goal(gid, "Edit savings goal")


@app.route("/goals/<int:gid>/delete", methods=["POST"])
@login_required
def delete_goal(gid):
    owned("savings_goals", gid)
    execute("DELETE FROM savings_goals WHERE id=? AND user_id=?", (gid, session["user_id"]))
    flash("Goal deleted.", "info")
    return redirect(url_for("goals"))


@app.route("/goals/<int:gid>/add-savings", methods=["POST"])
@login_required
def add_savings(gid):
    owned("savings_goals", gid)
    errs = []
    amt = to_amount(request.form.get("amount"), errs)
    if errs:
        flash(errs[0], "danger")
    else:
        execute("UPDATE savings_goals SET saved_amount = saved_amount + ? WHERE id=? AND user_id=?", (amt, gid, session["user_id"]))
        flash(f"Added {inr(amt)} to your goal.", "success")
    return redirect(url_for("goals"))


# --------------------------------------------------------------- analysis
def health_score(savings_rate, expense_ratio, budgets):
    """Rule-based score, 0-100 (educational, not financial advice).
    Savings rate  40 pts: 30%+ saved = full marks, scaled linearly below.
    Expense ratio 20 pts: <=70% of income = full, 100%+ = zero.
    Budget usage  20 pts: average utilisation <=75% = full, 125%+ = zero (10 if no budgets).
    Overspending  20 pts: minus 10 for every exceeded budget (10 if no budgets)."""
    p1 = max(0, min(savings_rate, 30)) / 30 * 40
    p2 = 20 if expense_ratio <= 70 else max(0, 20 * (100 - expense_ratio) / 30)
    if budgets:
        avg = sum(b["pct"] for b in budgets) / len(budgets)
        p3 = 20 if avg <= 75 else max(0, 20 * (125 - avg) / 50)
        p4 = max(0, 20 - 10 * sum(1 for b in budgets if b["pct"] >= 100))
    else:
        p3 = p4 = 10
    return round(p1 + p2 + p3 + p4), {"Savings rate": round(p1), "Expense ratio": round(p2), "Budget usage": round(p3), "Overspending": round(p4)}


def rate_for(txs, ym):
    inc = sum(t["amount"] for t in txs if t["transaction_type"] == "Income" and t["transaction_date"].startswith(ym))
    exp = sum(t["amount"] for t in txs if t["transaction_type"] == "Expense" and t["transaction_date"].startswith(ym))
    return inc, exp, ((inc - exp) / inc * 100 if inc else 0)


@app.route("/analysis")
@login_required
def analysis():
    uid, t = session["user_id"], date.today()
    txs = get_transactions(uid)
    ym = month_key()
    income, expense, rate = rate_for(txs, ym)
    ratio = expense / income * 100 if income else (100 if expense else 0)
    cats = category_totals(txs, ym)
    budgets = budget_rows(uid, t.year, t.month, cats)
    top = max(cats, key=cats.get) if cats else None
    score, parts = health_score(rate, ratio, budgets)
    prev_ym = last_months(2)[0]
    _, _, prev_rate = rate_for(txs, prev_ym)
    tips = []
    if top and expense and cats[top] / expense > 0.35 and top not in ("Rent / Hostel",):
        tips.append(f"Your {top.lower()} spending is high this month ({cats[top] / expense * 100:.0f}% of expenses).")
    tips += [f"You have used {b['pct']:.0f}% of your {b['category'].lower()} budget." for b in budgets if b["pct"] >= 75]
    if income and rate > prev_rate:
        tips.append("Your savings rate improved this month.")
    if income and rate < 10:
        tips.append("Consider reducing discretionary spending.")
    if not tips:
        tips.append("Looking steady. Keep tracking to see trends.")
    return render_template("analysis.html", income=income, expense=expense, rate=rate, ratio=ratio, top=top,
                           top_amount=cats.get(top, 0), budgets=budgets, score=score, parts=parts, tips=tips,
                           month_label=f"{MONTHS[t.month - 1]} {t.year}")


# ---------------------------------------------------------------- profile
@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    uid = session["user_id"]
    user = query("SELECT * FROM users WHERE id=?", (uid,), one=True)
    if request.method == "POST":
        f, errs = request.form, []
        if f.get("action") == "name":
            name = f.get("full_name", "").strip()
            if not name:
                errs.append("Full name is required.")
            else:
                execute("UPDATE users SET full_name=? WHERE id=?", (name, uid))
                session["user_name"] = name
                flash("Name updated.", "success")
        else:
            if not check_password_hash(user["password_hash"], f.get("current_password", "")):
                errs.append("Current password is incorrect.")
            if len(f.get("new_password", "")) < 6:
                errs.append("New password must be at least 6 characters.")
            if f.get("new_password") != f.get("confirm_password"):
                errs.append("New passwords do not match.")
            if not errs:
                execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(f["new_password"]), uid))
                flash("Password changed.", "success")
        for e in errs:
            flash(e, "danger")
        return redirect(url_for("profile"))
    return render_template("profile.html", user=user)


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("500.html"), 500


db.init_db()

if __name__ == "__main__":
    app.run(debug=True)
