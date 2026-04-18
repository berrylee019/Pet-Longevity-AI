import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
from fpdf import FPDF
from PIL import Image
# ... (기존 import 생략) ...

# --- 1. DB 초기화 함수 ---
def init_db():
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    # 이미지 경로, 견종, BCS 점수, 소견, 날짜 저장
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  breed TEXT, side_img TEXT, top_img TEXT, 
                  bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- 2. PDF 생성 함수 ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Pet Health & Longevity Report', 0, 1, 'C')

def create_pdf(breed, bcs, pace, reason):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Date: {datetime.datetime.now().strftime('%Y-%m-%d')}", ln=1)
    pdf.cell(200, 10, txt=f"Breed: {breed}", ln=1)
    pdf.cell(200, 10, txt=f"BCS Score: {bcs}/9", ln=1)
    pdf.cell(200, 10, txt=f"Aging Pace: {pace}x", ln=1)
    pdf.multi_cell(0, 10, txt=f"AI Veterinarian Opinion: \n{reason}")
    pdf.output("report.pdf")
    return "report.pdf"

# --- 3. UI 및 메인 로직 ---
st.title("🐾 4대천왕 견종별 노화 정밀 분석기")

# 견종 선택 (4대장)
breed = st.selectbox("견종을 선택해주세요", ["리트리버", "말티즈", "푸들", "포메라니안"])

# ... (Step 1 수집 로직은 기존과 동일하되 경로에 breed 추가 가능) ...

st.header("🔍 정밀 분석 및 DB 저장")
up_col1, up_col2 = st.columns(2)
with up_col1:
    side_file = st.file_uploader("📸 옆모습", type=['jpg', 'jpeg', 'png'])
with up_col2:
    top_file = st.file_uploader("📸 윗모습", type=['jpg', 'jpeg', 'png'])

if st.button("🧠 AI 정밀 진단 및 데이터 저장", use_container_width=True):
    if side_file and top_file:
        # 1. 파일 저장 및 경로 확보
        side_path = f"dataset/save_{datetime.datetime.now().timestamp()}_side.png"
        top_path = f"dataset/save_{datetime.datetime.now().timestamp()}_top.png"
        with open(side_path, "wb") as f: f.write(side_file.getbuffer())
        with open(top_path, "wb") as f: f.write(top_file.getbuffer())
        
        # 2. AI 분석 (견종 정보 포함 프롬프트)
        with st.spinner(f"{breed}의 특성을 고려하여 분석 중..."):
            # 기존 analyze_pet_multi_view 함수에 breed 매개변수 추가하여 호출
            res = analyze_pet_multi_view(side_path, top_path, breed) 
            
        bcs = res["bcs"]
        pace = calculate_pace_of_aging(bcs, is_large_breed=(breed=="리트리버"))
        
        # 3. DB에 데이터 쌓기
        conn = sqlite3.connect('pet_analysis.db')
        c = conn.cursor()
        c.execute("INSERT INTO analysis_logs (breed, side_img, top_img, bcs, pace, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                  (breed, side_path, top_path, bcs, pace, res["reason"], str(datetime.datetime.now())))
        conn.commit()
        conn.close()
        
        # 4. 결과 출력
        st.success(f"✅ {breed} 분석 완료 및 DB 저장 성공!")
        st.metric("노화 속도", f"{pace}배속")
        
        # 5. PDF 다운로드 버튼
        pdf_file = create_pdf(breed, bcs, pace, res["reason"])
        with open(pdf_file, "rb") as f:
            st.download_button("📥 PDF 정밀 진단서 다운로드", f, file_name=f"{breed}_진단서.pdf")
