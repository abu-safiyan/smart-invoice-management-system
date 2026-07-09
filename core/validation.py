import re
from datetime import datetime
import core.database as database


def normalize_date(date):
    if not date:
        return None
    date_formats = [
        '%d-%m-%Y',
        '%d.%m.%Y',
        '%d/%m/%Y',
        '%m/%d/%Y',
        '%Y-%m-%d',
        '%Y.%m.%d',
        '%Y/%m/%d',
        '%B %d, %Y',
        '%b %d, %Y',
        '%d %B %Y',
        '%d %b %Y'
    ]
    date = date.strip()
    for format in date_formats:
        try:
            parsed_date = datetime.strptime(date, format)
            parsed_date = datetime.strftime(parsed_date, '%Y-%m-%d')
            return parsed_date
        except ValueError:
            continue
    return None


def detect_missing_fields(invoice, raw_invoice_date=None, raw_due_date=None):
    if not invoice.invoice_number:
        invoice.validation_errors.append('Invoice Number is missing!')
        invoice.validation_status = 'Invalid'
    if not invoice.invoice_date:
        if raw_invoice_date:
            invoice.validation_errors.append('Invoice Date is invalid!')
        else:
            invoice.validation_errors.append('Invoice Date is missing!')
        invoice.validation_status = 'Invalid'
    if not invoice.due_date and invoice.payment_status!='PAID':
        if raw_due_date:
            invoice.validation_errors.append('Due Date is invalid!')
        else:
            invoice.validation_errors.append('Due Date is missing!')
        invoice.validation_status = 'Invalid'
    if not invoice.total_amount:
        invoice.validation_errors.append('Total amount is missing!')
        invoice.validation_status = 'Invalid'
    if not invoice.currency:
        invoice.validation_errors.append('Currency is missing!')
        invoice.validation_status = 'Invalid'
    if not invoice.payment_status:
        invoice.validation_errors.append('Payment status is missing!')
        invoice.validation_status = 'Invalid'
    return invoice

def is_duplicated_invoice(conn, invoice):
    duplicated = database.search_by_invoice_number(conn, invoice.invoice_number)
    if duplicated:
        invoice.validation_errors.append('Duplicate Invoice Number found!')
        invoice.validation_status = 'Invalid'
    return invoice

def validate_amount(invoice):
    if invoice.tax_amount:
        cleaned = str(invoice.tax_amount).replace(',', '').strip()
        try:
            invoice.tax_amount = float(cleaned)
        except ValueError:
            invoice.validation_errors.append('Tax Amount is invalid!')
            invoice.validation_status = 'Invalid'
    if invoice.total_amount:
        cleaned = str(invoice.total_amount).replace(',', '').strip()
        try:
            invoice.total_amount = float(cleaned)
        except ValueError:
            invoice.validation_errors.append('Total Amount is invalid!')
            invoice.validation_status = 'Invalid'
    return invoice

def is_plausible_name(name):
    if not name or len(name)<3:
        return False
    if re.match(r'\d', name):
        return False
    if '@' in name or 'www.' in name.lower():
        return False
    if re.match(r'(invoice|receipt|bill|date|due)\b', name, re.I):
        return False
    return True

def detect_and_split_merged_address(address):
    """
    Returns (is_merged, vendor_part, customer_part_or_None)
    """
    if not address:
        return False, None, None
    pattern = r'^(.+?,\s*\w+)\s+([A-Z].+,\s*\w+)$'
    match = re.match(pattern, address)
    if match:
        return True, match.group(1).strip(), match.group(2).strip()
    return False, address, None


def validate(conn, invoice, vendor):
    raw_invoice_date = invoice.invoice_date
    raw_due_date = invoice.due_date
    invoice.invoice_date = normalize_date(invoice.invoice_date)
    invoice.due_date = normalize_date(invoice.due_date)
    invoice = detect_missing_fields(invoice, raw_invoice_date, raw_due_date)
    if invoice.validation_status!='Invalid':
        invoice = is_duplicated_invoice(conn, invoice)
    if invoice.validation_status!='Invalid':
        invoice = validate_amount(invoice)
    if invoice.validation_status!='Invalid':
        if not is_plausible_name(invoice.customer_name):
            invoice.validation_errors.append('Customer name needs to be reviewed!')
            invoice.validation_status = 'Needs Review'
        if not is_plausible_name(vendor.vendor_name):
            invoice.validation_errors.append('Vendor name needs to be reviewed!')
            invoice.validation_status = 'Needs Review'
        merged, vendor_address, customer_address = detect_and_split_merged_address(vendor.vendor_address)
        if merged:
            vendor.vendor_address = vendor_address
            invoice.validation_errors.append('Vendor address needs to be reviewed!')
            invoice.validation_status = 'Needs Review'
    if invoice.validation_status=='Unvalidated':
        invoice.validation_status='Validated'
    
    return invoice, vendor
    
