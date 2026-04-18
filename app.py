import streamlit as st
import google.generativeai as genai
import os
import sqlite3
import datetime
import re
import pandas as pd
import textwrap
from PIL import Image, ImageDraw, ImageFont
from icrawler.builtin import BingImageCrawler

# --- 1. 시스템 초기화 및 DB 설정 ---
def init_system():
    # 저장용 폴더 생성
    for path in ["dataset/multi_view", "cards", "database_images"]:
        if not os.path.exists(path):
            os.makedirs(path)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    # 분석 로그 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, side_img TEXT, top_img TEXT, 
                  bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    # 수집 이미지 관리 테이블
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, 
                  source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. 핵심 로직 함수들 ---

# 진단 카드 이미지 생성
def create_diagnosis_card(breed, bcs, pace, reason):
    try:
        bg_path = "card_bg.png"
        img = Image.open(bg_path) if os.path.exists(bg_path) else Image.new('RGB', (800, 1000), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        font_path = "NanumGothicBold.ttf"
        if not os.path.exists(font_path):
            st.error("⚠️ NanumGothicBold.ttf 파일이 필요합니다.")
            return None

        font_title = ImageFont.truetype(font_path, 40)
        font_data = ImageFont.truetype(font_path, 30)
        font_reason = ImageFont.truetype(font_path, 20)
        
        # 텍스트 배치 (디자인에 맞춰 조정)
        draw.text((320, 50), f"{breed}", font=font_title, fill=(255, 255, 255))
        draw.text((220, 480), f"{bcs}", font=ImageFont.truetype(font_path, 80), fill=(0, 0, 0))
        draw.text((610, 420), f"{pace}x", font=ImageFont.truetype(font_path, 60), fill=(200, 50, 50))
        
        # 소견 자동 줄바꿈
        lines = textwrap.wrap(reason, width=40)
        y_text = 680
        for line in lines:
            draw.text((80, y_text), line, font=font_reason, fill=(50, 50, 50))
            y_text += 35
            
        card_path = f"cards/card_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        img.save(card_path)
        return card_path
    except Exception as e:
        st.error(f"카드 생성 실패: {e}")
        return None

# 노화 속도 계산
def calculate_pace_of_aging(bcs_score, breed):
    base_pace = 1.0
    if bcs_score <= 3: pace = base_pace + (5 - bcs_score) * 0.12
    elif 4 <= bcs_score <= 5: pace = base_pace
    else: pace = base_pace + (bcs_score - 5) * 0.15
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# AI 분석
def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        prompt = f"베테랑 수의사로서 {breed_name}의 옆/위 사진을 분석해 BCS 점수(1-9)와 근거를 '점수 / 근거' 형식으로 한글로 작성해줘."
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        bcs_val = int(re.findall(r'[1-9]', res_text)[0]) if re.findall(r'[1-9]', res_text) else 5
        return {"bcs": bcs_val, "reason": res_text}
    except:
        return {"bcs": 5, "reason": "분석 실패. 표준 체형으로 가정합니다."}

# --- 3. Streamlit UI ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

# API 설정
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
tab1, tab2, tab3 = st.tabs(["🔍 정밀 분석 카드", "🌐 이미지 수집", "📊 데이터 센터"])

# [Tab 1] 분석 및 카드 발급
with tab1:
    st.header("Step 2. AI 진단서 발급")
    col1, col2 = st.columns(2)
    with col1: side_file = st.file_uploader("옆모습", type=['jpg', 'png'])
    with col2: top_file = st.file_uploader("윗모습", type=['jpg', 'png'])

    if st.button("🧠 진단 카드 생성", use_container_width=True):
        if side_file and top_file:
            t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            s_path, t_path = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_path, "wb") as f: f.write(side_file.getbuffer())
            with open(t_path, "wb") as f: f.write(top_file.getbuffer())
            
            res = analyze_pet_multi_view(s_path, t_path, selected_breed)
            pace = calculate_pace_of_aging(res["bcs"], selected_breed)
            
            conn = sqlite3.connect('pet_analysis.db')
            conn.cursor().execute("INSERT INTO analysis_logs (breed, side_img, top_img, bcs, pace, reason, date) VALUES (?,?,?,?,?,?,?)",
                                 (selected_breed, s_path, t_path, res["bcs"], pace, res["reason"], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
            conn.commit()
            conn.close()

            card = create_diagnosis_card(selected_breed, res["bcs"], pace, res["reason"])
            if card:
                st.image(card, width=600)
                with open(card, "rb") as f:
                    st.download_button("📥 카드 저장", f, file_name=f"report_{selected_breed}.png")

# [Tab 2] 이미지 수집 (검색어 필터 강화)
with tab2:
    st.header("Step 1. 견종 데이터 수집")
    # 타 동물 제외 필터 추가
    refined_query = st.text_input("검색 쿼리 최적화", f"{selected_breed} dog real photo body condition -chart -diagram -infographic -poster -text")
    if st.button("🚀 데이터 수집 및 DB 등록"):
        save_dir = f"dataset/multi_view/{selected_breed}"
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        with st.spinner("이미지 수집 중..."):
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
        st.success("데이터베이스 동기화 완료!")

# [Tab 3] 데이터 센터 (DB 정화 코드 포함)
with tab3:
    st.header("📊 데이터 관리 및 정화")
    log_tab, coll_tab = st.tabs(["📋 분석 로그", "🖼️ 수집 라이브러리"])
    
    with log_tab:
        conn = sqlite3.connect('pet_analysis.db')
        df_l = pd.read_sql_query("SELECT * FROM analysis_logs", conn)
        st.dataframe(df_l, use_container_width=True)
        conn.close()

    with coll_tab:
        conn = sqlite3.connect('pet_analysis.db')
        df_c = pd.read_sql_query("SELECT * FROM collected_images", conn)
        
        if st.checkbox("🖼️ 이미지 라이브러리 크게 보기", value=True):
                # 한 줄에 2개씩 크게 보여줘서 글씨 유무를 확실히 판단하게 함
                img_cols = st.columns(2) 
                for i, row in df_c.iterrows():
                    with img_cols[i % 2]:
                        if os.path.exists(row['img_path']):
                            st.image(row['img_path'], use_container_width=True)
                            st.caption(f"ID: {row['id']} | {row['breed']}")
            


# 하단 푸터
st.divider()
st.caption("본 플랫폼은 AI 기반 펫 테크 비즈니스 모델 검증용입니다. 제휴 문의: bslee@yahoo.com")
