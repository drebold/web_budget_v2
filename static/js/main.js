// ── Locale / formatting ───────────────────────────────────────────────────────
// Change 'nb-NO' to your preferred locale (e.g. 'en-US', 'de-DE').
// This controls the decimal separator and thousands separator in displayed numbers.
const LOCALE = 'nb-NO';

function fmt(n) {
  return Number(n).toLocaleString(LOCALE, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const MONTH_NAME = {
  1:'January', 2:'February', 3:'March', 4:'April', 5:'May', 6:'June',
  7:'July', 8:'August', 9:'September', 10:'October', 11:'November', 12:'December',
};

// Human-readable labels for the "payments per year" dropdown values.
const PPY_LABEL = {
  1: 'Annual', 2: 'Semi-annual', 3: 'Every 4 mo',
  4: 'Quarterly', 6: 'Bi-monthly', 12: 'Monthly',
};

// ── API helper ────────────────────────────────────────────────────────────────
// A thin wrapper around fetch() so every API call looks the same.
// Usage: api('GET', '/expenses')  or  api('POST', '/expenses', { name: ... })
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  const res = await fetch('/api' + path, opts);
  return res.json();
}

// ── Tabs ──────────────────────────────────────────────────────────────────────
// Shows the selected tab section and hides the others, then loads fresh data for it.
function showTab(name, btn) {
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  btn.classList.add('active');
  if (name === 'expenses') loadExpenses();
  if (name === 'monthly') loadMonthly();
  if (name === 'summary') loadSummary();
}

// ── Expenses ──────────────────────────────────────────────────────────────────
// Fetches the full expense list from the server and renders it as a table.
async function loadExpenses() {
  const expenses = await api('GET', '/expenses');
  const tbody = document.getElementById('expenses-body');

  if (!expenses.length) {
    tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state">No expenses yet — click "+ Add Expense" to get started.</div></td></tr>`;
    return;
  }

  // Build a table row for each expense.
  tbody.innerHTML = expenses.map(e => {
    const myAmt = e.amount * e.my_share_pct / 100;
    const wifeAmt = e.amount * e.wife_share_pct / 100;
    return `<tr>
      <td><strong>${esc(e.name)}</strong></td>
      <td>${fmt(e.amount)}</td>
      <td>${e.my_share_pct}%</td>
      <td>${e.wife_share_pct}%</td>
      <td style="color:#1d4ed8;font-weight:500">${fmt(myAmt)}</td>
      <td style="color:#9d174d;font-weight:500">${fmt(wifeAmt)}</td>
      <td>${MONTH_NAME[e.first_month]}</td>
      <td>${PPY_LABEL[e.payments_per_year] ?? e.payments_per_year + 'x'}</td>
      <td>
        <div class="actions">
          <button class="btn btn-sm btn-secondary" onclick="editExpense('${e.id}')">Edit</button>
          <button class="btn btn-sm btn-danger" onclick="deleteExpense('${e.id}')">Delete</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

async function deleteExpense(id) {
  if (!confirm('Delete this expense?')) return;
  await api('DELETE', `/expenses/${id}`);
  loadExpenses();  // refresh the table
}

// ── Monthly view ──────────────────────────────────────────────────────────────
// Renders an accordion (collapsible cards) showing each month's expenses.
// The pattern is year-independent — it just shows which expenses fall in each month.
async function loadMonthly() {
  const months = await api('GET', '/monthly');
  const container = document.getElementById('monthly-container');

  container.innerHTML = months.map((m, i) => {
    // Build the inner table (or a "no expenses" message) for each month card.
    const bodyContent = m.expenses.length === 0
      ? `<div class="no-expenses">No expenses this month.</div>`
      : `<table>
          <thead><tr>
            <th>Expense</th><th>Total</th>
            <th style="color:#1d4ed8">My Share</th>
            <th style="color:#9d174d">Wife's Share</th>
          </tr></thead>
          <tbody>
            ${m.expenses.map(e => `<tr>
              <td>${esc(e.name)}</td>
              <td>${fmt(e.amount)}</td>
              <td style="color:#1d4ed8;font-weight:500">${fmt(e.my_amount)}</td>
              <td style="color:#9d174d;font-weight:500">${fmt(e.wife_amount)}</td>
            </tr>`).join('')}
            <tr style="font-weight:600;background:var(--bg)">
              <td>Total</td>
              <td>${fmt(m.total)}</td>
              <td style="color:#1d4ed8">${fmt(m.my_total)}</td>
              <td style="color:#9d174d">${fmt(m.wife_total)}</td>
            </tr>
          </tbody>
        </table>`;

    // January (i === 0) starts expanded; all other months start collapsed.
    return `<div class="month-card">
      <div class="month-header" onclick="toggleMonth(this)">
        <span class="month-title">${m.label}</span>
        <div class="month-totals">
          <span><span class="lbl">Me: </span><span class="val me-color">${fmt(m.my_total)}</span></span>
          <span><span class="lbl">Wife: </span><span class="val wife-color">${fmt(m.wife_total)}</span></span>
          <span><span class="lbl">Total: </span><span class="val">${fmt(m.total)}</span></span>
        </div>
        <span class="month-chevron ${i === 0 ? 'open' : ''}">▼</span>
      </div>
      <div class="month-body ${i === 0 ? 'open' : ''}">${bodyContent}</div>
    </div>`;
  }).join('');
}

// Toggle a month card open/closed when its header is clicked.
function toggleMonth(header) {
  const body = header.nextElementSibling;
  const chevron = header.querySelector('.month-chevron');
  body.classList.toggle('open');
  chevron.classList.toggle('open');
}

// ── Summary ───────────────────────────────────────────────────────────────────
// Fetches the deposit plan and balance table from the server and renders them.
async function loadSummary() {
  const s = await api('GET', '/summary');

  // Info cards at the top of the summary tab.
  document.getElementById('summary-cards').innerHTML = `
    <div class="card">
      <div class="card-label">My Annual Total</div>
      <div class="card-value" style="color:#1d4ed8">${fmt(s.my_annual)}</div>
      <div class="card-sub">My share of all expenses per year</div>
    </div>
    <div class="card">
      <div class="card-label">Wife Annual Total</div>
      <div class="card-value" style="color:#9d174d">${fmt(s.wife_annual)}</div>
      <div class="card-sub">Wife's share of all expenses per year</div>
    </div>
    <div class="card">
      <div class="card-label">My Monthly Deposit</div>
      <div class="card-value" style="color:#1d4ed8">${fmt(s.my_monthly_deposit)}</div>
      <div class="card-sub">Fixed amount to deposit every month</div>
    </div>
    <div class="card">
      <div class="card-label">Wife Monthly Deposit</div>
      <div class="card-value" style="color:#9d174d">${fmt(s.wife_monthly_deposit)}</div>
      <div class="card-sub">Fixed amount to deposit every month</div>
    </div>
    <div class="card">
      <div class="card-label">Combined Monthly Deposit</div>
      <div class="card-value">${fmt(s.total_monthly_deposit)}</div>
      <div class="card-sub">Total household deposit per month</div>
    </div>
    <div class="card">
      <div class="card-label">Combined Annual Total</div>
      <div class="card-value">${fmt(s.total_annual)}</div>
      <div class="card-sub">Total household expenses per year</div>
    </div>
    <div class="card">
      <div class="card-label">Starting Balance</div>
      <div class="card-value">${fmt(s.starting_balance)}</div>
      <div class="card-sub">One-time buffer needed to open the account</div>
    </div>`;

  // Month-by-month balance table. Negative balances are shown in red.
  document.getElementById('balance-body').innerHTML = s.balance_progression.map(b => `
    <tr>
      <td><strong>${b.label}</strong></td>
      <td style="color:#1d4ed8">${fmt(b.my_expenses)}</td>
      <td style="color:#9d174d">${fmt(b.wife_expenses)}</td>
      <td>${fmt(b.total_expenses)}</td>
      <td class="${b.balance_start >= 0 ? 'positive' : 'negative'}">${fmt(b.balance_start)}</td>
      <td class="${b.balance_end >= 0 ? 'positive' : 'negative'}">${fmt(b.balance_end)}</td>
    </tr>`).join('');
}

// ── Modal (Add / Edit expense) ────────────────────────────────────────────────
// _editId tracks whether we are editing an existing expense (has an ID) or adding a new one (null).
let _editId = null;

// Opens the modal, pre-filling fields if editing an existing expense.
function openModal(expense = null) {
  _editId = expense?.id ?? null;
  document.getElementById('modal-title').textContent = expense ? 'Edit Expense' : 'Add Expense';
  document.getElementById('f-id').value = expense?.id ?? '';
  document.getElementById('f-name').value = expense?.name ?? '';
  document.getElementById('f-amount').value = expense?.amount ?? '';
  document.getElementById('f-my-share').value = expense?.my_share_pct ?? 50;
  // Default first month to the current month when adding a new expense.
  document.getElementById('f-first-month').value =
    expense?.first_month ?? (new Date().getMonth() + 1);
  document.getElementById('f-ppy').value = expense?.payments_per_year ?? 12;
  updateShares();
  document.getElementById('modal').classList.remove('hidden');
  document.getElementById('f-name').focus();
}

function closeModal() {
  document.getElementById('modal').classList.add('hidden');
  _editId = null;
}

// Allows closing the modal by clicking the dark backdrop behind it.
function backdropClose(e) {
  if (e.target === e.currentTarget) closeModal();
}

// Updates the share percentage labels and the kr-amount preview as the slider moves.
function updateShares() {
  const my = parseInt(document.getElementById('f-my-share').value);
  const wife = 100 - my;
  document.getElementById('my-share-val').textContent = my;
  document.getElementById('wife-share-val').textContent = wife;

  // Show the actual amounts (e.g. "Me: 750") once an amount has been entered.
  const amount = parseFloat(document.getElementById('f-amount').value);
  const amts = document.getElementById('share-amounts');
  if (amount > 0) {
    document.getElementById('my-share-amt').textContent = `Me: ${fmt(amount * my / 100)}`;
    document.getElementById('wife-share-amt').textContent = `Wife: ${fmt(amount * wife / 100)}`;
    amts.classList.remove('hidden');
  } else {
    amts.classList.add('hidden');
  }
}

// Called when the form is submitted. Sends a POST (new) or PUT (edit) to the API.
async function saveExpense(e) {
  e.preventDefault();  // prevent the browser from reloading the page on form submit
  const my_share_pct = parseInt(document.getElementById('f-my-share').value);
  const data = {
    name: document.getElementById('f-name').value.trim(),
    amount: parseFloat(document.getElementById('f-amount').value),
    my_share_pct,
    wife_share_pct: 100 - my_share_pct,
    first_month: parseInt(document.getElementById('f-first-month').value),
    payments_per_year: parseInt(document.getElementById('f-ppy').value),
  };

  if (_editId) {
    await api('PUT', `/expenses/${_editId}`, data);
  } else {
    await api('POST', '/expenses', data);
  }

  closeModal();
  loadExpenses();  // refresh the table to show the change
}

// Fetches the expense by ID and opens the modal pre-filled with its data.
async function editExpense(id) {
  const expenses = await api('GET', '/expenses');
  const expense = expenses.find(e => e.id === id);
  if (expense) openModal(expense);
}

// ── Export / Import ───────────────────────────────────────────────────────────

async function exportBudget() {
  // Ask the user for a filename (pre-filled with today's date), then trigger a download.
  const today = new Date().toISOString().slice(0, 10);
  const name = prompt('Save as:', `budget_${today}.json`);
  if (!name) return;  // user cancelled the prompt
  const res = await fetch('/api/export');
  const blob = await res.blob();
  // Create a temporary invisible link and click it to trigger the browser's Save dialog.
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name.endsWith('.json') ? name : name + '.json';
  a.click();
  URL.revokeObjectURL(url);  // clean up the temporary URL
}

async function importBudget(event) {
  // Uploads the selected JSON file to the server, which replaces the current budget.
  const file = event.target.files[0];
  if (!file) return;
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/import', { method: 'POST', body: fd });
  const data = await res.json();
  if (data.ok) {
    loadExpenses();  // refresh to show the imported data
  } else {
    alert('Import failed: ' + data.error);
  }
  event.target.value = '';  // reset the file input so the same file can be re-imported if needed
}

// ── Helpers ───────────────────────────────────────────────────────────────────

// Escapes special HTML characters to prevent XSS when inserting user-provided text into the DOM.
function esc(str) {
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// ── Global event listeners ────────────────────────────────────────────────────

// Close the modal with the Escape key.
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// Recalculate the share amounts preview whenever the total amount field changes.
document.getElementById('f-amount').addEventListener('input', updateShares);

// ── Init ──────────────────────────────────────────────────────────────────────
// Load the expense list when the page first opens.
loadExpenses();
