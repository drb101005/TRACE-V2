from datetime import date
from app.audit_engine.sales_register import run_sales_register

def test_invoice_arithmetic_mismatch_is_deterministic():
    records = [{
        "id": "r1", "upload_id": "u1", "source_row_number": 2,
        "record": {"invoice_number":"INV-1", "invoice_date":"2026-03-30",
                   "customer_name":"A", "total_amount":"119000.00",
                   "taxable_value":"100000.00", "tax_amount":"18000.00"}
    }]
    a = run_sales_register(records, date(2025,4,1), date(2026,3,31))
    b = run_sales_register(records, date(2025,4,1), date(2026,3,31))
    assert a == b
    assert any(x["rule_code"] == "INVOICE_ARITHMETIC_MISMATCH" for x in a["findings"])
    f = next(x for x in a["findings"] if x["rule_code"] == "INVOICE_ARITHMETIC_MISMATCH")
    assert f["amount_under_review"] == "1000.00"

def test_missing_amount_is_not_treated_as_zero():
    records = [{"id":"r1","upload_id":"u1","source_row_number":2,
                "record":{"invoice_number":"I1","invoice_date":"2026-03-30"}}]
    result = run_sales_register(records, date(2025,4,1), date(2026,3,31))
    assert any(x["rule_code"] == "TOTAL_AMOUNT_INVALID_OR_MISSING" for x in result["findings"])
    assert result["summary"]["total_amount"] == "0.00"
    assert all(x["amount_under_review"] is None for x in result["findings"] if x["rule_code"] == "TOTAL_AMOUNT_INVALID_OR_MISSING")

def test_out_of_period_invoice_flagged_for_review_not_misstatement():
    records = [{"id":"r1","upload_id":"u1","source_row_number":2,
                "record":{"invoice_number":"I1","invoice_date":"2026-04-02","total_amount":"100",
                          "taxable_value":"100","tax_amount":"0"}}]
    result = run_sales_register(records, date(2025,4,1), date(2026,3,31))
    f = next(x for x in result["findings"] if x["rule_code"] == "INVOICE_OUTSIDE_AUDIT_PERIOD")
    assert f["severity"] == "MEDIUM"
    assert f["amount_under_review"] == "100.00"
