CREATE DATABASE invoice_management;

use invoice_management;

CREATE TABLE IF NOT EXISTS vendor (
	vendor_id INT PRIMARY KEY AUTO_INCREMENT,
	vendor_name VARCHAR(100) NOT NULL,
    vendor_address VARCHAR(150),
    UNIQUE KEY unique_vendor (vendor_name, vendor_address)
);

CREATE TABLE IF NOT EXISTS invoice (
	invoice_number VARCHAR(30) PRIMARY KEY,
    vendor_id INT,
    customer_name VARCHAR(100),
    invoice_date DATE NOT NULL,
    due_date DATE,
    tax_amount FLOAT,
    total_amount FLOAT,
    currency VARCHAR(5),
    payment_status VARCHAR(10),
    validation_status VARCHAR(15),
    validation_errors JSON,
    processed_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vendor_id) REFERENCES vendor(vendor_id)
);

