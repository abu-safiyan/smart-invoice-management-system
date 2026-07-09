import json

def get_daily_report(conn, report_date) -> dict:
    cursor = conn.cursor()
    cursor.execute('''SELECT invoice.*, vendor.vendor_name, vendor.vendor_address
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id
        WHERE DATE(processed_date)=%(rep_d)s''', {'rep_d':report_date}
    )
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice
    
    cursor.execute('''SELECT COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoice
        WHERE DATE(processed_date)=%(rep_d)s''', {'rep_d':report_date})
    total_count, total_amount = cursor.fetchone()

    cursor.close()
    return {
        'date':report_date,
        'invoices':invoices,
        'total_count':total_count,
        'total_amount':float(total_amount)
    }


def get_monthly_summary(conn, month, year) -> dict:
    cursor = conn.cursor()

    cursor.execute('''SELECT COUNT(*), COALESCE(SUM(total_amount), 0), COALESCE(SUM(tax_amount), 0),
        COUNT(DISTINCT vendor_id) FROM invoice
        WHERE YEAR(invoice_date) = %(yr)s AND MONTH(invoice_date) = %(mo)s''',
        {'yr': year, 'mo': month})
    invoice_count, total_amount, total_tax, vendor_count = cursor.fetchone()

    cursor.execute('''SELECT payment_status, COUNT(*), COALESCE(SUM(total_amount), 0) FROM invoice
        WHERE YEAR(invoice_date) = %(yr)s AND MONTH(invoice_date) = %(mo)s
        GROUP BY payment_status''', {'yr': year, 'mo': month})
    status_breakdown = {row[0]: {'count':row[1], 'amount':float(row[2])} for row in cursor.fetchall()}

    cursor.execute('''SELECT COUNT(*) FROM invoice
        WHERE YEAR(invoice_date) = %(yr)s AND MONTH(invoice_date) = %(mo)s
        AND validation_status IN ('Needs Review', 'Invalid')
    ''', {'yr': year, 'mo': month})
    needs_attention_count = cursor.fetchone()[0]

    cursor.close()
    return {
        'month': month,
        'year': year,
        'total_count': invoice_count,
        'total_amount': float(total_amount),
        'total_tax': float(total_tax),
        'vendor_count': vendor_count,
        'status_breakdown': status_breakdown,
        'needs_attention_count': needs_attention_count
    }


def get_vendor_wise_report(conn) -> list[dict]:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT vendor.vendor_id, vendor.vendor_name, vendor.vendor_address,
               COUNT(invoice.invoice_number) AS invoice_count,
               COALESCE(SUM(invoice.total_amount), 0) AS total_billed,
               COALESCE(SUM(invoice.tax_amount), 0) AS total_tax,
               COALESCE(SUM(CASE WHEN invoice.payment_status != 'PAID' THEN invoice.total_amount ELSE 0 END), 0) AS outstanding_amount
        FROM vendor LEFT JOIN invoice ON vendor.vendor_id = invoice.vendor_id
        GROUP BY vendor.vendor_id, vendor.vendor_name, vendor.vendor_address
        ORDER BY total_billed DESC
    ''')
    rows = cursor.fetchall()
    cursor.close()

    report = []
    for vendor_id, name, address, count, total_billed, total_tax, outstanding in rows:
        report.append({
            'vendor_id': vendor_id,
            'vendor_name': name,
            'vendor_address': address,
            'invoice_count': count,
            'total_billed': float(total_billed),
            'total_tax': float(total_tax),
            'outstanding_amount': float(outstanding),
            'average_invoice': float(total_billed)/count if count>0 else 0.0
        })
    return report


def get_tax_summary(conn, start_date=None, end_date=None) -> dict:
    cursor = conn.cursor()

    if start_date and end_date:
        date_filter = 'WHERE invoice_date BETWEEN %(st_d)s AND %(end_d)s'
        params = {'st_d': start_date, 'end_d': end_date}
    elif start_date:
        date_filter = 'WHERE invoice_date >= %(st_d)s'
        params = {'st_d': start_date}
    elif end_date:
        date_filter = 'WHERE invoice_date < %(end_d)s + INTERVAL 1 DAY'
        params = {'end_d': end_date}
    else:
        date_filter = ''
        params = {}

    cursor.execute(f'''
        SELECT vendor.vendor_name, COUNT(invoice.invoice_number), COALESCE(SUM(invoice.tax_amount), 0)
        FROM invoice INNER JOIN vendor ON invoice.vendor_id = vendor.vendor_id
        {date_filter}
        GROUP BY vendor.vendor_id, vendor.vendor_name
        ORDER BY COALESCE(SUM(invoice.tax_amount), 0) DESC
    ''', params)
    tax_by_vendor = [
        {'vendor_name': row[0], 'invoice_count': row[1], 'tax_amount': float(row[2])}
        for row in cursor.fetchall()
    ]

    cursor.execute(f'''
        SELECT currency, COUNT(*), COALESCE(SUM(tax_amount), 0)
        FROM invoice {date_filter}
        GROUP BY currency
    ''', params)
    tax_by_currency = {row[0]: {'invoice_count': row[1], 'tax_amount': float(row[2])} for row in cursor.fetchall()}

    cursor.close()
    return {
        'start_date': start_date,
        'end_date': end_date,
        'tax_by_vendor': tax_by_vendor,
        'tax_by_currency': tax_by_currency
    }


def get_outstanding_payments(conn) -> dict:
    cursor = conn.cursor()
    cursor.execute('''
        SELECT invoice.*, vendor.vendor_name, vendor.vendor_address,
            DATEDIFF(CURDATE(), invoice.due_date) AS days_overdue
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id
        WHERE invoice.payment_status IN ('PENDING', 'OVERDUE')
        ORDER BY invoice.due_date ASC
    ''')
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice

    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0)
        FROM invoice WHERE payment_status IN ('PENDING', 'OVERDUE')
    ''')
    total_count, total_outstanding = cursor.fetchone()

    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0)
        FROM invoice WHERE payment_status = 'PENDING'
    ''')
    pending_count, pending_amount = cursor.fetchone()

    cursor.execute('''
        SELECT COUNT(*), COALESCE(SUM(total_amount), 0)
        FROM invoice WHERE payment_status = 'OVERDUE'
    ''')
    overdue_count, overdue_amount = cursor.fetchone()

    cursor.close()
    return {
        'invoices': invoices,
        'total_count': total_count,
        'total_outstanding_amount': float(total_outstanding),
        'pending_count': pending_count,
        'pending_amount': float(pending_amount),
        'overdue_count': overdue_count,
        'overdue_amount': float(overdue_amount)
    }