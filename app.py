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
        if not os.path.exists(path): os.makedirs(path)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. PDF 생성 함수 (이미지 좌표 문제 근본 해결) ---
class PetReportPDF(FPDF):
    def header(self):
        self.set_font('NanumGothic', 'B', 20)
        self.set_text_color(0, 51, 102)
        self.cell(0, 15, '강아지 노화 정밀 진단서', ln=True, align='C')
        self.ln(5)

def create_pdf_report(breed, bcs, pace, reason):
    pdf = PetReportPDF()
    
    # 1. 폰트 등록을 가장 먼저 합니다! (add_page보다 먼저)
    # 스타일 'B'(Bold)로 쓸 수 있도록 스타일을 명시해줍니다.
    font_path = "NanumGothicBold.ttf"
    if not os.path.exists(font_path):
        st.error(f"⚠️ {font_path} 파일이 없습니다. 경로를 확인해주세요.")
        return None
        
    # 'NanumGothic'이라는 이름으로 'B'(Bold) 스타일을 등록
    pdf.add_font('NanumGothic', 'B', font_path, uni=True)
    
    # 2. 이제 페이지를 추가합니다. (이때 자동으로 header()가 호출됩니다)
    pdf.add_page()
    
    # 3. 본문 작성 시작
    pdf.set_draw_color(0, 51, 102)
    pdf.set_line_width(1)
    pdf.rect(10, 10, 190, 277)
    
    # 본문용 폰트 설정 (위에서 'B'로 등록했으니 'B'를 사용)
    pdf.set_font('NanumGothic', 'B', 14)
    pdf.set_text_color(50, 50, 50)
    
    data = [
        ['진단 대상', breed],
        ['체형 점수 (BCS)', f'{bcs} / 9 점'],
        ['예상 노화 속도', f'{pace} 배속'],
        ['진단 일시', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')]
    ]
    
    pdf.ln(10)
    for row in data:
        pdf.cell(50, 12, row[0], border=1)
        pdf.cell(130, 12, row[1], border=1, ln=True)
    
    pdf.ln(10)
    pdf.set_font('NanumGothic', 'B', 16)
    pdf.cell(0, 10, '[ AI 수의사 종합 소견 ]', ln=True)
    
    pdf.set_font('NanumGothic', 'B', 12)
    pdf.multi_cell(0, 10, reason, border=0)
    
    pdf.ln(20)
    pdf.set_font('NanumGothic', 'B', 10)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, '제작: [견종별 노화 정밀 분석기] | 본 진단은 AI 분석 결과로 참고용입니다.', align='C')
    
    report_path = f"reports/Report_{breed}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    pdf.output(report_path)
    return report_path

# --- 3. AI 분석 로직 ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        prompt = f"수의사로서 {breed_name} 사진 분석. 결과는 '점수 / 소견' 형식으로 한글 200자 내외 작성."
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        bcs_val = int(re.findall(r'[1-9]', res_text)[0]) if re.findall(r'[1-9]', res_text) else 5
        clean_reason = res_text.split('/')[-1].strip() if '/' in res_text else res_text
        return {"bcs": bcs_val, "reason": clean_reason}
    except:
        return {"bcs": 5, "reason": "분석 실패. 사진을 확인해 주세요."}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

selected_breed = st.sidebar.selectbox("견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
tab1, tab2, tab3 = st.tabs(["🔍 정밀 분석", "🌐 데이터 수집", "📊 데이터 센터"])

with tab1:
    st.header("🐶 AI 수의사 노화 정밀 분석")
    c1, c2 = st.columns(2)
    with c1: side_file = st.file_uploader("옆모습 업로드", type=['jpg','png'])
    with c2: top_file = st.file_uploader("윗모습 업로드", type=['jpg','png'])

    if st.button("🧠 정밀 진단 시작", use_container_width=True):
        if side_file and top_file:
            # 사진 저장
            t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_file.getbuffer())
            with open(t_p, "wb") as f: f.write(top_file.getbuffer())
            
            with st.spinner("AI 분석 중..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                # 결과 표시 (표 및 지표)
                st.subheader("📋 분석 결과")
                m1, m2, m3 = st.columns(3)
                m1.metric("대상 견종", selected_breed)
                m2.metric("체형 점수 (BCS)", f"{res['bcs']} / 9")
                m3.metric("예상 노화 속도", f"{pace}x")
                
                st.info(f"**AI 수의사 종합 소견:**\n\n{res['reason']}")
                
                # DB 기록
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, bcs, pace, reason, date) VALUES (?,?,?,?,?)",
                                     (selected_breed, res["bcs"], pace, res["reason"], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

                # PDF 생성 및 다운로드 버튼
                pdf_path = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                with open(pdf_path, "rb") as f:
                    st.download_button("📄 정밀 진단서 PDF 다운로드 (SNS 공유용)", f, 
                                     file_name=f"Report_{selected_breed}.pdf", use_container_width=True)
        else:
            st.warning("사진 2장을 모두 올려주세요.")

# [Tab 2] 이미지 수집
with tab2:
    st.header("Step 1. 견종 데이터 수집 (Filter 적용)")
    refined_query = st.text_input("검색 쿼리 최적화", f"{selected_breed} dog real photo body condition -chart -diagram -infographic -poster -text")
    if st.button("🚀 데이터 수집 시작"):
        save_dir = f"dataset/multi_view/{selected_breed}"
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        with st.spinner("Bing에서 이미지 낚시 중..."):
            crawler = BingImageCrawler(storage={'root_dir': save_dir})
            crawler.crawl(keyword=refined_query, max_num=10)
        
        conn = sqlite3.connect('pet_analysis.db')
        c = conn.cursor()
        for f_name in os.listdir(save_dir):
            f_path = os.path.join(save_dir, f_name)
            c.execute("SELECT id FROM collected_images WHERE img_path = ?", (f_path,))
            if not c.fetchone():
                c.execute("INSERT INTO collected_images (breed, img_path, source, collect_date) VALUES (?,?,?,?)",
                          (selected_breed, f_path, "Bing", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()
        conn.close()
        st.success("수집된 데이터가 DB에 등록되었습니다.")

# [Tab 3] 데이터 센터 및 정화
with tab3:
    st.header("📊 데이터 관리 센터")
    l_tab, c_tab = st.tabs(["📋 분석 로그", "🖼️ 수집 라이브러리"])
    
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
            to_del = st.multiselect("삭제할 데이터 ID 선택", df_c['id'].tolist())
            if st.button("🗑️ 선택 항목 영구 삭제", type="primary"):
                cur = conn.cursor()
                for d_id in to_del:
                    cur.execute("SELECT img_path FROM collected_images WHERE id = ?", (d_id,))
                    p = cur.fetchone()[0]
                    if os.path.exists(p): os.remove(p)
                    cur.execute("DELETE FROM collected_images WHERE id = ?", (d_id,))
                conn.commit()
                st.rerun()
            st.divider()
            st.dataframe(df_c, use_container_width=True)
        else:
            st.info("수집된 데이터가 없습니다.")
        conn.close()

st.divider()
st.caption("비즈니스 제휴 및 체험단 문의: bslee@yahoo.com")
