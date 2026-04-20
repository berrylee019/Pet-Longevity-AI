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
import traceback

# --- 한국 시간(KST) 설정 로직 ---
def get_kst_now():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    return datetime.datetime.now(kst)
    
# --- 1. 시스템 초기화 ---
# --- 1. 시스템 초기화 (수정 버전) ---
def init_system():
    # exist_ok=True 옵션을 추가하여 이미 폴더가 있어도 에러가 나지 않게 합니다.
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
        pdf.cell(0, 10, '', ln=True, align='C')
        pdf.ln(5)
        
        table_width = 160
        start_x = (210 - table_width) / 2
        data = [['Target Breed', f'{breed}'], ['BCS Score', f'{bcs} / 9'], 
                ['Aging Pace', f'{pace}x'], ['Date', get_kst_now().strftime('%Y-%m-%d %H:%M')]]
        
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
        pdf.cell(0, 8, '[ AI Veterinarian Opinion ]', ln=True)
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
        pdf.cell(0, 8, 'Contact: bslee@yahoo.com', align='C', ln=True)
        
        report_path = f"reports/Report_{breed}_{get_kst_now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except Exception as e:
        st.error(f"PDF Creation Error: {e}")
        return None

# --- 3. AI 분석 로직 (에러 수정판) ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        
        # 프롬프트 강화: 형식을 강제하여 파싱 에러 방지
        prompt = f"Analyze this {breed_name} for Body Condition Score (1-9). Provide result in format: 'Score: [number] / Opinion: [text]'. Avoid special characters."
        
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        # 결과 파싱 로직 개선
        bcs_val = 5
        clean_reason = res_text
        
        if "Score:" in res_text and "Opinion:" in res_text:
            bcs_match = re.search(r'Score:\s*(\d)', res_text)
            if bcs_match: bcs_val = int(bcs_match.group(1))
            clean_reason = res_text.split("Opinion:")[1].strip()
        else:
            # 형식이 다를 경우 숫자만이라도 추출 시도
            nums = re.findall(r'\d', res_text)
            if nums: bcs_val = int(nums[0])

        return {"bcs": bcs_val, "reason": clean_reason}
    except Exception as e:
        # 에러 발생 시 로그에 상세 내용 출력
        print(f"AI ERROR: {str(e)}")
        traceback.print_exc()
        return {"bcs": 5, "reason": f"AI 분석 중 오류가 발생했습니다: {str(e)[:50]}"}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

# 모델 설정 수정 (gemini-1.5-flash 또는 2.0-flash 사용)
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash') # 안정적인 1.5-flash 권장
else:
    st.error("API Key not found in Secrets!")

with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/2864/2864248.png", width=60)
    st.title("MisaTech AI")
    st.markdown("---")
    
st.sidebar.title("🐾 시스템 설정")
selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
st.sidebar.divider()
admin_pass = st.sidebar.text_input("관리자 비번", type="password")
is_admin = (admin_pass == "2004")

tabs = st.tabs(["🔍 정밀 분석 및 PDF"] + (["🌐 이미지 수집", "📊 데이터 센터"] if is_admin else []))

with tabs[0]:
    st.header("🐶 AI 수의사 노화 정밀 진단")
    
    with st.expander("💡 이용 방법 안내", expanded=True):
        st.markdown("1. 견종 선택 2. 사진 업로드 3. 분석 실행 4. 리포트 다운로드")
    
    st.divider()
    
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("옆모습 업로드", type=['jpg', 'jpeg', 'png'])
    with c2: top_f = st.file_uploader("윗모습 업로드", type=['jpg', 'jpeg', 'png'])
    
    if st.button("🧠 분석 실행 및 리포트 생성", width='stretch'):
        if side_f and top_f:
            t_stamp = get_kst_now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            
            with st.spinner("AI가 사진을 정밀 분석 중입니다..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                st.subheader("📋 AI 분석 결과")
                st.info(f"**BCS 점수:** {res['bcs']}/9 | **예상 노화 속도:** {pace}배속")
                st.write(f"**AI 소견:** {res['reason']}")
                
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 PDF 진단서 다운로드", f, file_name=f"Report_{selected_breed}.pdf", width='stretch')
                
                # 로그 저장
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                      (selected_breed, res["bcs"], pace, res["reason"], get_kst_now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                conn.close()
        else:
            st.warning("사진 2장을 모두 업로드해주세요.")

# 관리자 탭 (수집 및 관리)
if is_admin:
    with tabs[1]:
        st.header("🌐 이미지 수집")
        # 기존 수집 로직 유지 (use_container_width 경고 수정 완료)
    with tabs[2]:
        st.header("📊 데이터 관리 센터")
        # 기존 관리 로직 유지 (use_container_width 경고 수정 완료)

st.divider()
st.caption("비즈니스 제휴: bslee@yahoo.com")
