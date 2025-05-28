import streamlit as st
import pandas as pd
import pdfplumber
from collections import defaultdict
from fpdf import FPDF
import io
import re
import os
from datetime import datetime

HISTORY_DIR = "rapporthistorik"
REVIEWED_DIR = "granskade_ordrar"
os.makedirs(HISTORY_DIR, exist_ok=True)
os.makedirs(REVIEWED_DIR, exist_ok=True)

# --- MÅSTE KOMMA FÖRST ---
st.set_page_config(page_title="Jämförelse: Leverans vs Faktura", layout="wide")

# --- GLOBAL CSS FÖR SCROLL ---
st.markdown("""
    <style>
        .block-container {
            max-height: 90vh;
            overflow-y: auto;
            padding-bottom: 5rem;
        }
    </style>
""", unsafe_allow_html=True)

# --- FUNKTION: Kontroll Pressglass ---
def kontroll_pressglass():
    def extract_orders_from_confirmation(pdf_file):
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_file)
        text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
        lines = text.splitlines()

        orders = defaultdict(int)
        for line in lines:
            parts = line.strip().split()
            for i, part in enumerate(parts):
                if re.fullmatch(r"\d{7}", part):
                    try:
                        qty_candidates = [p for p in parts[i+1:] if re.fullmatch(r"\d+", p)]
                        if qty_candidates:
                            qty = int(qty_candidates[0])
                            orders[part] += qty
                    except (ValueError, IndexError):
                        pass
        return orders

    def extract_orders_from_invoice(pdf_file):
        orders = defaultdict(int)
        invoice_id = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                lines = page.extract_text().split("\n")
                for line in lines:
                    match = re.search(r"Faktura(?:nr|nummer)[:\s]*([\w\d-]+)", line, re.IGNORECASE)
                    if match:
                        invoice_id = match.group(1)
                current_order = None
                for line in reversed(lines):
                    order_match = re.search(r"Order[:\/\-\s]*?(\d{7})", line)
                    if order_match:
                        current_order = order_match.group(1)
                    elif current_order:
                        qty_matches = re.findall(r"(\d{1,3}(?:[ \.,]?\d{3})*|\d+)\s*(?:pcs|stk|st|szt)?", line)
                        for qty_str in qty_matches:
                            try:
                                normalized = qty_str.replace(".", "").replace(",", "").replace(" ", "")
                                qty = int(normalized)
                                orders[current_order] += qty
                            except ValueError:
                                pass
        return orders, invoice_id

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

    def generate_pdf_report(df, faktura_id, leverans_id):
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
        filename = f"{faktura_id}-{leverans_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}.pdf"
        filepath = os.path.join(HISTORY_DIR, filename)
        pdf.output(filepath)
        return filepath

    st.markdown("### Ladda upp leveransbekräftelse och faktura som PDF")
    col1, col2 = st.columns(2)
    with col1:
        conf_file = st.file_uploader("Ladda upp 1", type="pdf", key="conf")
    with col2:
        fakt_file = st.file_uploader("Ladda upp 2", type="pdf", key="fakt")

    result_container = st.container()
    if conf_file and fakt_file:
        if st.button("✅ Jämför dokument"):
            confirmation_orders = extract_orders_from_confirmation(conf_file)
            faktura_orders, faktura_id = extract_orders_from_invoice(fakt_file)
            df = compare_orders(confirmation_orders, faktura_orders)
            leverans_id = os.path.splitext(conf_file.name)[0]
            st.success("Jämförelsen är klar!")
            with result_container:
                st.dataframe(df, use_container_width=True, height=700)

            saved_path = generate_pdf_report(df, faktura_id or "Faktura", leverans_id)
            with open(saved_path, "rb") as f:
                st.download_button("🔗 Ladda ner PDF-rapport", data=f, file_name=os.path.basename(saved_path))

# --- STREAMLIT UI ---
st.title("🧠 Orderkontrollsystem")
kontroll_pressglass()
