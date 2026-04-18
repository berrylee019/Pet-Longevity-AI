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

# --- 2. PDF 생성 로직 (상단 로고 및 레이아웃 최적화) ---
class PetReportPDF(FPDF):
    def header(self):
        header_img = "card_bg1.png"
        if os.path.exists(header_img):
            self.image(header_img, x=10, y=10, w=190)
            self.ln(40)
        else:
            self.set_font('Helvetica', 'B', 20)
            self.cell(0, 20, 'Pet Health Report', ln=True, align='C')
            self.ln(10)

def create_pdf_report(breed, bcs, pace, reason):
    try:
        pdf = PetReportPDF()
        font_path = "NanumGothicBold.ttf"
        if not os.path.exists(font_path): return None
        pdf.add_font('NanumGothic', 'B', font_path, uni=True)
        pdf.add_page()
        
        pdf.set_font('NanumGothic', 'B', 22)
        pdf.cell(0, 15, 'Anti-Aging & Body Condition Report', ln=True, align='C')
        pdf.ln(10)
        
        table_width = 160
        start_x = (210 - table_width) / 2
        data = [['진단 대상 견종', f'{breed}'], ['체형 점수 (BCS)', f'{bcs} / 9 점'], 
                ['예상 노화 속도', f'{pace} 배속'], ['진단 일시', datetime.datetime.now().strftime('%Y-%m-%d %H:%M')]]
        
        for row in data:
            pdf.set_x(start_x)
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(60, 12, row[0], border=1, fill=True)
            pdf.cell(100, 12, row[1], border=1, ln=True, align='C')
            
        pdf.ln(20)
        pdf.set_x(start_x)
        pdf.set_font('NanumGothic', 'B', 16)
        pdf.set_text_color(0, 51, 102)
        pdf.cell(0, 10, '[ AI 수의사 종합 소견 ]', ln=True)
        pdf.ln(5)
        
        clean_reason = reason.replace('**', '').replace('*', '').strip()
        pdf.set_font('NanumGothic', 'B', 12)
        pdf.set_text_color(60, 60, 60)
        pdf.set_x(start_x)
        pdf.multi_cell(table_width, 10, clean_reason, border=0, align='L')
        
        pdf.set_y(265)
        pdf.set_font('NanumGothic', 'B', 10)
        pdf.set_text_color(160, 160, 160)
        pdf.cell(0, 10, '제작: [견종별 노화 정밀 분석기] | 다이어트 체험단 모집 중', align='C')
        
        report_path = f"reports/Report_{breed}_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.pdf"
        pdf.output(report_path)
        return report_path
    except: return None

# --- 3. AI 분석 및 계산 로직 ---
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        prompt = f"수의사로서 {breed_name} 사진 분석. '점수 / 소견' 형식(특수문자 제외)으로 작성."
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        if '/' in res_text:
            parts = res_text.split('/')
            bcs_val = int(re.search(r'\d', parts[0]).group()) if re.search(r'\d', parts[0]) else 5
            clean_reason = parts[1].strip()
        else:
            bcs_val = 5
            clean_reason = res_text
            
        return {"bcs": bcs_val, "reason": clean_reason}
    except: return {"bcs": 5, "reason": "AI 분석 중 오류가 발생했습니다."}

def calculate_pace_of_aging(bcs, breed):
    pace = 1.0 + (abs(5-bcs) * 0.15)
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 4. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')

st.sidebar.title("🐾 시스템 설정")
selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
st.sidebar.divider()
admin_pass = st.sidebar.text_input("관리자 비번", type="password")
is_admin = (admin_pass == "2004")

tab_list = ["🔍 정밀 분석 및 PDF"]
if is_admin: tab_list += ["🌐 멀티 소스 수집", "📊 데이터 센터"]
tabs = st.tabs(tab_list)

# [Tab 0] 분석 및 발급
with tabs[0]:
    st.header("🐶 AI 수의사 노화 정밀 진단")
    c1, c2 = st.columns(2)
    with c1: side_f = st.file_uploader("옆모습 업로드", type=['jpg', 'jpeg', 'png'], key="side_f")
    with c2: top_f = st.file_uploader("윗모습 업로드", type=['jpg', 'jpeg', 'png'], key="top_f")
    
    if st.button("🧠 분석 실행 및 리포트 생성", use_container_width=True):
        if side_f and top_f:
            t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            s_p, t_p = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_p, "wb") as f: f.write(side_f.getbuffer())
            with open(t_p, "wb") as f: f.write(top_f.getbuffer())
            
            with st.spinner("AI 분석 중..."):
                res = analyze_pet_multi_view(s_p, t_p, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                st.info(f"**AI 소견:** {res['reason']}")
                pdf_p = create_pdf_report(selected_breed, res["bcs"], pace, res["reason"])
                if pdf_p:
                    with open(pdf_p, "rb") as f:
                        st.download_button("📄 PDF 진단서 다운로드", f, file_name=f"Report_{selected_breed}.pdf", use_container_width=True)
        else:
            st.warning("사진 2장을 모두 업로드해주세요.")

# [Tab 1] 멀티 소스 수집 (Flickr 대신 Baidu 적용)
if is_admin:
    with tabs[1]:
        st.header("🌐 멀티 소스 데이터 수집 (Admin)")
        query = st.text_input("검색 쿼리", f"{selected_breed} dog body condition score -text")
        sources = st.multiselect("수집 출처 선택", ["Google", "Bing", "Baidu"], default=["Google", "Bing", "Baidu"])
        max_imgs = st.slider("소스당 수집 개수", 5, 50, 10)
        
        if st.button("🚀 통합 수집 시작"):
            save_base = f"dataset/multi_view/{selected_breed}"
            conn = sqlite3.connect('pet_analysis.db')
            
            for src in sources:
                src_dir = os.path.join(save_base, src.lower())
                if not os.path.exists(src_dir): os.makedirs(src_dir)
                
                with st.spinner(f"{src} 소스에서 데이터를 수집하는 중..."):
                    try:
                        if src == "Google":
                            crawler = GoogleImageCrawler(storage={'root_dir': src_dir})
                        elif src == "Bing":
                            crawler = BingImageCrawler(storage={'root_dir': src_dir})
                        elif src == "Baidu":
                            crawler = BaiduImageCrawler(storage={'root_dir': src_dir})
                        
                        crawler.crawl(keyword=query, max_num=max_imgs)
                        
                        # 파일 DB 등록
                        for f_name in os.listdir(src_dir):
                            f_path = os.path.join(src_dir, f_name)
                            conn.cursor().execute("INSERT INTO collected_images (breed, img_path, source, collect_date) VALUES (?,?,?,?)",
                                                 (selected_breed, f_path, src, datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))
                    except Exception as e:
                        st.error(f"{src} 수집 실패: {e}")
            
            conn.commit()
            conn.close()
            st.success("통합 수집이 완료되었습니다!")

    # [Tab 2] 데이터 센터
    with tabs[2]:
        st.header("📊 데이터 관리 센터 (Admin Only)")
        l_tab, c_tab = st.tabs(["📋 분석 로그", "🖼️ 수집 이미지 정화"])
        with l_tab:
            conn = sqlite3.connect('pet_analysis.db')
            st.dataframe(pd.read_sql_query("SELECT * FROM analysis_logs ORDER BY id DESC", conn), use_container_width=True)
            conn.close()
        with c_tab:
            conn = sqlite3.connect('pet_analysis.db')
            df_c = pd.read_sql_query("SELECT * FROM collected_images ORDER BY id DESC", conn)
            if not df_c.empty:
                to_del = st.multiselect("삭제할 이미지 ID 선택", df_c['id'].tolist())
                if st.button("🗑️ 선택 삭제 실행", type="primary"):
                    cur = conn.cursor()
                    for d_id in to_del:
                        cur.execute("SELECT img_path FROM collected_images WHERE id = ?", (d_id,))
                        p = cur.fetchone()[0]
                        if os.path.exists(p): os.remove(p)
                        cur.execute("DELETE FROM collected_images WHERE id = ?", (d_id,))
                    conn.commit()
                    st.rerun()
                st.divider()
                cols = st.columns(4)
                for i, row in df_c.iterrows():
                    with cols[i % 4]:
                        if os.path.exists(row['img_path']):
                            st.image(row['img_path'], use_container_width=True)
                            st.caption(f"ID:{row['id']} [{row['source']}]")
            conn.close()

st.divider()
st.caption("비즈니스 제휴 및 체험단 문의: bslee@yahoo.com")
