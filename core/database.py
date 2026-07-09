import mysql.connector, json, os
from pathlib import Path
from dotenv import load_dotenv


'''Search and Filter functions return invoices if found any else return None'''


ENV_PATH = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=ENV_PATH)

def connect_db():
    required = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise ConnectionError(
            f"Missing environment variable(s): {', '.join(missing)}. "
            f"Check that your .env file exists at the project root and is correctly filled in."
        )
    try:
        conn = mysql.connector.connect(
            host = os.getenv('DB_HOST'),
            user = os.getenv('DB_USER'),
            password = os.getenv('DB_PASSWORD'),
            database = os.getenv('DB_NAME'),
            use_pure = True
        )
        return conn
    except Exception as e:
        raise ConnectionError(f'Cannot connect to the database: {e}')


#----------------------Insert Invoice----------------------

def get_vendor_id(conn, vendor) -> (int | None):
    cursor = conn.cursor()
    cursor.execute(
        'SELECT vendor_id FROM vendor WHERE vendor_name=%(n)s AND vendor_address=%(a)s',
        {'n':vendor.vendor_name, 'a':vendor.vendor_address}
    )
    id = cursor.fetchone()
    cursor.close()
    return id[0] if id else None

def insert_vendor(conn, vendor) -> int:
    vendor_id = get_vendor_id(conn, vendor)
    if not vendor_id:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO vendor (vendor_name, vendor_address) VALUES (%(n)s, %(a)s)',
            {'n':vendor.vendor_name, 'a':vendor.vendor_address}
        )
        conn.commit()
        vendor_id = cursor.lastrowid
        cursor.close()
    return vendor_id
    
def insert_invoice(conn, invoice, vendor) -> str:
    vendor_id = insert_vendor(conn, vendor)
    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO invoice (invoice_number, vendor_id, customer_name, invoice_date, due_date, tax_amount, total_amount, currency, payment_status, validation_status, validation_errors)
        VALUES (%(inv_num)s, %(ven_id)s, %(cust_name)s, %(inv_d)s, %(due_d)s, %(tax)s, %(total)s, %(curr)s, %(pay_st)s, %(val_st)s, %(val_err)s)''',
        {'inv_num':invoice.invoice_number, 'ven_id':vendor_id, 'cust_name':invoice.customer_name, 'inv_d':invoice.invoice_date, 'due_d':invoice.due_date, 'tax':invoice.tax_amount, 
        'total':invoice.total_amount, 'curr':invoice.currency, 'pay_st':invoice.payment_status, 'val_st':invoice.validation_status, 'val_err':json.dumps(invoice.validation_errors)}
    )
    conn.commit()
    cursor.close()
    return invoice.invoice_number


#----------------------Update Invoice----------------------

def update_invoice(conn, current_invoice_number, **fields) -> bool:
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM invoice WHERE invoice_number=%(inv_num)s', {'inv_num':current_invoice_number})
    invoice = cursor.fetchone()

    if not invoice:
        cursor.close()
        return False

    if not fields:
        cursor.close()
        return False
    
    allowed_vendor_keywords = {'vendor_name', 'vendor_address'}
    allowed_invoice_keywods = {'customer_name', 'invoice_date', 'due_date', 'tax_amount',
        'total_amount', 'currency', 'payment_status', 'validation_status', 'validation_errors'}
    updated_any=False
    
    if 'invoice_number' in fields:
        try:
            cursor.execute('UPDATE invoice SET invoice_number=%(upd_num)s WHERE invoice_number=%(curr_num)s', {'curr_num':current_invoice_number, 'upd_num':fields['invoice_number']})
            conn.commit()
            current_invoice_number = fields['invoice_number']
            fields.pop('invoice_number')
            updated_any = True
        except mysql.connector.errors.IntegrityError:
            cursor.close()
            raise ValueError('Invoice Number already exists!')

    for ven_key in allowed_vendor_keywords:
        if ven_key in fields:
            cursor.execute('SELECT vendor_id from invoice WHERE invoice_number=%(inv_num)s', {'inv_num':current_invoice_number})
            vendor_id = cursor.fetchone()
            cursor.execute(f'UPDATE vendor SET {ven_key}=%(ven_val)s WHERE vendor_id=%(ven_id)s', 
                {'ven_val':fields[ven_key], 'ven_id':vendor_id[0]}
            )
            fields.pop(ven_key)
            updated_any=True

    for inv_key in allowed_invoice_keywods:
        if inv_key in fields:
            value = fields[inv_key]
            if inv_key=='validation_errors':
                value = json.dumps(value)
            cursor.execute(f'UPDATE invoice SET {inv_key}=%(inv_val)s WHERE invoice_number=%(inv_num)s',
            {'inv_val':value, 'inv_num':current_invoice_number})
            fields.pop(inv_key)
            updated_any=True
    
    conn.commit()
    cursor.close()
    return updated_any


#----------------------Delete Invoice----------------------

def delete_invoice(conn, invoice_number) -> bool:
    cursor = conn.cursor()
    cursor.execute('DELETE FROM invoice WHERE invoice_number=%(inv_num)s', {'inv_num':invoice_number})
    conn.commit()
    deleted = cursor.rowcount > 0
    cursor.close()
    return deleted


#----------------------Search by Invoice Number----------------------

def search_by_invoice_number(conn, invoice_number) -> (list | None):
    cursor = conn.cursor()
    cursor.execute('''SELECT invoice.*, vendor.vendor_name, vendor.vendor_address 
    FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id 
    WHERE invoice.invoice_number=%(inv_num)s''', {'inv_num':invoice_number})
    invoice = cursor.fetchone()
    if invoice:
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
    cursor.close()
    return invoice if invoice else None


#----------------------Search by Vendor----------------------

def get_vendors(conn, vendor_name) -> (list[tuple] | None):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM vendor WHERE vendor_name LIKE %(ven_name)s', 
        {'ven_name':f'%{vendor_name}%'})
    vendors = cursor.fetchall()
    cursor.close()
    return vendors if vendors else None

def search_by_vendor(conn, vendor_id) -> (list[list] | None):
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM invoice WHERE vendor_id=%(ven_id)s', {'ven_id':vendor_id})
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice
    cursor.close()
    return invoices if invoices else None
    

#----------------------Filter by Date----------------------
    
def filter_by_date(conn, start_date, end_date, date_field='processed_date') -> (list[list] | None):
    allowed_date_fields = {'processed_date', 'invoice_date', 'due_date'}
    if date_field not in allowed_date_fields:
        raise ValueError(f'Date field must be one of {allowed_date_fields}')
    
    cursor = conn.cursor()
    cursor.execute(f'''SELECT invoice.*, vendor.vendor_name, vendor.vendor_address
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id
        WHERE {date_field} >= %(st_d)s AND {date_field} < %(end_d)s + INTERVAL 1 DAY''',
        {'st_d':start_date, 'end_d':end_date})
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice
    cursor.close()
    return invoices if invoices else None
    

#----------------------Filter by Payment Status----------------------

def filter_by_payment_status(conn, payment_status) -> (list[list] | None):
    cursor = conn.cursor()
    cursor.execute('''SELECT invoice.*, vendor.vendor_name, vendor.vendor_address 
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id 
        WHERE invoice.payment_status=%(pay_st)s''', {'pay_st':payment_status})
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice
    cursor.close()
    return invoices if invoices else None


#----------------------Filter by Amount----------------------

def filter_by_amount(conn, min_amount, max_amount, amount_field='total_amount') -> (list[list] | None):
    allowed_amount_fields = {'total_amount', 'tax_amount'}
    if amount_field not in allowed_amount_fields:
        raise ValueError(f'Amount field must be one of {allowed_amount_fields}')

    cursor = conn.cursor()
    cursor.execute(f'''SELECT invoice.*, vendor.vendor_name, vendor.vendor_address
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id
        WHERE {amount_field} BETWEEN %(min_am)s AND %(max_am)s''',
        {'min_am':min_amount, 'max_am':max_amount})
    invoices = cursor.fetchall()
    for count, invoice in enumerate(invoices):
        invoice = list(invoice)
        invoice[10] = json.loads(invoice[10])
        invoices[count] = invoice
    cursor.close()
    return invoices if invoices else None


#----------------------Dashboard Stats----------------------

def get_total_invoices(conn) -> int:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM invoice')
    count = cursor.fetchone()[0]
    cursor.close()
    return count

def get_total_vendors(conn) -> int:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM vendor')
    count = cursor.fetchone()[0]
    cursor.close()
    return count

def get_total_amount(conn) -> float:
    cursor = conn.cursor()
    cursor.execute('SELECT COALESCE(sum(total_amount), 0) FROM invoice')
    total_amount = cursor.fetchone()[0]
    cursor.close()
    return float(total_amount)

def get_pending_payment_count(conn) -> int:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM invoice WHERE payment_status=%(status)s', {'status':'PENDING'})
    count = cursor.fetchone()[0]
    cursor.close()
    return count

def get_validation_errors_count(conn) -> int:
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM invoice WHERE JSON_LENGTH(validation_errors)>0')
    count = cursor.fetchone()[0]
    cursor.close()
    return count

def get_recent_invoices(conn, limit=10) -> (list[tuple] | None):
    limit = int(limit)
    cursor = conn.cursor()
    cursor.execute(
        f'''SELECT invoice.invoice_number, vendor.vendor_name, invoice.total_amount, invoice.currency, 
        invoice.payment_status, invoice.validation_status, invoice.processed_date
        FROM invoice INNER JOIN vendor ON invoice.vendor_id=vendor.vendor_id
        ORDER BY invoice.processed_date DESC LIMIT {limit}'''
    )
    invoices = cursor.fetchall()
    cursor.close()
    return invoices if invoices else None
    