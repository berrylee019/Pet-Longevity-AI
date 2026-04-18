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
    for path in ["dataset/multi_view", "cards", "database_images"]:
        if not os.path.exists(path):
            os.makedirs(path)
    
    conn = sqlite3.connect('pet_analysis.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analysis_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, side_img TEXT, top_img TEXT, 
                  bcs INTEGER, pace REAL, reason TEXT, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS collected_images
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, img_path TEXT, 
                  source TEXT, collect_date TEXT)''')
    conn.commit()
    conn.close()

init_system()

# --- 2. 핵심 로직 함수 (디자인 및 요약 최적화 교체본) ---

def analyze_pet_multi_view(side_img_path, top_img_path, breed_name):
    """AI에게 핵심 요약 및 인사말 생략을 지시하는 최적화 함수"""
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        
        # 디자인을 위해 한글 150자 이내 요약을 강제합니다.
        prompt = f"""
        너는 베테랑 수의사야. {breed_name}의 옆모습과 윗모습 사진을 분석해줘.
        1. BCS 점수 (1~9)를 결정해.
        2. 소견을 작성할 때 '안녕하세요' 같은 인사말은 생략하고, 
           갈비뼈 상태, 허리 라인, 복부 굴곡에 대한 핵심 진단만 한글 150자 이내로 짧고 명확하게 작성해줘.
        결과 형식: 점수 / 소견
        """
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        # 점수와 소견 분리 추출
        bcs_val = int(re.findall(r'[1-9]', res_text)[0]) if re.findall(r'[1-9]', res_text) else 5
        clean_reason = res_text.split('/')[-1].strip() if '/' in res_text else res_text
        
        return {"bcs": bcs_val, "reason": clean_reason}
    except Exception as e:
        return {"bcs": 5, "reason": f"분석 중 오류 발생: {str(e)}"}

def create_diagnosis_card(breed, bcs, pace, reason):
    """가변 폰트 및 줄바꿈 최적화가 적용된 카드 생성 함수"""
    try:
        bg_path = "card_bg.png"
        img = Image.open(bg_path) if os.path.exists(bg_path) else Image.new('RGB', (1000, 1300), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        font_path = "NanumGothicBold.ttf"
        if not os.path.exists(font_path):
            st.error("⚠️ NanumGothicBold.ttf 파일이 필요합니다.")
            return None

        # 1. 상단 견종 텍스트
        font_breed = ImageFont.truetype(font_path, 45)
        draw.text((420, 45), breed, font=font_breed, fill=(255, 255, 255)) 

        # 2. 중간 지표 (BCS, 노화 속도)
        font_score = ImageFont.truetype(font_path, 100)
        font_pace = ImageFont.truetype(font_path, 70)
        draw.text((215, 470), str(bcs), font=font_score, fill=(30, 30, 30))
        draw.text((615, 415), f"{pace}x", font=font_pace, fill=(210, 40, 40))

        # 3. 하단 종합 소견 (글자 수에 따른 폰트 사이즈 가변 적용)
        text_len = len(reason)
        if text_len > 120: font_size = 18
        elif text_len > 80: font_size = 22
        else: font_size = 25
        
        font_reason = ImageFont.truetype(font_path, font_size)
        
        # 줄바꿈 폭 최적화 (여백 확보)
        wrap_width = 40 if font_size > 20 else 48
        lines = textwrap.wrap(reason, width=wrap_width)
        
        y_text = 680 # 소견 시작 좌표
        for line in lines:
            if y_text > 950: break # 카드 하단 범위를 넘어가면 중단
            draw.text((80, y_text), line, font=font_reason, fill=(60, 60, 60))
            y_text += (font_size + 12) # 행간 간격 적용
            
        card_path = f"cards/card_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        img.save(card_path)
        return card_path
    except Exception as e:
        st.error(f"카드 생성 실패: {e}")
        return None

# --- 기타 비즈니스 로직 ---
def calculate_pace_of_aging(bcs_score, breed):
    base_pace = 1.0
    if bcs_score <= 3: pace = base_pace + (5 - bcs_score) * 0.12
    elif 4 <= bcs_score <= 5: pace = base_pace
    else: pace = base_pace + (bcs_score - 5) * 0.15
    if breed == "리트리버": pace *= 1.15
    return round(pace, 2)

# --- 3. UI 구성 (Streamlit) ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-flash')

selected_breed = st.sidebar.selectbox("대상 견종 선택", ["리트리버", "말티즈", "푸들", "포메라니안"])
tab1, tab2, tab3 = st.tabs(["🔍 정밀 분석 카드", "🌐 이미지 수집", "📊 데이터 센터"])

# [Tab 1] 분석 및 발급
with tab1:
    st.header("Step 2. AI 정밀 진단 카드 발급")
    col1, col2 = st.columns(2)
    with col1: side_file = st.file_uploader("📸 옆모습 사진 (Side)", type=['jpg', 'jpeg', 'png'])
    with col2: top_file = st.file_uploader("📸 윗모습 사진 (Top)", type=['jpg', 'jpeg', 'png'])

    if st.button("🧠 AI 수의사 정밀 진단 시작", use_container_width=True):
        if side_file and top_file:
            t_stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            s_path, t_path = f"database_images/{t_stamp}_s.png", f"database_images/{t_stamp}_t.png"
            with open(s_path, "wb") as f: f.write(side_file.getbuffer())
            with open(t_path, "wb") as f: f.write(top_file.getbuffer())
            
            with st.spinner("AI가 체형을 대조 분석 중입니다..."):
                res = analyze_pet_multi_view(s_path, t_path, selected_breed)
                pace = calculate_pace_of_aging(res["bcs"], selected_breed)
                
                # DB 저장
                conn = sqlite3.connect('pet_analysis.db')
                conn.cursor().execute("INSERT INTO analysis_logs (breed, side_img, top_img, bcs, pace, reason, date) VALUES (?,?,?,?,?,?,?)",
                                     (selected_breed, s_path, t_path, res["bcs"], pace, res["reason"], datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                conn.commit()
                conn.close()

                # 카드 이미지 생성
                card = create_diagnosis_card(selected_breed, res["bcs"], pace, res["reason"])
                if card:
                    st.image(card, width=700)
                    with open(card, "rb") as f:
                        st.download_button("📥 진단 카드 다운로드 (SNS 공유용)", f, file_name=f"Report_{selected_breed}_{t_stamp}.png")
        else:
            st.warning("옆모습과 윗모습 사진을 모두 업로드해주세요.")

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
st.caption("비즈니스 제휴 및 체험단 문의: [bslee@yahoo.com]")
