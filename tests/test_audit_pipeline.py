from app.services.audit_pipeline import run_revenue_audit


def run(sales, ledger):
    return run_revenue_audit(
        sales=sales,
        ledger=ledger,
        invoice_column="invoice",
        sales_amount_column="amount",
        ledger_invoice_column="invoice",
        ledger_amount_column="amount",
        date_column="date",
        period_start="2026-03-28",
        period_end="2026-04-02",
        materiality_threshold="1000",
    )


def test_pipeline_combines_reconciliation_duplicate_and_cutoff_rules():
    sales = [
        {"invoice": "A", "amount": "1200", "date": "2026-03-29"},
        {"invoice": "A", "amount": "1200", "date": "2026-03-29"},
        {"invoice": "B", "amount": "300", "date": "2026-03-20"},
    ]
    ledger = [
        {"invoice": "A", "amount": "1000"},
        {"invoice": "C", "amount": "200"},
    ]

    result = run(sales, ledger)
    codes = {item["rule_code"] for item in result["exceptions"]}

    assert result["status"] == "COMPLETED"
    assert result["sales_record_count"] == 3
    assert result["ledger_record_count"] == 2
    assert {
        "REV_DUPLICATE_INVOICE",
        "REV_RECON_DUPLICATE_KEY",
        "REV_RECON_SALES_ONLY",
        "REV_RECON_LEDGER_ONLY",
        "REV_CUTOFF_OUT_OF_PERIOD",
    } <= codes


def test_pipeline_is_reproducible():
    sales = [{"invoice": "A", "amount": "100", "date": "2026-03-29"}]
    ledger = [{"invoice": "A", "amount": "90"}]

    assert run(sales, ledger) == run(sales, ledger)


def test_clean_population_has_no_exceptions():
    sales = [{"invoice": "A", "amount": "100", "date": "2026-03-29"}]
    ledger = [{"invoice": "A", "amount": "100"}]

    result = run(sales, ledger)

    assert result["exception_count"] == 0
    assert result["exceptions"] == []


def test_missing_date_and_missing_amount_remain_explicit():
    sales = [{"invoice": "A", "amount": "", "date": ""}]
    ledger = [{"invoice": "A", "amount": "0"}]

    result = run(sales, ledger)
    codes = {item["rule_code"] for item in result["exceptions"]}

    assert "REV_RECON_MISSING_AMOUNT" in codes
    assert "REV_CUTOFF_MISSING_DATE" in codes


def test_pipeline_does_not_mutate_input_records():
    sales = [{"invoice": "A", "amount": "100", "date": "2026-03-29"}]
    ledger = [{"invoice": "A", "amount": "80"}]
    sales_before = [dict(row) for row in sales]
    ledger_before = [dict(row) for row in ledger]

    run(sales, ledger)

    assert sales == sales_before
    assert ledger == ledger_before
