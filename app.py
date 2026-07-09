import os, gc
import tempfile
from datetime import date, datetime

import streamlit as st
import pandas as pd

from core import *

st.set_page_config(page_title="Smart Invoice Processing System", layout="wide")


# ---------------------------------------------------------------------------
# DB connection (cached across reruns)

@st.cache_resource
def get_connection():
    return database.connect_db()


def get_conn_safe():
    try:
        conn = get_connection()
        conn.ping(reconnect=True, attempts=3, delay=2)
        return conn, None
    except Exception as e:
        get_connection.clear()
        try:
            conn = get_connection()
            return conn, None
        except Exception as e2:
            return None, str(e2)


# ---------------------------------------------------------------------------
# Sidebar navigation

st.sidebar.title("📄 Invoice System")
page = st.sidebar.radio(
    "Navigate",
    ["Dashboard", "Upload Invoices", "Manage Invoices", "Search & Filter", "Reports"],
)

conn, conn_error = get_conn_safe()
if conn_error:
    st.sidebar.error(f"Database not connected:\n{conn_error}")
    st.warning(
        "The app can't reach the database right now. Pages that read/write "
        "invoice data won't work until the connection is fixed. Check your "
        "MySQL server and the credentials in database.py / your .env file."
    )


# ---------------------------------------------------------------------------
# Helpers

log = get_logger()

INVOICE_COLUMNS = [
    'invoice_number', 'vendor_id', 'customer_name', 'invoice_date', 'due_date',
    'tax_amount', 'total_amount', 'currency', 'payment_status',
    'validation_status', 'validation_errors', 'processed_date',
    'vendor_name', 'vendor_address',
]

def rows_to_df(rows):
    if not rows:
        return pd.DataFrame(columns=INVOICE_COLUMNS)
    df = pd.DataFrame(rows, columns=INVOICE_COLUMNS)
    return df.drop(columns=['vendor_id'])

def status_badge(status):
    colors = {
        'Validated': '🟢', 'Needs Review': '🟡', 'Invalid': '🔴', 'Unvalidated': '⚪',
        'PAID': '🟢', 'PENDING': '🟡', 'OVERDUE': '🔴',
    }
    return f"{colors.get(status, '⚪')} {status}"

def render_export_buttons(df, base_filename):
    if df is None or df.empty:
        return
    dl1, dl2 = st.columns(2)
    excel_bytes = exporter.to_excel_bytes(df)
    csv_bytes = exporter.to_csv_bytes(df)
    if dl1.download_button(
        "⬇ Download Excel", excel_bytes,
        file_name=exporter.safe_filename(base_filename, "xlsx"),
        mime=exporter.EXCEL_MIME,
        key=f"{base_filename}_xlsx",
    ):
        log.info(f"Export requested: {base_filename}.xlsx ({len(df)} rows)")
    if dl2.download_button(
        "⬇ Download CSV", csv_bytes,
        file_name=exporter.safe_filename(base_filename, "csv"),
        mime=exporter.CSV_MIME,
        key=f"{base_filename}_csv",
    ):
        log.info(f"Export requested: {base_filename}.csv ({len(df)} rows)")


# ---------------------------------------------------------------------------
# PAGE: Dashboard

if page == "Dashboard":
    st.title("Dashboard")

    if conn:
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Invoices", database.get_total_invoices(conn))
        c2.metric("Total Vendors", database.get_total_vendors(conn))
        c3.metric("Total Amount", f"{database.get_total_amount(conn):,.2f}")
        c4.metric("Pending Payments", database.get_pending_payment_count(conn))
        c5.metric("Validation Errors", database.get_validation_errors_count(conn))

        st.subheader("Recently Processed Invoices")
        recent = database.get_recent_invoices(conn, limit=10)
        if recent:
            df = pd.DataFrame(
                recent,
                columns=['Invoice #', 'Vendor', 'Total', 'Currency',
                         'Payment Status', 'Validation Status', 'Processed'],
            )
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No invoices processed yet. Upload one to get started.")
    else:
        st.stop()


# ---------------------------------------------------------------------------
# PAGE: Upload Invoices
# ---------------------------------------------------------------------------
elif page == "Upload Invoices":
    st.title("Upload Invoices")
    st.caption("Upload one or more PDF invoices. Each will be extracted, validated, and stored.")

    uploaded_files = st.file_uploader(
        "Choose PDF invoice(s)", type=["pdf"], accept_multiple_files=True
    )

    if uploaded_files and st.button("Process Invoices", type="primary"):
        if not conn:
            st.error("Cannot process invoices without a database connection.")
        else:
            results = []
            progress = st.progress(0, text="Starting...")

            for i, uf in enumerate(uploaded_files):
                log.info(f'Uploaded file: {uf.name}')
                progress.progress((i) / len(uploaded_files), text=f"Processing {uf.name}...")
                tmp_path = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(uf.getbuffer())
                        tmp_path = tmp.name

                    invoice, vendor = extract_text(tmp_path)
                    invoice, vendor = validate(conn, invoice, vendor)

                    if invoice.validation_status == 'Invalid':
                        log.warning(f"Invalid invoice rejected: {uf.name} - {invoice.validation_errors}")
                        results.append({
                            'File': uf.name, 'Status': '❌ Invalid — not saved',
                            'Invoice #': invoice.invoice_number or '—',
                            'Details': '; '.join(invoice.validation_errors),
                        })
                    else:
                        database.insert_invoice(conn, invoice, vendor)
                        if invoice.validation_status == 'Needs Review':
                            log.info(f"Invoice needs review: {invoice.invoice_number} - {invoice.validation_errors}")
                        else:
                            log.info(f"Invoice processed successfully: {invoice.invoice_number}")
                        badge = '🟡 Needs Review' if invoice.validation_status == 'Needs Review' else '✅ Saved'
                        results.append({
                            'File': uf.name, 'Status': badge,
                            'Invoice #': invoice.invoice_number,
                            'Details': '; '.join(invoice.validation_errors) or '—',
                        })
                except Exception as e:
                    results.append({
                        'File': uf.name, 'Status': '⚠️ Failed to process',
                        'Invoice #': '—', 'Details': str(e),
                    })
                finally:
                    if tmp_path and os.path.exists(tmp_path):
                        gc.collect()
                        try:
                            os.remove(tmp_path)
                        except PermissionError:
                            pass
            progress.progress(1.0, text="Done")
            st.subheader("Results")
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

            saved = sum(1 for r in results if 'Saved' in r['Status'] or 'Review' in r['Status'])
            st.success(f"{saved} of {len(results)} invoice(s) saved to the database.")


# ---------------------------------------------------------------------------
# PAGE: Manage Invoice (update / delete)

elif page == "Manage Invoices":
    st.title("Manage Invoices")
    st.caption("Search for an invoice to view, edit, or delete it.")

    if not conn:
        st.stop()

    search_num = st.text_input("Enter Invoice Number to manage")
    if st.button("Load Invoice", type="primary") and search_num:
        row = database.search_by_invoice_number(conn, search_num)
        if row:
            st.session_state['manage_invoice'] = row
            st.session_state.pop('confirm_delete', None)
        else:
            st.session_state.pop('manage_invoice', None)
            st.warning(f"No invoice found with number '{search_num}'.")

    if 'manage_invoice' in st.session_state:
        row = st.session_state['manage_invoice']

        st.divider()
        st.subheader(f"Editing Invoice: {row[0]}")

        with st.form("edit_invoice_form"):
            c1, c2 = st.columns(2)
            new_invoice_number = c1.text_input("Invoice Number", value=row[0])
            new_customer_name = c2.text_input("Customer Name", value=row[2] or "")

            c3, c4 = st.columns(2)
            new_invoice_date = c3.date_input("Invoice Date", value=row[3])
            new_due_date = c4.date_input("Due Date", value=row[4])

            c5, c6 = st.columns(2)
            new_tax_amount = c5.number_input("Tax Amount", value=float(row[5] or 0), min_value=0.0)
            new_total_amount = c6.number_input("Total Amount", value=float(row[6] or 0), min_value=0.0)

            c7, c8 = st.columns(2)
            new_currency = c7.text_input("Currency", value=row[7] or "")
            status_options = ["PENDING", "PAID", "OVERDUE", "CANCELLED"]
            new_payment_status = c8.selectbox(
                "Payment Status", status_options,
                index=status_options.index(row[8]) if row[8] in status_options else 0
            )

            st.markdown("**Vendor Details** — _editing these updates the vendor everywhere, not just this invoice_")
            c9, c10 = st.columns(2)
            new_vendor_name = c9.text_input("Vendor Name", value=row[12] or "")
            new_vendor_address = c10.text_input("Vendor Address", value=row[13] or "")

            st.markdown("**Validation** — _manually override if you've reviewed this invoice and disagree with the automated flags_")
            c11, c12 = st.columns(2)
            status_opts = ["Unvalidated", "Validated", "Needs Review", "Invalid"]
            new_validation_status = c11.selectbox(
                "Validation Status", status_opts,
                index=status_opts.index(row[9]) if row[9] in status_opts else 0
            )
            new_validation_errors_text = c12.text_area(
                "Validation Errors (one per line)",
                value='\n'.join(row[10]) if row[10] else '',
                height=100,
            )

            submitted = st.form_submit_button("Save Changes", type="primary")
            validated_button = st.form_submit_button("Mark as Validated & Clear Errors", type="primary")
            fields_to_update = {}
            if validated_button:
                new_validation_status = 'Validated'
                new_validation_errors = []
            else:
                new_validation_errors = [line.strip() for line in new_validation_errors_text.split('\n') if line.strip()]

        if submitted or validated_button:
            if new_invoice_number != row[0]:
                fields_to_update['invoice_number'] = new_invoice_number
            if new_customer_name != row[2]:
                fields_to_update['customer_name'] = new_customer_name
            if str(new_invoice_date) != str(row[3]):
                fields_to_update['invoice_date'] = new_invoice_date
            if str(new_due_date) != str(row[4]):
                fields_to_update['due_date'] = new_due_date
            if new_tax_amount != row[5]:
                fields_to_update['tax_amount'] = new_tax_amount
            if new_total_amount != row[6]:
                fields_to_update['total_amount'] = new_total_amount
            if new_currency != row[7]:
                fields_to_update['currency'] = new_currency
            if new_payment_status != row[8]:
                fields_to_update['payment_status'] = new_payment_status
            if new_vendor_name != row[12]:
                fields_to_update['vendor_name'] = new_vendor_name
            if new_vendor_address != row[13]:
                fields_to_update['vendor_address'] = new_vendor_address
            if new_validation_status != row[9]:
                fields_to_update['validation_status'] = new_validation_status
            if new_validation_errors != row[10]:
                fields_to_update['validation_errors'] = new_validation_errors

            if not fields_to_update:
                st.info("No changes detected.")
            else:
                try:
                    success = database.update_invoice(conn, row[0], **fields_to_update)
                    if success:
                        log.info(f"Invoice {row[0]} updated. Changed fields: {list(fields_to_update.keys())}")
                        st.success(f"Invoice updated. Changed: {', '.join(fields_to_update.keys())}")
                        refreshed = database.search_by_invoice_number(
                            conn, fields_to_update.get('invoice_number', row[0])
                        )
                        if refreshed:
                            row = refreshed
                            st.session_state['manage_invoice'] = refreshed
                    else:
                        st.warning("No changes were saved.")
                except ValueError as e:
                    st.error(str(e))

        st.divider()
        st.subheader("Danger Zone")

        if not st.session_state.get('confirm_delete'):
            if st.button("🗑️ Delete This Invoice"):
                st.session_state['confirm_delete'] = True
        else:
            st.warning(f"Are you sure you want to permanently delete invoice **{row[0]}**? This cannot be undone.")
            dc1, dc2 = st.columns(2)
            if dc1.button("Yes, delete it", type="primary"):
                deleted = database.delete_invoice(conn, row[0])
                st.session_state.pop('manage_invoice', None)
                st.session_state.pop('confirm_delete', None)
                if deleted:
                    log.info(f"Invoice {row[0]} deleted.")
                    st.success(f"Invoice {row[0]} deleted.")
                else:
                    st.error("Deletion failed — invoice may have already been removed.")
            if dc2.button("Cancel"):
                st.session_state.pop('confirm_delete', None)


# ---------------------------------------------------------------------------
# PAGE: Search & Filter

elif page == "Search & Filter":
    st.title("Search & Filter")

    if not conn:
        st.stop()

    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["By Invoice Number", "By Vendor", "By Date", "By Payment Status", "By Amount"]
    )

    with tab1:
        inv_num = st.text_input("Invoice Number")
        if st.button("Search", key="search_num") and inv_num:
            row = database.search_by_invoice_number(conn, inv_num)
            if row:
                st.dataframe(rows_to_df([row]), use_container_width=True, hide_index=True)
            else:
                st.info("No invoice found with that number.")

    with tab2:
        vendor_query = st.text_input("Vendor name contains...")
        if st.button("Search", key="search_vendor") and vendor_query:
            vendors = database.get_vendors(conn, vendor_query)
            if vendors:
                for vid, vname, vaddr in vendors:
                    with st.expander(f"{vname} — {vaddr or 'no address'}"):
                        invs = database.search_by_vendor(conn, vid)
                        if invs:
                            st.dataframe(
                                pd.DataFrame(invs, columns=INVOICE_COLUMNS[:-2]),
                                use_container_width=True, hide_index=True,
                            )
                        else:
                            st.caption("No invoices for this vendor yet.")
            else:
                st.info("No matching vendors.")

    with tab3:
        date_field = st.selectbox("Date field", ["processed_date", "invoice_date", "due_date"])
        c1, c2 = st.columns(2)
        start = c1.date_input("Start date", value=date.today().replace(day=1))
        end = c2.date_input("End date", value=date.today())
        if st.button("Filter", key="filter_date"):
            rows = database.filter_by_date(conn, start, end, date_field=date_field)
            st.dataframe(rows_to_df(rows), use_container_width=True, hide_index=True)
    
    with tab4:
        status_field = st.selectbox("Payment Status", ["PENDING", "PAID", "OVERDUE"])
        if st.button("Filter", key="filter_status"):
            rows = database.filter_by_payment_status(conn, status_field)
            st.dataframe(rows_to_df(rows), use_container_width=True, hide_index=True)

    with tab5:
        amount_field = st.selectbox("Amount field", ["total_amount", "tax_amount"])
        c1, c2 = st.columns(2)
        min_amt = c1.number_input("Min amount", min_value=0.0, value=0.0)
        max_amt = c2.number_input("Max amount", min_value=0.0, value=100000.0)
        if st.button("Filter", key="filter_amount"):
            rows = database.filter_by_amount(conn, min_amt, max_amt, amount_field=amount_field)
            st.dataframe(rows_to_df(rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# PAGE: Reports

elif page == "Reports":
    st.title("Reports")

    if not conn:
        st.stop()

    report_type = st.selectbox(
        "Report type",
        ["Daily Invoice Report",
         "Monthly Invoice Summary",
         "Vendor Wise Report",
         "Tax Summary",
         "Outstanding Payments Report"
        ]
    )

    if report_type == "Daily Invoice Report":
        report_date = st.date_input("Report date", value=date.today())

        if st.button("Generate Report", type="primary"):
            st.session_state['daily_report'] = get_daily_report(
                conn, report_date=report_date
            )

        if 'daily_report' in st.session_state:
            report = st.session_state['daily_report']

            if not report['total_count']:
                st.info(f"No invoices found for {report_date}.")
            else:
                df = rows_to_df(report['invoices'])

                st.subheader(f"Report Date: {report['date']}")
                m1, m2 = st.columns(2)
                m1.metric("Total Invoices", report['total_count'])
                m2.metric("Total Amount", f"{report['total_amount']:,.2f}")
                
                st.subheader('Processed Invoices')
                st.dataframe(df, use_container_width=True, hide_index=True)
                render_export_buttons(df, f"daily_report_{report['date']}")

    elif report_type == "Monthly Invoice Summary":
        c1, c2 = st.columns(2)
        months = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = c1.selectbox("Month", months)
        month = months.index(month_name) + 1
        year = c2.number_input(
            "Year",
            min_value=2000,
            max_value=2100,
            value=datetime.now().year
        )
        
        if st.button('Generate', type='primary'):
            st.session_state['monthly_summary'] = get_monthly_summary(conn, month, year)
            st.session_state['monthly_summary_params'] = (month, year)

        if 'monthly_summary' in st.session_state:
            cached_month, cached_year = st.session_state.get('monthly_summary_params', (None, None))

            if (cached_month, cached_year) != (month, year):
                st.info("Selection changed — click **Generate** to see results for the newly selected month/year.")
            else:
                summary = st.session_state['monthly_summary']
                if not summary['total_count']:
                    st.info(f"No invoices found for {month_name} {year}.")
                else:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Total Invoices", summary['total_count'])
                    m2.metric("Total Amount", f"{summary['total_amount']:,.2f}")
                    m3.metric("Total Tax", f"{summary['total_tax']:,.2f}")
                    m4.metric("Vendors Involved", summary['vendor_count'])

                    if summary['needs_attention_count'] > 0:
                        st.warning(f"⚠️ {summary['needs_attention_count']} invoice(s) need review or are invalid.")
                    
                    st.subheader("Payment Status Breakdown")
                    if summary['status_breakdown']:
                        status_df = pd.DataFrame([
                            {'Status': status, 'Count': data['count'], 'Amount': data['amount']}
                            for status, data in summary['status_breakdown'].items()
                        ])
                        sc1, sc2 = st.columns(2)
                        with sc1:
                            st.dataframe(status_df, use_container_width=True, hide_index=True)
                            render_export_buttons(status_df, f"monthly_summary_{month_name}_{year}")
                        with sc2:
                            st.bar_chart(status_df.set_index('Status')['Amount'])
                    else:
                        st.caption("No payment status data available.")

    elif report_type == "Vendor Wise Report":
        if st.button('Generate', type='primary'):
            st.session_state['vendor_report'] = get_vendor_wise_report(conn)

        if 'vendor_report' in st.session_state:
            vendor_report = st.session_state['vendor_report']

            if not vendor_report:
                st.info("No vendors found in the database.")
            else:
                df = pd.DataFrame(vendor_report)
                df = df.drop(columns=['vendor_id'])
                df = df.rename(columns={
                    'vendor_name': 'Vendor',
                    'vendor_address': 'Address',
                    'invoice_count': 'Invoices',
                    'total_billed': 'Total Billed',
                    'total_tax': 'Total Tax',
                    'outstanding_amount': 'Outstanding',
                    'average_invoice': 'Avg. Invoice'
                })

                total_vendors = len(df)
                total_billed_all = df['Total Billed'].sum()
                total_outstanding_all = df['Outstanding'].sum()
                vendors_with_outstanding = (df['Outstanding'] > 0).sum()

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Vendors", total_vendors)
                m2.metric("Total Billed (all)", f"{total_billed_all:,.2f}")
                m3.metric("Total Outstanding", f"{total_outstanding_all:,.2f}")
                m4.metric("Vendors with Balance Due", vendors_with_outstanding)

                st.subheader("Top Vendors by Amount Billed")
                if total_vendors <= 3:
                    top_n = total_vendors
                else:
                    top_n = st.slider("Show top N vendors", min_value=3, max_value=min(20, total_vendors), value=min(10, total_vendors))
                chart_df = df.nlargest(top_n, 'Total Billed').set_index('Vendor')
                st.bar_chart(chart_df['Total Billed'])

                st.subheader("Full Vendor Breakdown")
                show_only_outstanding = st.checkbox("Show only vendors with outstanding balance")
                display_df = df[df['Outstanding'] > 0] if show_only_outstanding else df
                
                st.dataframe(
                    display_df.style.format({
                        'Total Billed': '{:,.2f}',
                        'Total Tax': '{:,.2f}',
                        'Outstanding': '{:,.2f}',
                        'Avg. Invoice': '{:,.2f}',
                    }),
                    use_container_width=True,
                    hide_index=True,
                )
                render_export_buttons(display_df, "vendor_wise_report")

    elif report_type == "Tax Summary":
        use_date_range = st.checkbox("Filter by date range")

        start_date = None
        end_date = None
        if use_date_range:
            c1, c2 = st.columns(2)
            start_date = c1.date_input("Start date", value=date.today().replace(day=1))
            end_date = c2.date_input("End date", value=date.today())

        if st.button('Generate', type='primary'):
            st.session_state['tax_summary'] = get_tax_summary(conn, start_date, end_date)

        if 'tax_summary' in st.session_state:
            summary = st.session_state['tax_summary']

            if not summary['tax_by_vendor']:
                st.info("No tax data found for the selected range.")
            else:
                if summary['start_date'] and summary['end_date']:
                    st.subheader(f"Tax Summary: {summary['start_date']} to {summary['end_date']}")
                else:
                    st.subheader("Tax Summary: All Time")

                st.subheader("Tax by Currency")
                currency_cols = st.columns(max(1, len(summary['tax_by_currency'])))
                for col, (currency, data) in zip(currency_cols, summary['tax_by_currency'].items()):
                    col.metric(f"{currency} Tax Collected", f"{data['tax_amount']:,.2f}", help=f"{data['invoice_count']} invoice(s)")

                st.subheader("Tax by Vendor")
                vendor_df = pd.DataFrame(summary['tax_by_vendor'])
                vendor_df = vendor_df.rename(columns={
                    'vendor_name': 'Vendor',
                    'invoice_count': 'Invoices',
                    'tax_amount': 'Tax Amount'
                })

                vc1, vc2 = st.columns([2, 1])
                with vc1:
                    st.dataframe(
                        vendor_df.style.format({'Tax Amount': '{:,.2f}'}),
                        use_container_width=True,
                        hide_index=True,
                    )
                    render_export_buttons(vendor_df, "tax_summary_by_vendor")
                with vc2:
                    st.bar_chart(vendor_df.set_index('Vendor')['Tax Amount'])

    elif report_type == "Outstanding Payments Report":
        if st.button('Generate', type='primary'):
            st.session_state['outstanding'] = get_outstanding_payments(conn)

        if 'outstanding' in st.session_state:
            report = st.session_state['outstanding']

            if not report['invoices']:
                st.success("✅ No outstanding payments — everything is paid up!")
            else:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Total Outstanding", report['total_count'])
                m2.metric("Total Amount Due", f"{report['total_outstanding_amount']:,.2f}")
                m3.metric("Pending", report['pending_count'], f"{report['pending_amount']:,.2f}")
                m4.metric("Overdue", report['overdue_count'], f"{report['overdue_amount']:,.2f}", delta_color="inverse")

                COLUMNS = ['invoice_number', 'vendor_id', 'customer_name', 'invoice_date', 'due_date',
                       'tax_amount', 'total_amount', 'currency', 'payment_status', 'validation_status',
                       'validation_errors', 'processed_date', 'vendor_name', 'vendor_address', 'days_overdue']
                df = pd.DataFrame(report['invoices'], columns=COLUMNS)

                def urgency_label(days):
                    if days > 0:
                        return f"🔴 {days}d overdue"
                    else:
                        return f"🟡 due in {abs(days)}d"

                df['Urgency'] = df['days_overdue'].apply(urgency_label)
                df = df.rename(columns={
                    'invoice_number': 'Invoice #', 'vendor_name': 'Vendor',
                    'due_date': 'Due Date', 'total_amount': 'Amount',
                    'currency': 'Currency', 'payment_status': 'Status'
                })

                display_cols = ['Invoice #', 'Vendor', 'Due Date', 'Amount', 'Currency', 'Status', 'Urgency']
                st.subheader("Outstanding Invoices (sorted by due date)")
                st.dataframe(
                    df[display_cols].style.format({'Amount': '{:,.2f}'}),
                    use_container_width=True,
                    hide_index=True,
                )
                render_export_buttons(df[display_cols], "outstanding_payments")


