# AuditEase Bug Log: Net Loss / Profit Calculated as Sum instead of Difference

## 1. Issue Overview
In the AuditEase financial reports, the total for the Profit & Loss statement is incorrectly calculated as the **sum** of Total Income and Total Expenditure, instead of the **difference**. This leads to the net profit/loss appearing as a sum of both absolute balances rather than properly reflecting the net financial position.

## 2. Where the Issue is Located
The bug exists in two locations—both the Frontend Preview and the Backend Generated Report:

### Frontend
- **File:** `frontend/src/pages/company/auditease/ReportsTab.tsx`
- **Component:** `ReportsTab` rendering the `Profit & Loss` section.
- **Helper Component:** `StatementSection`

### Backend
- **File:** `app/routers/auditease.py`
- **Endpoint/Function:** `preview_report` (HTML generation logic inside)
- **Helper Function:** `section()` (nested inside `preview_report`)

## 3. What is Happening
Both the frontend UI and backend HTML generator use a reusable section component (`StatementSection` in React, `section()` in Python) to render the statements. 

For the Profit & Loss statement, both systems group `'Income'` and `'Expenditure'` together into a single section:
- **Frontend:** `<StatementSection title="Income & Expenditure" groups={['Income', 'Expenditure']} lines={report.lines} />`
- **Backend:** `section('Profit &amp; Loss', ['Income', 'Expenditure'])`

These generic section components calculate their bottom-line total by unconditionally **summing** the `final` values of all ledgers in the provided groups. Since AuditEase stores the `final` balances of both Income and Expenditure as absolute (positive) values, the code performs the following math:
`Section Total = abs(Income) + abs(Expenditure)`

## 4. The Main Issue
The core issue is that the generic `StatementSection` (and backend `section()`) assumes that all grouped ledgers should be added together. While this works for the Balance Sheet (where Assets and Liabilities are in separate sections), it fails for the Profit & Loss statement because Income and Expenditure have opposite accounting natures and must be **subtracted** to calculate the net profit or loss.

By grouping them together and blindly summing their absolute balances, the system displays a meaningless "Total" that users mistake for the net loss/profit.

## 5. Recommended Fix
1. **Separate Sections:** Split the P&L statement into two distinct sections (one for `Income` and one for `Expenditure`), similar to how `Assets` and `Liabilities` are separated in the Balance Sheet.
2. **Remove Misleading Totals:** Alternatively, remove the generic section total for the combined P&L block and rely purely on the explicitly calculated `net_profit` (which is correctly calculated as `totals["Income"] - totals["Expenditure"]` in the backend and displayed at the bottom of the report summary).
