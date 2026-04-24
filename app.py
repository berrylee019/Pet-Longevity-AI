import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
import time  # 재시도 대기 시간을 위해 추가
from PIL import Image
from fpdf import FPDF
import traceback

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
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

@st.cache_resource
def load_gemini_model(api_key):
    genai.configure(api_key=api_key)
    # 가장 빠르고 효율적인 1.5-flash 모델 권장
    return genai.GenerativeModel('gemini-2.0-flash')

init_system()

# --- 2. PDF 생성 로직 (최적화) ---
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
        pdf.cell(0, 10, '', ln=True, align='C')
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
        font_size = 10 if len(clean_reason) < 400 else 9
        
        pdf.set_font('NanumGothic', 'B', font_size)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(start_x)
        pdf.multi_cell(table_width, 5.5, clean_reason, border=0, align='L')
        
        pdf.set_y(260) 
        pdf.set_font('NanumGothic', 'B', 11)
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 8, '초정밀 분석 요청: bslee@yahoo.com', align='C', ln=True)
        
        report_path = f"reports/Report_{breed}_{get_kst_now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except Exception as e:
        st.error(f"PDF 생성 중 오류: {e}")
        return None

# --- 3. AI 분석 로직 (자동 재시도 및 오류 처리 강화) ---
def analyze_pet_with_retry(model, side_img_path, top_img_path, breed_name, max_retries=3):
    side_img = Image.open(side_img_path)
    top_img = Image.open(top_img_path)
    
    prompt = f"""
    당신은 20년 경력의 베테랑 수의사입니다. {breed_name}의 옆모습과 윗모습을 정밀 분석하세요.
    반드시 한국어로 '점수'와 '소견'을 구분하여 아주 상세하게(500자 이상) 작성하세요.
    마크다운(**)은 생략하고 텍스트로만 정중하게 작성하세요.
    
    형식:
    점수: [숫자]
    소견: [상세 내용]
    """

    for i in range(max_retries):
        try:
            response = model.generate_content(
                [prompt, side_img, top_img],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,
                    temperature=0.7
                )
            )
            res_text = response.text.strip()
            
            # 파싱 로직
            bcs_val = 5
            score_match = re.search(r'점수:\s*(\d)', res_text)
            if score_match:
                bcs_val = int(score_match.group(1))
            
            clean_reason = res_text.split("소견:")[1].strip() if "소견:" in res_text else res_text
            
            return {"bcs": bcs_val, "reason": clean_reason}

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                if i < max_retries - 1:
                    wait_time = (i + 1) * 2 # 2초, 4초 대기 후 재시도
                    time.sleep(wait_time)
                    continue
                else:
                    return {"bcs": 5, "reason": "현재 API 할당량이 초과되었습니다. 약 1분 후 다시 시도해 주세요."}
            return {"bcs": 5, "reason": f"분석 중 오류 발생: {err_msg[:100]}"}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

# API 키 및 모델 로드
if "GEMINI_API_KEY" in st.secrets:
    model = load_gemini_model(st.secrets["GEMINI_API_KEY"])
else:
    st.error("API Key를 찾을 수 없습니다. Secrets 설정을 확인해 주세요.")
    st.stop()

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2864/2864248.png", width=60)
    st.title("MisaTech AI")
    st.markdown("---")
    
    st.title("🐾 시스템 설정")
    selected_breed = st.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
    st.divider()
    admin_pass = st.text_input("관리자 비번", type="password")
    is_admin = (admin_pass == "2004")

tabs = st.tabs(["🔍 정밀 분석 및 PDF"] + (["🌐 데이터 센터"] if is_admin else []))

with tabs[0]:
    st.header("🐶 AI 수의사 노화 정밀 진단")
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("옆모습 업로드", type=['jpg', 'jpeg', 'png'], key="side")
    with c2: top_f = st.file_uploader("윗모습 업로드", type=['jpg', 'jpeg', 'png'], key="top")
    
    if st.button("🧠 분석 실행 및 리포트 생성", use_container_width=True):
        if side_f and top_f:
            t_stamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            
            with st.spinner("AI가 사진을 분석하고 있습니다. (최대 10초 소요)"):
                res = analyze_pet_with_retry(model, s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                st.subheader("📋 AI 분석 소견")
                st.info(res['reason'])
                
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 PDF 진단서 다운로드", f, 
                                         file_name=f"Report_{selected_breed}_{t_stamp}.pdf", 
                                         use_container_width=True)
                
                # 로그 저장
                try:
                    conn = sqlite3.connect('pet_analysis.db')
                    conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                          (selected_breed, res["bcs"], pace, res["reason"], get_kst_now().strftime('%Y-%m-%d %H:%M')))
                    conn.commit()
                    conn.close()
                except:
                    pass
        else:
            st.warning("옆모습과 윗모습 사진을 모두 업로드해주세요.")

st.divider()
st.caption("비즈니스 문의: bslee@yahoo.com | Powered by MisaTech SUROP")
