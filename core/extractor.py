import pdfplumber, re, os
from .models import Invoice, Vendor


def extract_invoice_number(text):
    pattern = r'Inv(?:oice)?\s*(?:(?:(?:Number|No\.?|Reference|#)\s*[:\-]?)|(?::|\-))\s*([a-z0-9\-/]{4,20})'
    match = re.search(pattern, text, re.IGNORECASE)
    return (match.group(1)).strip().strip('.').strip() if match else None

def extract_vendor_name(text):
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if not lines:
        return None
    candidate = lines[0]
    candidate = re.sub(r'\s*(?:TAX\s*)?INVOICE\s*$', '', candidate, flags=re.I).strip()
    return candidate.strip() if candidate else None

def extract_customer_name(text):
    pattern = r'(?:Customer|Bill\s*To) *:? *\n?([\w\- &\(\)]*)'
    match = re.search(pattern, text, re.I)
    if not match:
        match = re.search(r'(?:Customer|Bill)?\s*To *:? *\n?([\w\- &\(\)]*)(?:\sfor|\sregarding|\.)', text, re.I)
    if not match:
        pattern = r'(?:Customer|Bill)?\s*To *:? *\n?([\w\- &\.\(\)]*)'
        match = re.search(pattern, text, re.I)
    if match:
        vendor = extract_vendor_name(text)
        if vendor and vendor in match.group(1):
            customer = re.sub(vendor, '', match.group(1))
            return customer.strip() if customer else None
    return match.group(1) if match else None

def extract_invoice_date(text):
    pattern = r'(?:(?:Invoice\s*Date)|(?:Date\s*issued)|(?:issued\s*on))\s*:?\s*((?:[\d ]{1,4})?(?:[a-z]{3,12})?[\d\.,/\- ]{6,20})'
    match = re.search(pattern, text, re.I)
    if not match:
        pattern = r'(?<!Due\s)Date\s*:?\s*((?:[\d ]{1,4})?(?:[a-z]{3,12})?[\d\.,/\- ]{6,20})'
        match = re.search(pattern, text, re.I)
    return (match.group(1)).strip().strip('.').strip() if match else None

def extract_due_date(text):
    pattern = r'(?:(?:Due\s*Date)|(?:Payment\s*Due))\s*:?\s*((?:[\d ]{1,4})?(?:[a-z]{3,12})?[\d\.,/\- ]{6,20})'
    match = re.search(pattern, text, re.I)
    if not match:
        pattern = r'(?<!Total\s)(?<!Amount\s)Due\s*:?\s*((?:[\d ]{1,4})?(?:[a-z]{3,12})?[\d\.,/\- ]{6,20})'
        match = re.search(pattern, text, re.I)
    if not match:
        pattern = r'payment\s*deadline\s*(?:on|is)?:?\s*((?:[\d ]{1,4})?(?:[a-z]{3,12})?[\d\.,/\- ]{6,20})'
        match = re.search(pattern, text, re.I)
    return (match.group(1)).strip().strip('.').strip() if match else None

def extract_tax_amount(text):
    pattern = r'(?:VAT|GST|Sales\s*Tax|Tax)\s*(?:\(?\d+%\)?)?\s*:\s*(?:[a-z]{2,4}\s*)?([\d,\.]+)'
    match = re.search(pattern, text, re.I)
    return (match.group(1)).strip().strip('.').strip() if match else None

def extract_total_amount(text):
    pattern = r'(?:Total\s*Amount|Amount\s*Due|Total\s*Due|Grand\s*Total|(?<!sub)Total)\s*:\s*(?:[a-z]{2,4}\s*)?([\d,\.]+)'
    match = re.search(pattern, text, re.I)
    return (match.group(1)).strip().strip('.').strip() if match else None

def extract_currency(text):
    pattern = r'Currency\s*:?\s*([a-z]{2,4})'
    match = re.search(pattern, text, re.I)
    if not match:
        pattern = pattern = r'(?:Total\s*Amount|Amount\s*Due|Total\s*Due|Grand\s*Total|(?<!sub)Total)\s*:\s*([a-z]{2,4})?\s*[\d,\.]+\s*([a-z]{2,4})?'
        match = re.search(pattern, text, re.I)
    if not match:
        return None
    currency = match.group(1) or match.group(2)
    return currency.strip().upper() if currency else None

def extract_status(text):
    pattern = r'(?:Payment)?\s*Status:\s*(\w+)'
    match = re.search(pattern, text, re.I)
    if match:
        if match.group(1).upper()=='PENDING' or match.group(1).upper()=='UNPAID':
            return 'PENDING'
        return match.group(1).upper()
    negative_pattern = r'(?:not\s+(?:yet\s+)?(?:been\s+)?paid|unpaid|not\s+paid)'
    if re.search(negative_pattern, text, re.I):
        return 'PENDING'
    positive_pattern = r'\bpaid\b'
    if re.search(positive_pattern, text, re.I):
        return 'PAID'
    return None

def extract_vendor_address(text):
    lines = [l.strip() for l in text.strip().split('\n') if l.strip()]
    if len(lines)<2:
        return None
    label_patterns = r'(tax\s*)?inv(?:oice)?|^receipt\b|@|www\.|^bill\s*to|^customer|^invoice\s*(no|number|#|reference)|^date'
    vendor_address = None
    for line in lines[1:4]:
        if re.search(label_patterns, line, re.I):
            continue        
        if is_plausible_address(line):
            vendor_address = line
            break
    return vendor_address


def is_plausible_address(line):
    if len(line)<6:
        return False
    has_comma = ',' in line
    has_digit = bool(re.search(r'\d', line))
    address_keywords = re.search(r'\b(street|st\.|road|rd\.|avenue|ave\.|lane|zone|park|drive|way)\b', line, re.I)
    return has_comma or has_digit or bool(address_keywords)


def validate_file_format(file_path):
    # Check 1: file actually exists
    if not os.path.isfile(file_path):
        raise ValueError(f"File not found: '{file_path}'")

    # Check 2: extension check (catches obvious mismatches, e.g. .docx renamed... 
    if not file_path.lower().endswith('.pdf'):
        raise ValueError(f"Invalid file format: '{file_path}' does not have a .pdf extension")

    # Check 3: file isn't empty
    if os.path.getsize(file_path) == 0:
        raise ValueError(f"File is empty: '{file_path}'")

    # Check 4: genuine PDF magic bytes - every real PDF starts with '%PDF'
    # This catches files that were renamed to .pdf but are actually something else
    # (e.g. a .txt or .docx file renamed to trick the extension check above)
    try:
        with open(file_path, 'rb') as f:
            header = f.read(5)
    except Exception as e:
        raise ValueError(f"Could not read file '{file_path}': {e}")

    if not header.startswith(b'%PDF'):
        raise ValueError(f"Invalid file format: '{file_path}' does not appear to be a genuine PDF file")

    return True


def extract_text(pdf_path):
    validate_file_format(str(pdf_path))
    pdf = None

    try:
        pdf = pdfplumber.open(pdf_path)
        text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()])
    except Exception as e:
        raise ValueError(f"Could not process PDF '{pdf_path}': corrupted or unreadable — {e}")
    finally:
        if pdf is not None:
            pdf.close()
    
    text = '\n'.join([page.extract_text() for page in pdf.pages if page.extract_text()!=''])
    invoice_number = extract_invoice_number(text)
    vendor_name = extract_vendor_name(text)
    customer_name = extract_customer_name(text)
    invoice_date = extract_invoice_date(text)
    due_date = extract_due_date(text)
    tax_amount = extract_tax_amount(text)
    total_amount = extract_total_amount(text)
    currency = extract_currency(text)
    payment_status = extract_status(text)
    vendor_address = extract_vendor_address(text)

    return Invoice(invoice_number, customer_name, invoice_date, due_date, tax_amount, total_amount, currency, payment_status), Vendor(vendor_name, vendor_address)

