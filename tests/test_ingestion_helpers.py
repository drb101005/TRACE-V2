from app.services.ingestion import suggest_mapping, validate_rows, canonicalize

def test_suggest_mapping_sales_register():
    mapping = suggest_mapping(["Invoice No.", "Invoice Date", "Customer Name", "Total Amount"])
    assert mapping["invoice_number"] == "Invoice No."
    assert mapping["invoice_date"] == "Invoice Date"
    assert mapping["customer_name"] == "Customer Name"
    assert mapping["total_amount"] == "Total Amount"

def test_validate_valid_sales_rows():
    row = {"Inv": "INV-1", "Date": "2026-03-31", "Customer": "Acme", "Amount": "1,200.50"}
    mapping = {"invoice_number": "Inv", "invoice_date": "Date", "customer_name": "Customer", "total_amount": "Amount"}
    result = validate_rows([row], mapping, "sales_register")
    assert result["valid"] is True
    assert result["error_count"] == 0

def test_validate_invalid_amount_and_duplicate_invoice():
    rows = [
        {"Inv": "INV-1", "Date": "2026-03-31", "Customer": "Acme", "Amount": "oops"},
        {"Inv": "INV-1", "Date": "2026-03-31", "Customer": "Acme", "Amount": "100"},
    ]
    mapping = {"invoice_number": "Inv", "invoice_date": "Date", "customer_name": "Customer", "total_amount": "Amount"}
    result = validate_rows(rows, mapping, "sales_register")
    codes = {e["code"] for e in result["errors"]}
    assert "INVALID_AMOUNT" in codes
    assert "DUPLICATE_IN_UPLOAD" in codes

def test_canonicalize_amount_as_decimal_string():
    result = canonicalize({"Amount": "1,200.50"}, {"total_amount": "Amount"})
    assert result["total_amount"] == "1200.50"
