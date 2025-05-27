import streamlit as st
import pandas as pd
import pdfplumber
from collections import defaultdict
from fpdf import FPDF
import io
import re


def extract_orders_from_confirmation(pdf_file):
    from PyPDF2 import PdfReader
    reader = PdfReader(pdf_file)
    text = "\n".join(page.extract_text() for page in reader.pages)
    lines = text.splitlines()

    orders = defaultdict(int)
    for line in lines:
        parts = line.strip().split()
        if len(parts) >= 6 and parts[3].isdigit():
            order_number = parts[3]
            try:
                qty = int(parts[-1])
                orders[order_number] += qty
            except ValueError:
                pass
    return orders

def extract_orders_from_invoice(pdf_file):
    orders = defaultdict(int)
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            lines = page.extract_text().split("\n")
            current_order = None
            for line in reversed(lines):
                order_match = re.search(r"Order[:\/\-]?\s*(\d{7})", line)
                if order_match:
                    current_order = order_match.group(1)
                elif current_order:
                    qty_matches = re.findall(r"(\d+[\.,]?\d*)\s*pcs", line, re.IGNORECASE)
                    for qty_str in qty_matches:
                        try:
                            qty = int(float(qty_str.replace(",", ".")))
                            orders[current_order] += qty
                        except ValueError:
                            pass
    return orders

def compare_orders(confirmation, invoice):
    all_orders = set(confirmation.keys()) | set(invoice.keys())
    result = []
    for order in sorted(all_orders):
        leverans = confirmation.get(order, 0)
        faktura = invoice.get(order, 0)
        result.append({
            "Ordernummer": order,
            "Antal (Leveransbekräftelse)": leverans,
            "Antal (Faktura)": faktura,
            "Matchar?": "JA" if leverans == faktura else "NEJ"
        })
    return pd.DataFrame(result)

def generate_pdf_report(df):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 10, "Orderjämförelse: Leveransbekräftelse vs Faktura", ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    headers = ["Ordernummer", "Antal (Leveransbekräftelse)", "Antal (Faktura)", "Matchar?"]
    col_widths = [40, 70, 40, 30]
    for i, header in enumerate(headers):
        pdf.cell(col_widths[i], 10, header, 1, 0, 'C', fill=True)
    pdf.ln()
    pdf.set_font("Arial", size=12)
    for _, row in df.iterrows():
        pdf.cell(col_widths[0], 10, str(row["Ordernummer"]), 1)
        pdf.cell(col_widths[1], 10, str(row["Antal (Leveransbekräftelse)"]), 1)
        pdf.cell(col_widths[2], 10, str(row["Antal (Faktura)"]), 1)
        pdf.cell(col_widths[3], 10, row["Matchar?"], 1)
        pdf.ln()
    output_bytes = pdf.output(dest='S').encode('latin1')
    return io.BytesIO(output_bytes)

# Streamlit-gränssnitt
st.set_page_config(page_title="Jämförelse: Leverans vs Faktura", layout="centered")
st.title("📝 Orderjämförelse: Leveransbekräftelse vs Faktura")

st.info("Ladda upp leveransbekräftelse och faktura som PDF.")

conf_file = st.file_uploader("Leveransbekräftelse (PDF)", type="pdf")
fakt_file = st.file_uploader("Faktura (PDF)", type="pdf")

if conf_file and fakt_file:
    if st.button("✅ Jämför dokument"):
        confirmation_orders = extract_orders_from_confirmation(conf_file)
        faktura_orders = extract_orders_from_invoice(fakt_file)
        df = compare_orders(confirmation_orders, faktura_orders)
        st.success("Jämförelsen är klar!")
        st.dataframe(df)

        pdf_buf = generate_pdf_report(df)
        st.download_button("🔗 Ladda ner PDF-rapport", data=pdf_buf, file_name="jamforelse.pdf")
