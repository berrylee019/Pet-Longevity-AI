import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
import time
from PIL import Image
from fpdf import FPDF
import traceback
import subprocess
import sys

# 라이브러리 버전 강제 업데이트 로직
def upgrade_library():
    try:
        import google.generativeai as genai
        # 버전 체크 (예: 0.5.0 미만이면 업데이트)
        if float('.'.join(genai.__version__.split('.')[:2])) < 0.5:
            raise ImportError
    except (ImportError, AttributeError):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-U", "google-generativeai"])
        st.rerun() # 업데이트 후 앱 재실행

# 실행 (한 번 업데이트되면 다음부터는 건너뜁니다)
# upgrade_library()

# --- 한국 시간(KST) 설정 ---
def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)

# --- 1. 시스템 초기화 및 모델 캐싱 ---
def init_system():
    for path in ["dataset/multi_view", "reports", "database_images"]:
        os.makedirs(path, exist_ok=True)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    conn.commit()
    conn.close()

@st.cache_resource
def load_gemini_model(api_key):
    try:
        genai.configure(api_key=api_key)
        # 404 에러 방지를 위해 가장 표준적인 모델명 사용
        model = genai.GenerativeModel('gemini-1.5-flash')
        return model
    except Exception as e:
        st.error(f"모델 로드 중 오류 발생: {e}")
        return None

init_system()

# --- 2. PDF 생성 로직 ---
class PetReportPDF(FPDF):
    def header(self):
        header_img = "card_bg1.png"
        if os.path.exists(header_img):
            self.image(header_img, x=10, y=10, w=190)
            self.ln(32)
        else:
            self.set_font('Helvetica', 'B', 20)
            self.cell(0, 15, 'Pet Health Report', ln=True, align='C')
            self.ln(5)

def create_pdf_report(breed, bcs, pace, reason):
    try:
        pdf = PetReportPDF()
        pdf.set_auto_page_break(auto=False, margin=0)
        font_path = "NanumGothicBold.ttf"
        if not os.path.exists(font_path): return None
        
        pdf.add_font('NanumGothic', 'B', font_path, uni=True)
        pdf.add_page()
        pdf.set_font('NanumGothic', 'B', 18)
        pdf.ln(5)
        
        table_width = 160
        start_x = (210 - table_width) / 2
        data = [['진단 대상 견종', f'{breed}'], ['체형 점수 (BCS)', f'{bcs} / 9 점'], 
                ['예상 노화 속도', f'{pace} 배속'], ['진단 일시', get_kst_now().strftime('%Y-%m-%d %H:%M')]]
        
        pdf.set_font('NanumGothic', 'B', 10)
        for row in data:
            pdf.set_x(start_x)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(50, 8, row[0], border=1, fill=True)
            pdf.cell(110, 8, row[1], border=1, ln=True, align='C')
            
        pdf.ln(8)
        pdf.set_x(start_x)
        pdf.set_font('NanumGothic', 'B', 14)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 8, '[ AI 수의사 종합 소견 ]', ln=True)
        pdf.ln(2)
        
        clean_reason = reason.replace('**', '').replace('*', '').strip()
        pdf.set_font('NanumGothic', 'B', 9)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(start_x)
        pdf.multi_cell(table_width, 5.5, clean_reason, border=0, align='L')
        
        pdf.set_y(260) 
        pdf.set_font('NanumGothic', 'B', 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, '초정밀 분석 요청: bslee@yahoo.com', align='C', ln=True)
        
        report_path = f"reports/Report_{get_kst_now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except Exception as e:
        st.error(f"PDF 생성 오류: {e}")
        return None

# --- 3. AI 분석 로직 (재시도 + 404 예외처리) ---
def analyze_pet_with_retry(model, side_img_path, top_img_path, breed_name, max_retries=3):
    if model is None:
        return {"bcs": 5, "reason": "모델이 정상적으로 로드되지 않았습니다. API 키와 라이브러리 버전을 확인해주세요."}

    side_img = Image.open(side_img_path)
    top_img = Image.open(top_img_path)
    
    prompt = f"""
    당신은 20년 경력의 베테랑 수의사입니다. {breed_name}의 옆모습과 윗모습 사진을 정밀 분석하세요.
    반드시 한국어로 '점수'와 '소견'을 구분하여 상세하게 작성하세요.
    형식:
    점수: [숫자]
    소견: [상세 내용]
    """

    for i in range(max_retries):
        try:
            # 이미지와 텍스트를 함께 전달
            response = model.generate_content([prompt, side_img, top_img])
            res_text = response.text.strip()
            
            bcs_val = 5
            score_match = re.search(r'점수:\s*(\d)', res_text)
            if score_match:
                bcs_val = int(score_match.group(1))
            
            clean_reason = res_text.split("소견:")[1].strip() if "소견:" in res_text else res_text
            return {"bcs": bcs_val, "reason": clean_reason}

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg: # 할당량 초과
                time.sleep((i + 1) * 2)
                continue
            elif "404" in err_msg: # 모델 못 찾음
                return {"bcs": 5, "reason": "API 모델(1.5-flash)을 찾을 수 없습니다. 라이브러리를 업데이트하거나 모델명을 확인해주세요."}
            else:
                return {"bcs": 5, "reason": f"분석 오류: {err_msg[:100]}"}
    
    return {"bcs": 5, "reason": "재시도 횟수를 초과했습니다. 잠시 후 다시 시도해주세요."}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    model = load_gemini_model(st.secrets["GEMINI_API_KEY"])
else:
    st.error("Secrets에 GEMINI_API_KEY가 없습니다.")
    st.stop()

with st.sidebar:
    st.title("MisaTech AI")
    selected_breed = st.selectbox("대상 견종", ["리트리버", "말티즈", "푸들", "포메라니안"])
    admin_pass = st.text_input("관리자 비번", type="password")
    is_admin = (admin_pass == "2004")

tabs = st.tabs(["🔍 정밀 분석 및 PDF", "🌐 데이터 센터"])

with tabs[0]:
    st.header("🐶 AI 수의사 노화 정밀 진단")
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("옆모습", type=['jpg', 'png'], key="side")
    with c2: top_f = st.file_uploader("윗모습", type=['jpg', 'png'], key="top")
    
    if st.button("🧠 분석 실행", use_container_width=True):
        if side_f and top_f:
            t_stamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            
            with st.spinner("AI 분석 중..."):
                res = analyze_pet_with_retry(model, s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                st.info(res['reason'])
                
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 PDF 다운로드", f, file_name=f"Report_{t_stamp}.pdf", use_container_width=True)
        else:
            st.warning("사진을 모두 업로드해주세요.")

if is_admin and tabs[1]:
    st.subheader("📊 분석 로그")
    conn = sqlite3.connect('pet_analysis.db')
    df = pd.read_sql_query("SELECT * FROM analysis_logs", conn)
    st.dataframe(df)
    conn.close()

st.divider()
st.caption("비즈니스 문의: bslee@yahoo.com")
