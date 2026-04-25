import streamlit as st
from google import genai
from google.genai import types
import os
import sqlite3
import datetime
import re
import pandas as pd
import time
from PIL import Image
from fpdf import FPDF

# [CRITICAL] set_page_config MUST be the first Streamlit command
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

# --- 1. System Initialization ---
def init_db():
    for folder in ["dataset/multi_view", "reports", "database_images"]:
        os.makedirs(folder, exist_ok=True)
    
    conn = sqlite3.connect('pet_health.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS health_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, opinion TEXT, date TEXT)''')
    conn.commit()
    conn.close()

@st.cache_resource
def get_ai_client():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        # Correct initialization for google-genai v1.0+
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to load AI Client: {e}")
        return None

init_db()
client = get_ai_client()

# --- 2. PDF Generation ---
class PetPDF(FPDF):
    def header(self):
        # Ensure card_bg1.png exists or remove this block
        if os.path.exists("card_bg1.png"):
            self.image("card_bg1.png", x=10, y=10, w=190)
            self.ln(35)
        else:
            self.set_font('Helvetica', 'B', 20)
            self.cell(0, 15, 'Pet Longevity Analysis Report', ln=True, align='C')
            self.ln(5)

def create_report(breed, bcs, pace, opinion):
    pdf = PetPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)
    
    # Summary Table
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(50, 10, 'Target Breed', border=1, fill=True)
    pdf.cell(140, 10, f'{breed}', border=1, ln=True)
    pdf.cell(50, 10, 'Body Score (BCS)', border=1, fill=True)
    pdf.cell(140, 10, f'{bcs} / 9', border=1, ln=True)
    pdf.cell(50, 10, 'Aging Pace', border=1, fill=True)
    pdf.cell(140, 10, f'{pace}x speed', border=1, ln=True)
    
    pdf.ln(10)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, '[ AI Clinical Opinion ]', ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 6, opinion.replace('*', ''))
    
    pdf.set_y(265)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(0, 10, "Inquiry: bslee@yahoo.com", align='C')
    
    report_name = f"reports/Report_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    pdf.output(report_name)
    return report_name

# --- 3. AI Analysis Logic ---
def analyze_pet_vision(side_path, top_path, breed, max_retries=3):
    # 1. 초기 결과값 설정 (에러 발생 시에도 이 형식을 유지하여 TypeError 방지)
    result = {"bcs": 5, "opinion": "Starting analysis..."}
    
    if client is None:
        result["opinion"] = "AI Client not initialized. Please check API Key."
        return result

    try:
        side_img = Image.open(side_path)
        top_img = Image.open(top_path)
        
        prompt = f"""
        You are a veteran veterinarian with 20 years of experience. 
        Analyze the side and top view images of this {breed}.
        Provide the BCS (Body Condition Score) on a scale of 1-9.
        Format your response exactly as:
        Score: [Number]
        Opinion: [Detailed explanation in English]
        """

        # i 반복문 시작
        for attempt in range(max_retries):
            try:
                # [404 방어] 후보 모델명을 순차적으로 테스트
                model_names = ["models/gemini-1.5-flash", "models/gemini-1.5-flash-latest", "models/gemini-1.5-pro"]
                text = ""
                success = False

                for m_name in model_names:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=[prompt, side_img, top_img]
                        )
                        text = response.text
                        success = True
                        break # 성공하면 모델 루프 탈출
                    except Exception as inner_e:
                        if "404" in str(inner_e):
                            continue # 다음 모델로 시도
                        else:
                            raise inner_e # 429 등은 상위 try로 전달

                if not success:
                    raise Exception("All models failed with 404.")

                # 결과 파싱
                score = 5
                match = re.search(r'Score:\s*(\d)', text)
                if match: score = int(match.group(1))
                
                opinion = text.split("Opinion:")[1].strip() if "Opinion:" in text else text
                
                result["bcs"] = score
                result["opinion"] = opinion
                return result # 성공 시 최종 반환

            except Exception as e:
                err_msg = str(e).upper()
                if "429" in err_msg:
                    wait_time = (attempt + 1) * 15
                    st.warning(f"Quota exceeded. Retrying in {wait_time}s... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue # 다음 재시도로
                else:
                    result["opinion"] = f"AI Error: {str(e)[:100]}"
                    break # 치명적 에러 시 중단

    except Exception as e:
        result["opinion"] = f"System Error: {str(e)[:100]}"
    
    return result

# --- 4. Main UI ---
st.title("🐾 Pet Longevity AI (Global)")

with st.sidebar:
    st.header("Settings")
    breed = st.selectbox("Select Breed", ["Retriever", "Maltese", "Poodle", "Pomeranian"])
    admin_code = st.text_input("Admin Code", type="password")

t1, t2 = st.tabs(["Diagnosis", "Data Logs"])

with t1:
    col1, col2 = st.columns(2)
    with col1: side_f = st.file_uploader("Side View Image", type=['jpg', 'jpeg', 'png'])
    with col2: top_f = st.file_uploader("Top View Image", type=['jpg', 'jpeg', 'png'])
    
    if st.button("Run AI Diagnosis", type="primary", use_container_width=True):
        if side_f and top_f:
            with st.spinner("Analyzing pet health..."):
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                s_path, t_path = f"database_images/{ts}_s.png", f"database_images/{ts}_t.png"
                with open(s_path, "wb") as f: f.write(side_f.getbuffer())
                with open(t_path, "wb") as f: f.write(top_f.getbuffer())
                
                res = analyze_pet_vision(s_path, t_path, breed)
                pace = round(1.0 + (abs(5 - res['bcs']) * 0.15), 2)
                
                st.subheader("Results")
                st.write(res['opinion'])
                
                pdf_file = create_report(breed, res['bcs'], pace, res['opinion'])
                with open(pdf_file, "rb") as f:
                    st.download_button("📩 Download PDF Report", f, file_name=f"{breed}_Report.pdf")
                
                # Log to DB
                conn = sqlite3.connect('pet_health.db')
                conn.cursor().execute("INSERT INTO health_logs (breed, bcs, pace, opinion, date) VALUES (?,?,?,?,?)",
                                     (breed, res['bcs'], pace, res['opinion'], datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                conn.close()
        else:
            st.warning("Please upload both images.")

if admin_code == "2004":
    with t2:
        conn = sqlite3.connect('pet_health.db')
        df = pd.read_sql_query("SELECT * FROM health_logs ORDER BY id DESC", conn)
        st.dataframe(df)
        conn.close()

st.divider()
st.caption("Contact: bslee@yahoo.com")
