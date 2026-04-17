import streamlit as st
import google.generativeai as genai
import os
import json
import random
from PIL import Image
from icrawler.builtin import BingImageCrawler

# --- 1. 기본 설정 및 보안 ---
st.set_page_config(page_title="Pet Longevity AI", layout="centered")

# Gemini 설정
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-1.5-pro')
    else:
        st.warning("⚠️ Streamlit Secrets에 GEMINI_API_KEY를 설정해주세요.")
except Exception as e:
    st.error(f"설정 에러: {e}")

# --- 2. 로직 함수들 ---
def calculate_pace_of_aging(bcs_score, is_large_breed=True):
    base_pace = 1.0
    if bcs_score <= 3: pace = base_pace + (5 - bcs_score) * 0.1
    elif 4 <= bcs_score <= 5: pace = base_pace
    else: pace = base_pace + (bcs_score - 5) * 0.125
    if is_large_breed: pace *= 1.15 
    return round(pace, 2)

def analyze_pet_image(image_path):
    try:
        img = Image.open(image_path)
        prompt = """
        너는 수의사야. 이 리트리버 사진을 보고 BCS(1-9)를 판독해줘.
        전신이 아니면 {"status": "INVALID"}를, 
        전신이면 {"status": "VALID", "bcs_score": 점수, "reason": "이유"}를 JSON으로 답해줘.
        """
        response = model.generate_content([prompt, img])
        # JSON 파싱 안전장치
        text = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(text)
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

# --- 3. 메인 화면 UI ---
st.title("🐾 리트리버 노화 속도 분석 시스템")
st.info("데이터 수집부터 AI 판독까지 한 화면에서 진행합니다.")

# --- STEP 1: 데이터 수집 ---
st.header("Step 1. 리트리버 이미지 수집")
col1, col2 = st.columns([2, 1])
with col1:
    search_query = st.text_input("검색어", "Golden Retriever standing side view")
with col2:
    count = st.number_input("수집 개수", min_value=5, max_value=50, value=10)

if st.button("🚀 이미지 수집 시작", use_container_width=True):
    save_dir = "dataset/side_view"
    if not os.path.exists(save_dir): os.makedirs(save_dir)
    
    with st.spinner("이미지를 긁어모으는 중..."):
        crawler = BingImageCrawler(storage={'root_dir': save_dir})
        crawler.crawl(keyword=search_query, max_num=count)
    st.success(f"✅ {count}장의 이미지 수집 완료!")

st.divider()

# --- STEP 2: 수집 현황 및 샘플 확인 ---
st.header("Step 2. 수집 데이터 확인")
sample_path = "dataset/side_view"

if os.path.exists(sample_path) and len(os.listdir(sample_path)) > 0:
    files = [f for f in os.listdir(sample_path) if f.endswith(('.jpg', '.jpeg', '.png'))]
    st.write(f"현재 폴더에 **{len(files)}**장의 사진이 있습니다.")
    
    if st.button("🖼️ 랜덤 샘플 3장 보기"):
        samples = random.sample(files, min(3, len(files)))
        cols = st.columns(3)
        for i, img_name in enumerate(samples):
            cols[i].image(os.path.join(sample_path, img_name), use_column_width=True)
else:
    st.warning("아직 수집된 데이터가 없습니다. Step 1을 먼저 진행해주세요.")

st.divider()

# --- STEP 3: AI 판독 ---
st.header("Step 3. Gemini AI 수의사 채점")
if st.button("🧠 AI 노화 속도 분석 시작", use_container_width=True):
    if not os.path.exists(sample_path) or not os.listdir(sample_path):
        st.error("분석할 이미지가 없습니다!")
    else:
        files = [f for f in os.listdir(sample_path) if f.endswith(('.jpg', '.jpeg', '.png'))]
        test_files = files[:3] # 우선 3장만 테스트
        
        for img_name in test_files:
            full_path = os.path.join(sample_path, img_name)
            st.image(full_path, width=300)
            
            with st.spinner("AI가 체형을 분석 중입니다..."):
                res = analyze_pet_image(full_path)
            
            if res.get("status") == "VALID":
                bcs = res["bcs_score"]
                pace = calculate_pace_of_aging(bcs)
                st.write(f"**결과:** BCS {bcs}/9 | **노화 속도:** {pace}배속")
                st.caption(f"**이유:** {res['reason']}")
            else:
                st.warning("이 사진은 전신이 아니거나 분석이 불가능합니다.")
            st.divider()
