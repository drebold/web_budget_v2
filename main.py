import calendar
import io
import json
import os
import uuid
from datetime import date

from flask import Flask, jsonify, render_template, request, send_file

app = Flask(__name__)
BUDGET_FILE = "budget.json"


def load_budget():
    if os.path.exists(BUDGET_FILE):
        with open(BUDGET_FILE) as f:
            return json.load(f)
    return {"expenses": []}


def save_budget(data):
    with open(BUDGET_FILE, "w") as f:
        json.dump(data, f, indent=2)


def month_diff(y1, m1, y2, m2):
    return (y2 - y1) * 12 + (m2 - m1)


def expense_occurs_in_month(expense, year, month):
    fy, fm = map(int, expense["first_month"].split("-"))
    diff = month_diff(fy, fm, year, month)
    if diff < 0:
        return False
    interval = 12 // expense["payments_per_year"]
    return diff % interval == 0


def get_next_months(n=13):
    today = date.today()
    y, m = today.year, today.month
    result = []
    for _ in range(n):
        result.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/expenses", methods=["GET"])
def get_expenses():
    return jsonify(load_budget()["expenses"])


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    budget = load_budget()
    expense = request.json
    expense["id"] = str(uuid.uuid4())
    expense["wife_share_pct"] = 100 - expense["my_share_pct"]
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
            budget["expenses"][i] = expense
            save_budget(budget)
            return jsonify(expense)
    return jsonify({"error": "Not found"}), 404


@app.route("/api/expenses/<expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    budget = load_budget()
    budget["expenses"] = [e for e in budget["expenses"] if e["id"] != expense_id]
    save_budget(budget)
    return jsonify({"ok": True})


def expense_in_month(expense, month):
    """Check if an expense falls in a given month (1–12), year-independent."""
    fm = int(expense["first_month"].split("-")[1])
    interval = 12 // expense["payments_per_year"]
    return (month - fm) % interval == 0


@app.route("/api/monthly")
def get_monthly():
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


@app.route("/api/summary")
def get_summary():
    expenses = load_budget()["expenses"]

    # Annual deposit = exact total (amount * payments_per_year * share)
    my_annual = sum(
        e["amount"] * e["my_share_pct"] / 100 * e["payments_per_year"] for e in expenses
    )
    wife_annual = sum(
        e["amount"] * e["wife_share_pct"] / 100 * e["payments_per_year"] for e in expenses
    )
    my_deposit = my_annual / 12
    wife_deposit = wife_annual / 12

    # Monthly distribution over next 12 months for balance progression
    months = get_next_months(12)
    total_deposit = my_deposit + wife_deposit
    monthly_my = []
    monthly_wife = []
    monthly_combined = []
    for year, month in months:
        m_total = 0.0
        w_total = 0.0
        for exp in expenses:
            if expense_occurs_in_month(exp, year, month):
                m_total += exp["amount"] * exp["my_share_pct"] / 100
                w_total += exp["amount"] * exp["wife_share_pct"] / 100
        monthly_my.append(m_total)
        monthly_wife.append(w_total)
        monthly_combined.append(m_total + w_total)

    def min_starting_balance(monthly_expenses, monthly_deposit):
        max_deficit = 0.0
        cum_exp = 0.0
        for k, exp in enumerate(monthly_expenses):
            cum_exp += exp
            deficit = cum_exp - (k + 1) * monthly_deposit
            max_deficit = max(max_deficit, deficit)
        return max(0.0, max_deficit)

    starting_balance = min_starting_balance(monthly_combined, total_deposit)

    balance_progression = []
    for k, (year, month) in enumerate(months):
        # Balance at start of month (before deposit)
        bal_start = starting_balance + k * total_deposit - sum(monthly_combined[:k])
        # Balance after deposit and expenses
        bal_end = bal_start + total_deposit - monthly_combined[k]
        balance_progression.append(
            {
                "label": f"{calendar.month_name[month]} {year}",
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


@app.route("/api/export")
def export_budget():
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
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    try:
        data = json.loads(f.read())
        save_budget(data)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def main():
    app.run(host="0.0.0.0", port=5000, debug=True)


if __name__ == "__main__":
    main()
