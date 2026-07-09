class Invoice:
    def __init__(self, invoice_number, customer_name,
                invoice_date, due_date, tax_amount, total_amount,
                currency, payment_status='PENDING', validation_status='Unvalidated',
                validation_errors=None):
        self.invoice_number = invoice_number
        self.customer_name = customer_name
        self.invoice_date = invoice_date
        self.due_date = due_date
        self.tax_amount = tax_amount
        self.total_amount = total_amount
        self.currency = currency
        self.payment_status = payment_status
        self.validation_status = validation_status
        self.validation_errors = validation_errors if validation_errors is not None else []
    
    def to_dict(self):
        return self.__dict__
    
    def __repr__(self):
        return f'Invoice({self.invoice_number}, {self.total_amount} {self.currency})'
    

class Vendor:
    def __init__(self, vendor_name, vendor_address):
        self.vendor_name = vendor_name
        self.vendor_address = vendor_address
    
    def __repr__(self):
        return f'Vendor({self.vendor_name}: {self.vendor_address})'
    