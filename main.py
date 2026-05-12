import calendar
import io
import json
import os
import uuid
from datetime import date

from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)

# The budget is stored as a plain JSON file on disk.
# All changes (add/edit/delete) are written immediately — no separate "save" step needed.
BUDGET_FILE = "budget.json"


def load_budget():
    # If no file exists yet, start with an empty list of expenses.
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE) as f:
            return json.load(f)
    return {"expenses": []}


def save_budget(data):
    # Overwrite the file with the current state, formatted for readability.
    with open(BUDGET_FILE, "w") as f:
        json.dump(data, f, indent=2)


def expense_in_month(expense, month):
    """Return True if this expense falls in the given month (1–12).

    How it works:
      - 'first_month' is the month the expense first occurs (e.g. "2026-03" = March).
      - 'payments_per_year' tells us how often it repeats: 12 = every month,
        4 = every 3 months (quarterly), 1 = once a year, etc.
      - interval = 12 / payments_per_year gives the gap in months between payments.
      - We check if (current_month - first_month) is an exact multiple of that interval.

    Example: first_month = March (3), payments_per_year = 4, interval = 3.
      Payments fall in months 3, 6, 9, 12 (March, June, September, December).
    """
    fm = expense["first_month"]  # integer 1–12
    interval = 12 // expense["payments_per_year"]
    # Python's % operator always returns a non-negative result for positive divisors,
    # so this correctly wraps around (e.g. November + 3 months = February next year).
    return (month - fm) % interval == 0


# ── Serve the single-page app ─────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


# ── Expense CRUD API ──────────────────────────────────────────────────────────

@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    return jsonify(load_budget()["expenses"])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    budget = load_budget()
    expense = request.json
    expense["id"] = str(uuid.uuid4())  # unique ID so we can identify each expense later
    expense["wife_share_pct"] = 100 - expense["my_share_pct"]  # the two shares must always add to 100
    budget["expenses"].append(expense)
    save_budget(budget)
    return jsonify(expense), 201


@app.route("/api/expenses/<expense_id>", methods=["PUT"])
def update_expense(expense_id):
    budget = load_budget()
    expense = request.json
    expense["id"] = expense_id
    expense["wife_share_pct"] = 100 - expense["my_share_pct"]
    for i, e in enumerate(budget["expenses"]):
        if e["id"] == expense_id:
            budget["expenses"][i] = expense  # replace the old entry in-place
            save_budget(budget)
            return jsonify(expense)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/expenses/<expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    budget = load_budget()
    # Keep every expense except the one being deleted.
    budget["expenses"] = [e for e in budget["expenses"] if e["id"] != expense_id]
    save_budget(budget)
    return jsonify({"ok": True})


# ── Monthly breakdown API ─────────────────────────────────────────────────────

@app.route("/api/monthly")
def get_monthly():
    """Return expenses grouped by month (January–December).

    Since the budget repeats the same pattern every year, no year is needed —
    we just show which expenses fall in each of the 12 months.
    """
    expenses = load_budget()["expenses"]
    result = []
    for month in range(1, 13):
        month_data = {
            "month": month,
            "label": calendar.month_name[month],
            "expenses": [],
            "my_total": 0.0,
            "wife_total": 0.0,
            "total": 0.0,
        }
        for exp in expenses:
            if expense_in_month(exp, month):
                my_amt = round(exp["amount"] * exp["my_share_pct"] / 100, 2)
                wife_amt = round(exp["amount"] * exp["wife_share_pct"] / 100, 2)
                month_data["expenses"].append(
                    {
                        "name": exp["name"],
                        "amount": exp["amount"],
                        "my_amount": my_amt,
                        "wife_amount": wife_amt,
                    }
                )
                month_data["my_total"] += my_amt
                month_data["wife_total"] += wife_amt
                month_data["total"] += exp["amount"]
        month_data["my_total"] = round(month_data["my_total"], 2)
        month_data["wife_total"] = round(month_data["wife_total"], 2)
        month_data["total"] = round(month_data["total"], 2)
        result.append(month_data)
    return jsonify(result)


# ── Summary & deposit plan API ────────────────────────────────────────────────

@app.route("/api/summary")
def get_summary():
    """Calculate how much each person should deposit every month, and the
    required starting balance for the joint account.

    The deposit logic:
      - Total annual cost per person = sum of (amount × share% × payments_per_year).
      - Monthly deposit = annual cost / 12.
      - Depositing the same fixed amount every month means some months you
        "save up" and other months you draw down the balance for big expenses.

    The starting balance logic:
      - Because some months have higher expenses than others, you need a buffer
        in the account from day one so it never goes negative.
      - We calculate the worst-case deficit across all 12 months and use that
        as the required starting balance (a one-time top-up when opening the account).
    """
    expenses = load_budget()["expenses"]

    # Annual totals: for each expense, multiply by how many times it occurs per year.
    my_annual = sum(
        e["amount"] * e["my_share_pct"] / 100 * e["payments_per_year"] for e in expenses
    )
    wife_annual = sum(
        e["amount"] * e["wife_share_pct"] / 100 * e["payments_per_year"] for e in expenses
    )
    my_deposit = my_annual / 12
    wife_deposit = wife_annual / 12
    total_deposit = my_deposit + wife_deposit  # combined monthly deposit to the joint account

    # Build a list of combined expenses for each month (January = index 0, etc.)
    monthly_my = []
    monthly_wife = []
    monthly_combined = []
    for month in range(1, 13):
        m_total = 0.0
        w_total = 0.0
        for exp in expenses:
            if expense_in_month(exp, month):
                m_total += exp["amount"] * exp["my_share_pct"] / 100
                w_total += exp["amount"] * exp["wife_share_pct"] / 100
        monthly_my.append(m_total)
        monthly_wife.append(w_total)
        monthly_combined.append(m_total + w_total)

    def min_starting_balance(monthly_expenses, monthly_deposit):
        """Find the minimum initial balance needed so the account never goes negative.

        For each month k, we check: cumulative expenses so far minus cumulative deposits.
        The largest such deficit is what you need to have in the account at the start.
        """
        max_deficit = 0.0
        cum_exp = 0.0
        for k, exp in enumerate(monthly_expenses):
            cum_exp += exp
            # How far ahead or behind are we after k+1 months of depositing?
            deficit = cum_exp - (k + 1) * monthly_deposit
            max_deficit = max(max_deficit, deficit)
        return max(0.0, max_deficit)  # can't be negative — if deposits always cover expenses, no buffer needed

    starting_balance = min_starting_balance(monthly_combined, total_deposit)

    # Compute the running balance for each month so it can be shown in the table.
    balance_progression = []
    for k in range(12):
        # Balance at the start of this month (before this month's deposit is added).
        # = starting buffer + all deposits so far - all expenses so far
        bal_start = starting_balance + k * total_deposit - sum(monthly_combined[:k])
        # Balance at the end of the month (after deposit and all expenses are paid).
        bal_end = bal_start + total_deposit - monthly_combined[k]
        balance_progression.append(
            {
                "label": calendar.month_name[k + 1],
                "my_expenses": round(monthly_my[k], 2),
                "wife_expenses": round(monthly_wife[k], 2),
                "total_expenses": round(monthly_combined[k], 2),
                "balance_start": round(bal_start, 2),
                "balance_end": round(bal_end, 2),
            }
        )

    return jsonify(
        {
            "my_annual": round(my_annual, 2),
            "wife_annual": round(wife_annual, 2),
            "my_monthly_deposit": round(my_deposit, 2),
            "wife_monthly_deposit": round(wife_deposit, 2),
            "starting_balance": round(starting_balance, 2),
            "total_annual": round(my_annual + wife_annual, 2),
            "total_monthly_deposit": round(total_deposit, 2),
            "balance_progression": balance_progression,
        }
    )


# ── Export / Import ───────────────────────────────────────────────────────────

@app.route("/api/export")
def export_budget():
    # Serialize the budget to JSON and send it as a downloadable file.
    # The filename includes today's date as a default suggestion (the user can rename it).
    data = json.dumps(load_budget(), indent=2)
    filename = f"budget_{date.today().strftime('%Y-%m-%d')}.json"
    return send_file(
        io.BytesIO(data.encode()),
        mimetype="application/json",
        as_attachment=True,
        download_name=filename,
    )


@app.route("/api/import", methods=["POST"])
def import_budget():
    # Expect a multipart form upload with a field named "file".
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    try:
        data = json.loads(f.read())
        save_budget(data)  # completely replaces the current budget
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def main():
    # debug=True enables auto-reload when you edit the code, and shows detailed errors in the browser.
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
