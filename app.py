import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
from PIL import Image
from fpdf import FPDF
from icrawler.builtin import BingImageCrawler

# --- 1. 시스템 초기화 ---
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

# --- 2. PDF 클래스 커스텀 (상단 로고 및 레이아웃 최적화) ---
class PetReportPDF(FPDF):
    def header(self):
        # 형님이 주신 상단 이미지 로고 삽입
        header_img = "card_bg1.png"
        if os.path.exists(header_img):
            # 이미지 너비를 190mm로 설정하여 중앙 배치 느낌을 줌
            self.image(header_img, x=10, y=10, w=190)
            self.ln(40) # 이미지 높이만큼 충분히 내려오기
        else:
            self.set_font('NanumGothic', 'B', 25)
            self.set_text_color(0, 51, 102)
            self.cell(0, 20, '강아지 노화 정밀 진단서', ln=True, align='C')
            self.ln(10)

def create_pdf_report(breed, bcs, pace, reason):
    pdf = PetReportPDF()
    font_path = "NanumGothicBold.ttf"
    
    if not os.path.exists(font_path):
        st.error("⚠️ NanumGothicBold.ttf 파일이 필요합니다.")
        return None
        
    # 스타일 'B'로 폰트 등록
    pdf.add_font('NanumGothic', 'B', font_path, uni=True)
    pdf.add_page()
    
    # 1. 메인 타이틀 (중앙 배치)
    pdf.set_font('NanumGothic', 'B', 22)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 15, 'Anti-Aging & Body Condition Report', ln=True, align='C')
    pdf.ln(10)
    
    # 2. 진단 요약 표 (중앙 정렬 레이아웃)
    pdf.set_font('NanumGothic', 'B', 14)
    table_width = 160
    start_x = (210 - table_width) / 2 # A4 폭 210mm 기준 중앙 정렬
    
    data = [
        ['진단 대상 견종', f'{breed}'],
        ['체형 점수 (BCS)', f'{bcs} / 9 점'],
        ['예상 노화 속도', f'{pace} 배속'],
        ['진단 일시', datetime.datetime.now().strftime('%Y-%m-%d %H:%M')]
    ]
    
    for row in data:
        pdf.set_x(start_x)
        pdf.set_fill_color(245, 245, 245) # 연한 회색 배경
        pdf.cell(60, 12, row[0], border=1, fill=True)
        pdf.cell(100, 12, row[1], border=1, ln=True, align='C')
    
    pdf.ln(20)
    
    # 3. AI 수의사 종합 소견 섹션
    pdf.set_x(start_x)
    pdf.set_font('NanumGothic', 'B', 16)
    pdf.set_text_color(0, 51, 102) # 진한 파란색 제목
    pdf.cell(0, 10, '[ AI 수의사 종합 소견 ]', ln=True)
    pdf.ln(5)
    
    # 텍스트 정제: **, * 등 마크다운 기호 제거
    clean_reason = reason.replace('**', '').replace('*', '').strip()
    
    pdf.set_font('NanumGothic', 'B', 12)
    pdf.set_text_color(60, 60, 60)
    pdf.set_x(start_x)
    # multi_cell로 자동 줄바꿈 및 깔끔한 출력
    pdf.multi_cell(table_width, 10, clean_reason, border=0, align='L')
    
    # 4. 하단 카피라이트 (중앙 고정)
    pdf.set_y(265)
    pdf.set_font('NanumGothic', 'B', 10)
    pdf.set_text_color(160, 160, 160)
    pdf.cell(0, 10, '제작: [견종별 노화 정밀 분석기] | 다이어트 체험단 모집 중', align='C')
    
    report_path = f"reports/Report_{breed}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    pdf.output(report_path)
    return report_path

# --- 3. AI 분석 로직 ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        prompt = f"""
        너는 베테랑 수의사야. {breed_name}의 옆/위 사진을 분석해줘.
        1. BCS 점수(1-9)를 결정해.
        2. 소견 작성 시 **, * 같은 특수기호는 절대 쓰지 말고 깔끔한 문장으로만 작성해.
        3. 결과는 반드시 '점수 / 소견' 형식으로 한글로 작성해.
        """
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        bcs_val = int(re.findall(r'[1-9]', res_text)[0]) if re.findall(r'[1-9]', res_text) else 5
        clean_reason = res_text.split('/')[-1].strip() if '/' in res_text else res_text
        return {"bcs": bcs_val, "reason": clean_reason}
    except:
        return {"bcs": 5, "reason": "이미지 분석 중 오류가 발생했습니다. 사진 품질을 확인해주세요."}

def calculate_pace_of_aging(bcs, breed):
    base_pace = 1.0
    if bcs <= 3: pace = base_pace + (5 - bcs) * 0.12
    elif 4 <= bcs <= 5: pace = base_pace
    else: pace = base_pace + (bcs - 5) * 0.15
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
tab1, tab2, tab3 = st.tabs(["🔍 정밀 분석 및 PDF 발급", "🌐 이미지 수집", "📊 데이터 센터"])

with tab1:
    st.header("🐶 AI 수의사 노화 정밀 진단")
    c1, c2 = st.columns(2)
    with c1: side_file = st.file_uploader("옆모습 사진 업로드", type=['jpg', 'jpeg', 'png'])
    with c2: top_file = st.file_uploader("윗모습 사진 업로드", type=['jpg', 'jpeg', 'png'])

    if st.button("🧠 정밀 진단 및 리포트 생성", use_container_width=True):
        if side_file and top_file:
            t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_file.getbuffer())
            with open(t_p, "wb") as f: f.write(top_file.getbuffer())
            
            with st.spinner("AI가 체형 데이터를 분석 중입니다..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                # 화면 결과 표시
                st.subheader("📋 실시간 진단 요약")
                m1, m2, m3 = st.columns(3)
                m1.metric("견종", selected_breed)
                m2.metric("BCS 점수", f"{res['bcs']} / 9")
                m3.metric("노화 속도", f"{pace}x")
                st.info(f"**AI 종합 소견:** {res['reason']}")
                
                # DB 저장
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                     (selected_breed, res["bcs"], pace, res["reason"], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

                # PDF 생성
                pdf_path = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                if pdf_path:
                    with open(pdf_path, "rb") as f:
                        st.download_button("📄 정밀 진단서 PDF 다운로드 (SNS 공유용)", f, 
                                         file_name=f"Health_Report_{selected_breed}.pdf", use_container_width=True)
        else:
            st.warning("분석을 위해 사진 2장을 모두 업로드해주세요.")

# --- Tab 2: 이미지 수집 ---
with tab2:
    st.header("🌐 데이터 수집 (Bing Crawler)")
    refined_query = st.text_input("검색 최적화 쿼리", f"{selected_breed} dog real photo body condition -chart -text -poster")
    if st.button("🚀 이미지 수집 시작"):
        save_dir = f"dataset/multi_view/{selected_breed}"
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        with st.spinner("이미지 수집 중..."):
            crawler = BingImageCrawler(storage={'root_dir': save_dir})
            crawler.crawl(keyword=refined_query, max_num=10)
        
        conn = sqlite3.connect('pet_analysis.db')
        c = conn.cursor()
        for f_name in os.listdir(save_dir):
            f_path = os.path.join(save_dir, f_name)
            c.execute("INSERT INTO collected_images (breed, img_path, source, collect_date) VALUES (?,?,?,?)",
                      (selected_breed, f_path, "Bing", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        st.success("데이터 수집 및 DB 등록 완료!")

# --- Tab 3: 데이터 센터 ---
with tab3:
    st.header("📊 데이터 관리 센터")
    l_tab, c_tab = st.tabs(["📋 분석 로그", "🖼️ 수집 이미지"])
    with l_tab:
        conn = sqlite3.connect('pet_analysis.db')
        df_l = pd.read_sql_query("SELECT * FROM analysis_logs ORDER BY id DESC", conn)
        st.dataframe(df_l, use_container_width=True)
        conn.close()
    with c_tab:
        conn = sqlite3.connect('pet_analysis.db')
        df_c = pd.read_sql_query("SELECT * FROM collected_images ORDER BY id DESC", conn)
        if not df_c.empty:
            st.subheader("🧹 오염 데이터 정화")
            to_del = st.multiselect("삭제할 ID 선택", df_c['id'].tolist())
            if st.button("🗑️ 선택 삭제"):
                cur = conn.cursor()
                for d_id in to_del:
                    cur.execute("SELECT img_path FROM collected_images WHERE id = ?", (d_id,))
                    p = cur.fetchone()[0]
                    if os.path.exists(p): os.remove(p)
                    cur.execute("DELETE FROM collected_images WHERE id = ?", (d_id,))
                conn.commit()
                st.rerun()
            st.dataframe(df_c, use_container_width=True)
        conn.close()
st.divider()
st.caption("비즈니스 제휴 및 체험단 문의: bslee@yahoo.com")
