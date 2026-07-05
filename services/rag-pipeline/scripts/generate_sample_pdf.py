"""Generate the sample PDF used by scripts/test_ingest_and_query.py.

This is a one-off helper, not part of the pipeline itself: it only exists so
the checked-in sample_data/sample_budget_guide.pdf can be regenerated if it's
ever lost or needs editing. Requires the "dev" extra (fpdf2):

    pip install -e ".[dev]"
    python scripts/generate_sample_pdf.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "sample_data" / "sample_budget_guide.pdf"

TITLE = "FinSight Personal Finance Guide: Budgeting Basics"

SECTIONS = [
    (
        "Introduction",
        "This guide introduces the core habits behind a healthy personal budget. "
        "It is meant as a starting point for FinSight users who want a simple, "
        "repeatable system for managing income, expenses, and savings without "
        "spending hours in a spreadsheet every month.",
    ),
    (
        "The 50/30/20 Rule",
        "A popular way to structure a monthly budget is the 50/30/20 rule. Fifty "
        "percent of after-tax income goes to needs such as rent, utilities, "
        "groceries, and minimum debt payments. Thirty percent goes to wants, "
        "including dining out, entertainment subscriptions, and hobbies. The "
        "remaining twenty percent goes to savings and extra debt paydown, such as "
        "contributions to an emergency fund, a retirement account, or a brokerage "
        "account. The rule is a starting ratio, not a strict law: renters in "
        "expensive cities may need to shift more toward needs, while someone with "
        "low fixed costs can push more into savings.",
    ),
    (
        "Building an Emergency Fund",
        "Before aggressively investing, most financial planners recommend saving "
        "three to six months of essential expenses in an easily accessible "
        "account, such as a high-yield savings account. This emergency fund "
        "covers job loss, medical bills, or unexpected home and car repairs "
        "without forcing you to rely on high-interest credit cards. A common "
        "approach is to automate a fixed transfer to savings right after each "
        "paycheck arrives, treating it like a non-negotiable bill rather than an "
        "afterthought at the end of the month.",
    ),
    (
        "Managing Debt",
        "When paying down multiple debts, two common strategies are the "
        "avalanche method and the snowball method. The avalanche method pays "
        "extra toward the debt with the highest interest rate first, minimizing "
        "total interest paid over time. The snowball method pays off the "
        "smallest balance first, which builds momentum and motivation even "
        "though it is not always the mathematically optimal choice. Either "
        "strategy works better than making only minimum payments, since "
        "minimum payments on high-interest credit cards can take years to clear "
        "a balance.",
    ),
    (
        "Saving for Retirement",
        "Retirement accounts such as a 401(k) or an IRA offer tax advantages "
        "that make them more efficient than a regular brokerage account for "
        "long-term savings. Many employers match a percentage of 401(k) "
        "contributions, which is effectively free money and should usually be "
        "captured in full before directing extra savings elsewhere. Starting "
        "early matters more than starting with a large amount, since "
        "compounding returns reward time in the market over attempts to time "
        "it.",
    ),
    (
        "Tracking Your Spending",
        "A budget only works if it is compared against actual spending. "
        "Reviewing transactions weekly or monthly, categorizing them "
        "consistently, and flagging categories that regularly exceed their "
        "planned share of income turns a budget from a one-time exercise into "
        "an ongoing feedback loop. Tools like FinSight aim to make this review "
        "step fast by automatically categorizing transactions and surfacing "
        "trends, so the habit of checking in is less friction and more "
        "insight.",
    ),
]


def build_pdf() -> None:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 10, TITLE)
    pdf.ln(4)

    for heading, body in SECTIONS:
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 8, heading)
        pdf.set_x(pdf.l_margin)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, body)
        pdf.ln(4)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PATH))
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
