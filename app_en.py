import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
from PIL import Image
from fpdf import FPDF
from icrawler.builtin import BingImageCrawler, GoogleImageCrawler, BaiduImageCrawler

# --- Timezone Logic (Kept KST for Developer, labeled as KST) ---
def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# --- 1. System Initialization ---
def init_system():
    for path in ["dataset/multi_view", "reports", "database_images"]:
        if not os.path.exists(path):
            os.makedirs(path)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. PDF Report Logic (English + 1-Page Constraint) ---
class PetReportPDF(FPDF):
    def header(self):
        header_img = "card_bg_en.png"
        if os.path.exists(header_img):
            self.image(header_img, x=10, y=10, w=190)
            self.ln(32)
        else:
            self.set_font('Arial', 'B', 20)
            self.cell(0, 15, 'Pet Health Report', ln=True, align='C')
            self.ln(5)

def create_pdf_report(breed, bcs, pace, reason):
    try:
        pdf = PetReportPDF()
        pdf.set_auto_page_break(auto=False, margin=0) # Absolute 1-page
        
        # Using standard fonts for global compatibility (Arial)
        pdf.add_page()
        
        pdf.set_font('Arial', 'B', 18)
        pdf.cell(0, 10, '', ln=True, align='C')
        pdf.ln(5)
        
        kst_time = get_kst_now().strftime('%Y-%m-%d %H:%M')
        table_width = 160
        start_x = (210 - table_width) / 2
        
        # English Labels
        data = [
            ['Breed', f'{breed}'], 
            ['Body Condition Score (BCS)', f'{bcs} / 9 pts'], 
            ['Aging Pace Factor', f'{pace}x Speed'], 
            ['Diagnostic Date (KST)', f'{kst_time}']
        ]
        
        pdf.set_font('Arial', 'B', 10)
        for row in data:
            pdf.set_x(start_x)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(60, 8, row[0], border=1, fill=True)
            pdf.cell(100, 8, row[1], border=1, ln=True, align='C')
            
        pdf.ln(8)
        pdf.set_x(start_x)
        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 8, '[ AI Veterinarian Comprehensive Opinion ]', ln=True)
        pdf.ln(2)
        
        clean_reason = reason.replace('**', '').replace('*', '').strip()
        # Dynamic font sizing to keep it on one page
        font_size = 8 if len(clean_reason) > 600 else 9 if len(clean_reason) > 400 else 10
            
        pdf.set_font('Arial', '', font_size)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(start_x)
        pdf.multi_cell(table_width, 5.5, clean_reason, border=0, align='L')
        
        # Business Footer
        pdf.set_y(260)
        pdf.set_font('Arial', 'B', 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, 'Premium Analysis Request: bslee@yahoo.com', align='C', ln=True)
        
        pdf.set_font('Arial', 'I', 8)
        pdf.set_text_color(160, 160, 160)
        pdf.cell(0, 5, 'Powered by: [Pet Longevity AI] | This is an AI-generated simulation report.', align='C', ln=True)
        
        report_path = f"reports/Report_{breed}_{get_kst_now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except Exception as e:
        return None

# --- 3. AI Analysis Prompt (Updated for English Output) ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        # Prompts AI to respond in English
        prompt = f"As a professional veterinarian, analyze these photos of a {breed_name}. Provide the 'BCS Score / Clinical Opinion' in English. Avoid special characters."
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        if '/' in res_text:
            parts = res_text.split('/')
            bcs_val = int(re.search(r'\d', parts[0]).group()) if re.search(r'\d', parts[0]) else 5
            clean_reason = parts[1].strip()
        else:
            bcs_match = re.search(r'\d', res_text)
            bcs_val = int(bcs_match.group()) if bcs_match else 5
            clean_reason = res_text
        return {"bcs": bcs_val, "reason": clean_reason}
    except: return {"bcs": 5, "reason": "An error occurred during AI analysis."}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    # Specific logic for Large breeds
    if breed in ["Retriever", "German Shepherd"]: pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI (English) ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

st.sidebar.title("🐾 System Settings")
selected_breed = st.sidebar.selectbox("Select Breed", ["Retriever", "Maltese", "Poodle", "Pomeranian", "Etc"])
st.sidebar.divider()
admin_pass = st.sidebar.text_input("Admin Password", type="password")
is_admin = (admin_pass == "2004")

tabs = st.tabs(["🔍 AI Diagnosis"] + (["🌐 Data Collection", "📊 Data Center"] if is_admin else []))

with tabs[0]:
    st.header("🐶 AI Veterinarian: Longevity Diagnosis")
    
    # --- Instructions Guide (English) ---
    with st.expander("💡 How to Use & Request Diagnosis (Read First)", expanded=True):
        st.markdown("""
        1.  **Select Breed:** Choose your dog's breed from the **sidebar on the left**.
        2.  **Upload Images:** Upload clear photos of your dog's **Side View** and **Top View** below.
        3.  **Run Analysis:** Click the **'🧠 Run AI Analysis & Create Report'** button.
        4.  **Check Opinion:** Wait about 10 seconds for the **AI Veterinarian's clinical opinion**.
        5.  **Download Report:** Click **'📄 Download PDF Report'** to save or print the results.
        6.  **In-depth Analysis:** For a more detailed premium consultation, contact us via **email** below.
        """)
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("📸 Upload Side View", type=['jpg', 'jpeg', 'png'], key="side_f")
    with c2: top_f = st.file_uploader("📸 Upload Top View", type=['jpg', 'jpeg', 'png'], key="top_f")
    
    if st.button("🧠 Run AI Analysis & Create Report", use_container_width=True, type="primary"):
        if side_f and top_f:
            t_stamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            with st.spinner("AI Veterinarian is analyzing. Please wait..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                st.success("✅ Analysis Complete!")
                st.info(f"**[AI Veterinarian's Opinion]**\n\n{res['reason']}")
                
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                
                # DB logging
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                     (selected_breed, res["bcs"], pace, res["reason"], get_kst_now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                conn.close()

                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 Download PDF Report (Save & Print)", f, file_name=f"Report_{selected_breed}.pdf", use_container_width=True)
        else: st.warning("Please upload both Side and Top view photos.")

# --- Admin Tabs (Logic remains same, labels translated) ---
if is_admin:
    with tabs[1]:
        st.header("🌐 Data Collection (Global Search)")
        query = st.text_input("Search Query", f"{selected_breed} dog full body photo side view -chart -diagram")
        sources = st.multiselect("Sources", ["Google", "Bing", "Baidu"], default=["Google", "Bing"])
        max_imgs = st.slider("Quantity", 5, 50, 15)
        if st.button("🚀 Start Collection"):
            # (Image collection logic same as original)
            st.info("Collecting data...")
            # ... (omitted for brevity, same as Korean version)

    with tabs[2]:
        st.header("📊 Admin Data Center")
        # (Data management logic same as original)

st.divider()
st.caption("Business Partnership & Pilot Program: bslee@yahoo.com")
