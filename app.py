import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import random
from PIL import Image
from icrawler.builtin import BingImageCrawler
from fpdf import FPDF

# --- 1. 시스템 초기화 및 DB 설정 ---
def init_system():
    # 저장용 폴더 생성
    for path in ["dataset/multi_view", "cards", "database_images"]:
        if not os.path.exists(path):
            os.makedirs(path)
    
    # SQLite DB 초기화
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    # 1. 분석 결과 로그 테이블 (기존)
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  breed TEXT, side_img TEXT, top_img TEXT, 
                  bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    # 2. 수집된 원천 이미지 관리 테이블 (신규!)
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, 
                  source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. PDF 생성 클래스 ---
class PetReport(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.cell(0, 10, 'AI Pet Health & Longevity Report', 0, 1, 'C')
        self.ln(10)

def create_pdf(breed, bcs, pace, reason):
    # FPDF 대신 한글 지원을 위해 인코딩 설정을 넣습니다.
    pdf = PetReport()
    pdf.add_page()
    
    # [중요] 한글 폰트가 프로젝트 폴더에 있다면 아래 주석을 풀고 사용하세요.
    # 만약 폰트 파일이 없다면 임시로 영어로 출력되게 아래에 안전장치를 걸어둡니다.
    # pdf.add_font('Nanum', '', 'NanumGothic.ttf', unicode=True)
    # pdf.set_font('Nanum', size=12)

    # 폰트가 없는 환경에서 에러를 방지하기 위해 '유니코드' 지원 설정을 강제합니다.
    pdf.set_font("Helvetica", size=12) # 기본 폰트
    
    # 한글 에러를 피하기 위해 영어로 변환하거나 인코딩 에러를 무시하는 처리
    safe_breed = breed.encode('ascii', 'ignore').decode('ascii') if not breed.isascii() else breed
    
    pdf.cell(0, 10, f"Analysis Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}", ln=1)
    pdf.cell(0, 10, f"Target Breed: {breed}", ln=1) # 한글 지원 폰트 설정 전까진 영문 권장
    pdf.cell(0, 10, f"BCS Score: {bcs} / 9", ln=1)
    pdf.cell(0, 10, f"Predicted Aging Pace: {pace}x", ln=1)
    pdf.ln(10)
    
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 10, "AI Veterinarian Opinion:", ln=1)
    pdf.set_font("Helvetica", size=11)
    
    # 한글이 포함된 reason을 출력할 때 에러가 안 나게 처리
    # (진짜 한글 PDF를 뽑으려면 나눔폰트.ttf 파일을 업로드하고 add_font를 써야 합니다!)
    pdf.multi_cell(0, 10, reason.encode('utf-8').decode('latin-1', 'replace')) 
    
    report_path = f"reports/report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf.output(report_path)
    return report_path

# --- 3. 비즈니스 로직 함수 ---
def calculate_pace_of_aging(bcs_score, breed):
    base_pace = 1.0
    if bcs_score <= 3:
        pace = base_pace + (5 - bcs_score) * 0.12
    elif 4 <= bcs_score <= 5:
        pace = base_pace
    else:
        pace = base_pace + (bcs_score - 5) * 0.15
    
    # 리트리버는 대형견 가산치, 나머지는 소형견 기준으로 유지
    if breed == "리트리버":
        pace *= 1.15
    return round(pace, 2)

def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        
        prompt = f"""
        너는 베테랑 수의사야. 사진 속 견종은 '{breed_name}'이야.
        제공된 두 장의 사진(옆모습, 윗모습)을 교차 분석해서 BCS 점수를 매겨줘.
        
        1. 옆모습: 복부 턱(Abdominal tuck)과 갈비뼈 부위 확인.
        2. 윗모습: 허리 라인(Waist line)의 굴곡 확인.
        
        '{breed_name}'의 견종 특성(털의 양, 체형 특징)을 고려해서 최종 BCS(1~9) 점수와 근거를 말해줘.
        결과는 반드시 '점수 / 근거' 형식으로 대답해줘.
        """
        
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        numbers = re.findall(r'[1-9]', res_text)
        bcs_val = int(numbers[0]) if numbers else 5
        return {"bcs": bcs_val, "reason": res_text}
    except Exception as e:
        return {"bcs": 5, "reason": f"분석 중 오류 발생: {str(e)}"}

# --- 4. Streamlit UI 설정 ---
st.set_page_config(page_title="Pet Longevity AI - Multi-View", layout="wide")

# Gemini 설정
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash') # 모델명 최신화
    else:
        st.warning("⚠️ Streamlit Secrets에 GEMINI_API_KEY를 설정해주세요.")
except Exception as e:
    st.error(f"설정 에러: {e}")

# 사이드바 설정
st.sidebar.title("🐾 AI Pet Health")
selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
st.sidebar.divider()
st.sidebar.info("데이터베이스에 분석 이력이 자동으로 저장됩니다.")

# 메인 화면
st.title(f"🐾 {selected_breed} 노화 정밀 분석기")
tab1, tab2, tab3 = st.tabs(["🔍 정밀 분석", "🌐 이미지 수집", "📊 데이터 히스토리"])

with tab1:
    st.header("Step 2. AI 정밀 분석")
    st.info(f"현재 선택된 견종: **{selected_breed}**")
    
    up_col1, up_col2 = st.columns(2)
    with up_col1:
        side_file = st.file_uploader("📸 옆모습 사진 (Side)", type=['jpg', 'jpeg', 'png'], key="side_up")
    with up_col2:
        top_file = st.file_uploader("📸 윗모습 사진 (Top)", type=['jpg', 'jpeg', 'png'], key="top_up")

    if st.button("🧠 AI 수의사 정밀 진단 시작", use_container_width=True):
        if side_file and top_file:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            side_path = f"database_images/{timestamp}_side.png"
            top_path = f"database_images/{timestamp}_top.png"
            
            with open(side_path, "wb") as f: f.write(side_file.getbuffer())
            with open(top_path, "wb") as f: f.write(top_file.getbuffer())
            
            with st.spinner(f"{selected_breed} 데이터를 대조 분석 중..."):
                res = analyze_pet_multi_view(side_path, top_path, selected_breed)
                
            bcs = res["bcs"]
            pace = calculate_pace_of_aging(bcs, selected_breed)
            
            # DB 저장 로직
            conn = sqlite3.connect('pet_analysis.db')
            c = conn.cursor()
            c.execute("INSERT INTO analysis_logs (breed, side_img, top_img, bcs, pace, reason, date) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (selected_breed, side_path, top_path, bcs, pace, res["reason"], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            conn.close()

            # 결과 대시보드
            st.divider()
            c1, c2 = st.columns(2)
            with c1: st.metric(label="최종 판독 BCS", value=f"{bcs} / 9")
            with c2: st.metric(label="예상 노화 속도", value=f"{pace} 배속")
                
            st.success("✨ 분석 완료 및 DB 저장이 완료되었습니다.")
            
            with st.expander("📄 AI 수의사 정밀 판독서 보기", expanded=True):
                st.write(res['reason'])
            
            # PDF 다운로드
            pdf_path = create_pdf(selected_breed, bcs, pace, res["reason"])
            with open(pdf_path, "rb") as f:
                st.download_button("📥 PDF 진단서 다운로드", f, file_name=f"{selected_breed}_진단리포트_{timestamp}.pdf")
        else:
            st.error("두 장의 사진을 모두 업로드해주세요.")

with tab2:
    st.header("Step 1. 테스트 이미지 수집")
    search_query = st.text_input("검색어", f"{selected_breed} body condition score side top view")
    if st.button("🚀 이미지 수집 시작"):
        save_dir = f"dataset/multi_view/{selected_breed}"
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        with st.spinner(f"Bing에서 {selected_breed} 이미지를 수집 중입니다..."):     
            crawler = BingImageCrawler(storage={'root_dir': save_dir})
            crawler.crawl(keyword=search_query, max_num=10)

        # --- DB에 수집 정보 기록 (추가된 로직) ---
        conn = sqlite3.connect('pet_analysis.db')
        c = conn.cursor()
        
        collected_files = os.listdir(save_dir)
        new_records = 0
        for file_name in collected_files:
            file_path = os.path.join(save_dir, file_name)
            # 중복 체크 (동일 경로가 없을 때만 저장)
            c.execute("SELECT id FROM collected_images WHERE img_path = ?", (file_path,))
            if not c.fetchone():
                c.execute("INSERT INTO collected_images (breed, img_path, source, collect_date) VALUES (?, ?, ?, ?)",
                          (selected_breed, file_path, "Bing Crawler", datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                new_records += 1
        
        conn.commit()
        conn.close()
        st.success(f"✅ {selected_breed} 이미지 {new_records}건이 새롭게 DB에 등록되었습니다!")

with tab3:
    hist_tab1, hist_tab2 = st.tabs(["📝 분석 이력", "🖼️ 수집 데이터 라이브러리"])
    
    with hist_tab1:
        # 기존 분석 이력 조회 코드 (df = pd.read_sql_query("SELECT * FROM analysis_logs..."))
        pass
        
    with hist_tab2:
        st.subheader("🌐 수집된 이미지 데이터셋")
        conn = sqlite3.connect('pet_analysis.db')
        df_collected = pd.read_sql_query("SELECT * FROM collected_images ORDER BY id DESC", conn)
        conn.close()
        
        if not df_collected.empty:
            # 견종별로 필터링해서 볼 수 있게 필터 추가
            filter_breed = st.selectbox("견종 필터", ["전체"] + list(df_collected['breed'].unique()))
            display_df = df_collected if filter_breed == "전체" else df_collected[df_collected['breed'] == filter_breed]
            
            st.dataframe(display_df, use_container_width=True)
            
            # 필요할 때 이미지 불러와서 확인하기 (갤러리 형태)
            if st.checkbox("이미지 미리보기 활성화"):
                cols = st.columns(3)
                for idx, row in display_df.head(12).iterrows(): # 너무 많으면 느려지니 12개만
                    with cols[idx % 3]:
                        if os.path.exists(row['img_path']):
                            st.image(row['img_path'], caption=f"{row['breed']} ({row['id']})")
        else:
            st.write("아직 수집된 데이터가 없습니다.")

# 하단 푸터
st.divider()
st.caption("본 플랫폼은 AI 기반 펫 테크 비즈니스 모델 검증용입니다. 제휴 문의: bslee@yahoo.com")
