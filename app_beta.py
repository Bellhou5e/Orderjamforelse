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

st.set_page_config(page_title="Jämförelse: Leverans vs Faktura", layout="centered")

st.markdown("""
    <style>
        .block-container {
            max-height: 90vh;
            overflow-y: auto;
            padding-bottom: 5rem;
        }
    </style>
""", unsafe_allow_html=True)

def kontroll_pressglass():
    def extract_orders_from_confirmation(pdf_file):
        from PyPDF2 import PdfReader
        reader = PdfReader(pdf_file)
        text = "\n".join(page.extract_text() for page in reader.pages)
        lines = text.splitlines()

        orders = defaultdict(int)
        for line in lines:
            reorder_match = re.search(r"Reorder\s+(\d{7})", line)
            qty_match = re.search(r"(\d+)$", line)
            if reorder_match and qty_match:
                order_number = reorder_match.group(1)
                qty = int(qty_match.group(1))
                orders[order_number] += qty
            else:
                line_match = re.search(r"(\d{7})", line)
                qty_match = re.findall(r"(\d+)$", line)
                if line_match and qty_match:
                    order_number = line_match.group(1)
                qty = int(qty_match[0])
                if qty < 1000:  # uteslut felslag
                    orders[order_number] += qty
        return orders

    def extract_orders_from_invoice(pdf_file):
        orders = defaultdict(int)
        current_order = None
        invoice_id = ""
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                lines = page.extract_text().split("\n")
                for line in lines:
                    faktura_id_match = re.search(r"Faktura(?:nr|nummer)[:\s]*([\w\d-]+)", line, re.IGNORECASE)
                    if faktura_id_match:
                        invoice_id = faktura_id_match.group(1)
                    order_match = re.search(r"Zamówienie\s*/\s*Order:\s*(\d{7})", line)
                    if order_match:
                        current_order = order_match.group(1)
                    qty_match = re.search(r"P\s+(\d+(?:[.,]\d+)?)\s*pcs", line, re.IGNORECASE)
                    if current_order and qty_match:
                        qty = int(float(qty_match.group(1).replace(",", ".")))
                        orders[current_order] += qty
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
        conf_file = st.file_uploader("Ladda upp leveransbekräftelse", type="pdf", key="conf")
    with col2:
        fakt_file = st.file_uploader("Ladda upp faktura", type="pdf", key="fakt")

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

def rapporthistorik():
    st.info("Tidigare jämförelser som PDF.")
    history_files = sorted(os.listdir(HISTORY_DIR), reverse=True)
    for file in history_files:
        filepath = os.path.join(HISTORY_DIR, file)
        with open(filepath, "rb") as f:
            st.download_button(file, data=f, file_name=file, key=file)

def extract_text_blocks_from_pdf(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        lines = []
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.splitlines())
    return lines

def detect_pdf_anomalies(text_lines):
    blocks = []
    block = []
    for line in text_lines:
        if re.match(r"Rad\s*\d+", line):
            if block:
                blocks.append(block)
            block = [line]
        else:
            block.append(line)
    if block:
        blocks.append(block)

    anomaly_report = []
    colors = [line for group in blocks for line in group if any(color in line.lower() for color in ["vit", "röd", "svart"])]
    common_color = max(set(colors), key=colors.count) if colors else None

    for block in blocks:
        color_lines = [line for line in block if any(color in line.lower() for color in ["vit", "röd", "svart"])]
        for color in color_lines:
            if color != common_color:
                header = f"{block[0]} - {next((l for l in block if 'AF' in l or 'AVF' in l), '')}"
                anomaly_report.append({
                    "Header": header,
                    "Detaljer": [l for l in block[1:] if l != color],
                    "Avvikelse": color,
                    "Förväntat": common_color
                })
    return anomaly_report

def orderkontroll():
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
                st.markdown(f"**{anomaly['Header']}**")
                for detail in anomaly['Detaljer']:
                    st.markdown(f"<p style='margin:0 0 2px 10px;'>{detail}</p>", unsafe_allow_html=True)
                response = st.radio("Status", ["OK", "EJ OK"], key=f"feedback_{i}")
                feedback_list.append((anomaly, response))
                st.markdown("---")
            if st.button("✔️ Klar"):
                filename = os.path.splitext(order_pdf.name)[0] + "_granskning.txt"
                filepath = os.path.join(REVIEWED_DIR, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    for anomaly, response in feedback_list:
                        f.write(f"{anomaly['Header']} – {anomaly['Avvikelse']} – Förväntat: {anomaly['Förväntat']} – Status: {response}\n")
                st.success("Granskningen är sparad.")

def granskade_ordrar():
    st.info("Sparade granskningar.")
    reviewed_files = sorted(os.listdir(REVIEWED_DIR), reverse=True)
    for file in reviewed_files:
        filepath = os.path.join(REVIEWED_DIR, file)
        with open(filepath, "r", encoding="utf-8") as f:
            st.text(f"{file}\n{'-'*len(file)}\n{f.read()}\n")

def testyta():
    st.warning("Detta är en testyta för framtida funktioner. Här kan du experimentera utan att påverka något annat.")

# Huvudgränssnitt
st.title("🧠 Orderkontrollsystem")

main_tabs = st.tabs(["📦 Kontroll Pressglass", "🧾 Orderkontroll", "🧪 Testyta"])

with main_tabs[0]:
    sub_tabs = st.tabs(["Jämförelse", "Rapporthistorik"])
    with sub_tabs[0]:
        kontroll_pressglass()
    with sub_tabs[1]:
        rapporthistorik()

with main_tabs[1]:
    sub_tabs2 = st.tabs(["Granskning", "Granskade ordrar"])
    with sub_tabs2[0]:
        orderkontroll()
    with sub_tabs2[1]:
        granskade_ordrar()

with main_tabs[2]:
    testyta()
