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
def init_system():
    # 폴더 생성 시 에러 방지 (exist_ok=True 추가)
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

# --- 2. PDF 생성 로직 (폰트 에러 방지 및 한글 최적화) ---
class PetReportPDF(FPDF):
    def header(self):
        header_img = "card_bg1.png"
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
        pdf.set_auto_page_break(auto=False, margin=0)
        
        # 폰트 경로 확인 및 추가 (uni=True 필수)
        font_path = "NanumGothicBold.ttf"
        if not os.path.exists(font_path): 
            st.error("폰트 파일을 찾을 수 없습니다. (NanumGothicBold.ttf)")
            return None
            
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
        print(f"PDF 생성 에러: {e}")
        return None

# --- 3. AI 분석 및 노화 속도 계산 (한국어 소견 강제) ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        
        # --- 프롬프트: 특수문자 사용 금지 및 구조 단순화 지시 ---
        prompt = f"""
        당신은 20년 경력의 베테랑 수의사입니다. 제공된 {breed_name}의 사진을 정밀 분석하세요.
        
        [지시 사항]
        1. 반드시 한국어로 상세히 작성할 것.
        2. BCS 점수를 1~9 사이 숫자로 판정할 것.
        3. 소견 내용에 '**' 또는 '*' 같은 마크다운 기호를 절대 사용하지 마세요. (텍스트로만 작성)
        4. 소견서는 체형 분석, 건강 위험, 식단/운동 제안을 포함해 500자 이상 아주 길게 작성하세요.
        5. 반드시 아래 형식을 정확히 지키세요:
        
        결과시작
        점수: [숫자]
        소견: [상세 내용]
        결과종료
        """
        
        # 출력 길이를 최대치로 설정 (2048 토큰)
        response = model.generate_content(
            [prompt, side_img, top_img],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2048,
                temperature=0.7,
            )
        )
        res_text = response.text.strip()
        
        # --- 개선된 파싱 로직 (문자열 슬라이싱 방식) ---
        bcs_val = 5
        clean_reason = "분석 결과를 정리 중입니다."
        
        try:
            # 점수 추출
            if "점수:" in res_text:
                score_part = res_text.split("점수:")[1].split("\n")[0]
                bcs_match = re.search(r'\d', score_part)
                if bcs_match: bcs_val = int(bcs_match.group())
            
            # 소견 추출 (키워드 기반 슬라이싱으로 끊김 방지)
            if "소견:" in res_text:
                # "소견:" 이후부터 "결과종료" 이전까지 모든 텍스트를 가져옴
                reason_start = res_text.find("소견:") + 3
                reason_end = res_text.find("결과종료")
                if reason_end == -1: # 만약 결과종료가 누락되었다면 끝까지 가져옴
                    clean_reason = res_text[reason_start:].strip()
                else:
                    clean_reason = res_text[reason_start:reason_end].strip()
            else:
                clean_reason = res_text # 형식이 틀려도 전체 내용이라도 보여줌
                
        except Exception as parse_err:
            print(f"Parsing Error: {parse_err}")
            clean_reason = res_text # 파싱 실패 시 원문 그대로 노출

        return {"bcs": bcs_val, "reason": clean_reason}
        
    except Exception as e:
        print(f"AI ERROR: {str(e)}")
        return {"bcs": 5, "reason": f"분석 중 오류가 발생했습니다: {str(e)[:100]}"}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    # 안정적인 1.5-flash 권장
    model = genai.GenerativeModel('gemini-2.5-flash')
else:
    st.error("Secret 에 API Key가 설정되지 않았습니다.")

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
    
    with st.expander("💡 이용 방법 및 진단 요청 안내", expanded=True):
        st.markdown("""
        1. **견종 선택**: 사이드바에서 견종 선택
        2. **이미지 업로드**: 옆모습/윗모습 사진 업로드
        3. **분석 실행**: 버튼 클릭 후 AI 소견 확인 및 PDF 다운로드
        """)
    
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
            
            with st.spinner("AI 수의사가 분석 중입니다..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                st.info(f"**AI 소견:** {res['reason']}")
                
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

# 관리자 기능 (생략 가능)
if is_admin:
    with tabs[1]:
        st.header("🌐 이미지 수집")
    with tabs[2]:
        st.header("📊 데이터 센터")
        conn = sqlite3.connect('pet_analysis.db')
        st.dataframe(pd.read_sql_query("SELECT * FROM analysis_logs ORDER BY id DESC", conn), width='stretch')
        conn.close()

st.divider()
st.caption("비즈니스 제휴 문의: bslee@yahoo.com")
