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

# --- PRESSGLASS ---
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

# --- PDF AVVIKELSEANALYS ---
def extract_text_blocks_from_pdf(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.splitlines())
    return lines

def detect_pdf_anomalies(text_lines):
    label_groups = defaultdict(list)
    for line in text_lines:
        if any(key in line.lower() for key in ["vit", "röd", "spröjs", "utan spröjs", "svart"]):
            label_groups[line.strip()].append(line.strip())

    anomaly_report = []
    all_values = [key for key in label_groups.keys()]
    if len(all_values) > 1:
        common = max(label_groups, key=lambda k: len(label_groups[k]))
        for val in all_values:
            if val != common:
                anomaly_report.append({
                    "Text": val,
                    "Förväntat": common,
                    "Status": "Ej OK"
                })
    return anomaly_report

# --- STREAMLIT GRÄNSSNITT ---
st.set_page_config(page_title="Jämförelse: Leverans vs Faktura", layout="centered")
st.title("🧠 Orderkontrollsystem")

tabs = st.tabs(["📄 Kontroll Pressglass", "🧠 Ordergranskning", "📚 Rapporthistorik", "✅ Granskade ordrar"])

with tabs[0]:
    st.info("Ladda upp leveransbekräftelse och faktura som PDF.")
    conf_file = st.file_uploader("Leveransbekräftelse (PDF)", type="pdf")
    fakt_file = st.file_uploader("Faktura (PDF)", type="pdf")

    if conf_file and fakt_file:
        if st.button("✅ Jämför dokument"):
            confirmation_orders = extract_orders_from_confirmation(conf_file)
            faktura_orders, faktura_id = extract_orders_from_invoice(fakt_file)
            df = compare_orders(confirmation_orders, faktura_orders)
            leverans_id = os.path.splitext(conf_file.name)[0]
            st.success("Jämförelsen är klar!")
            st.dataframe(df, use_container_width=True, height=600)

            saved_path = generate_pdf_report(df, faktura_id or "Faktura", leverans_id)
            with open(saved_path, "rb") as f:
                st.download_button("🔗 Ladda ner PDF-rapport", data=f, file_name=os.path.basename(saved_path))

with tabs[1]:
    st.info("Ladda upp en order som PDF med information om fönster, färg, spröjs etc.")
    order_pdf = st.file_uploader("Order (PDF)", type="pdf", key="order_pdf")
    if order_pdf:
        lines = extract_text_blocks_from_pdf(order_pdf)
        st.subheader("🔍 Avvikelseanalys")
        anomalies = detect_pdf_anomalies(lines)
        if not anomalies:
            st.success("Ingen tydlig avvikelse hittad.")
        else:
            feedback_list = []
            for i, anomaly in enumerate(anomalies):
                feedback = st.radio(f"'{anomaly['Text']}' – Förväntat: '{anomaly['Förväntat']}'", ["OK", "EJ OK"], key=f"pdf_feedback_{i}")
                feedback_list.append((anomaly, feedback))
            if st.button("✔️ Klar"):
                filename = os.path.splitext(order_pdf.name)[0] + "_granskning.txt"
                filepath = os.path.join(REVIEWED_DIR, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    for anomaly, response in feedback_list:
                        f.write(f"{anomaly['Text']} – Förväntat: {anomaly['Förväntat']} – Status: {response}\n")
                st.success("Granskningen är sparad.")

with tabs[2]:
    st.info("Tidigare jämförelser som PDF.")
    history_files = sorted(os.listdir(HISTORY_DIR), reverse=True)
    for file in history_files:
        filepath = os.path.join(HISTORY_DIR, file)
        with open(filepath, "rb") as f:
            st.download_button(file, data=f, file_name=file, key=file)

with tabs[3]:
    st.info("Sparade granskningar.")
    reviewed_files = sorted(os.listdir(REVIEWED_DIR), reverse=True)
    for file in reviewed_files:
        filepath = os.path.join(REVIEWED_DIR, file)
        with open(filepath, "r", encoding="utf-8") as f:
            st.text(f"{file}\n{'-'*len(file)}\n{f.read()}\n")
