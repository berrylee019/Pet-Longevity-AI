import streamlit as st
import google.generativeai as genai
import os
import json
import random
import re
from PIL import Image
from icrawler.builtin import BingImageCrawler

# --- 1. 기본 설정 ---
st.set_page_config(page_title="Pet Longevity AI", layout="centered")

# Gemini 설정 (Secrets 사용)
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flesh')
    else:
        st.warning("⚠️ Secrets에 GEMINI_API_KEY를 넣어주세요.")
except Exception as e:
    st.error(f"설정 에러: {e}")

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
        prompt = "수의사로서 이 사진 속 강아지의 BCS(1~9) 점수를 숫자 하나만 먼저 말하고, 그 뒤에 이유를 써줘."
        response = model.generate_content([prompt, img])
        res_text = response.text.strip()
        
        numbers = re.findall(r'[1-9]', res_text)
        bcs_val = int(numbers[0]) if numbers else 5
        
        return {"bcs": bcs_val, "reason": res_text}
    except Exception as e:
        # 이 부분이 핵심입니다! "일시적 오류" 대신 진짜 에러를 보여줍니다.
        return {"bcs": 5, "reason": f"🚨 실제 에러 발생: {str(e)}"}

# --- 2. 메인 화면 UI ---
st.title("🐾 리트리버 노화 속도 분석 시스템")

# --- Step 1: 수집 ---
st.header("Step 1. 이미지 수집")
if st.button("🚀 이미지 수집 시작 (10장)", key="collect_btn"):
    save_dir = "dataset/side_view"
    if not os.path.exists(save_dir): os.makedirs(save_dir)
    with st.spinner("이미지를 가져오는 중..."):
        crawler = BingImageCrawler(storage={'root_dir': save_dir})
        crawler.crawl(keyword="Golden Retriever side view body", max_num=10)
    st.success("✅ 수집 완료!")

st.divider()

# --- Step 2 & 3: 확인 및 분석 (통합) ---
st.header("Step 2. AI 판독 및 노화 분석")
sample_path = "dataset/side_view"

if st.button("🧠 현재 폴더 사진으로 분석 시작", key="final_analysis_btn"):
    if not os.path.exists(sample_path) or not os.listdir(sample_path):
        st.error("먼저 이미지를 수집해주세요!")
    else:
        all_files = [f for f in os.listdir(sample_path) if f.endswith(('.jpg', '.jpeg', '.png'))]
        # [중요] 샘플로 보여주는 사진과 분석하는 사진을 '동일하게' 맞춤
        target_files = random.sample(all_files, min(3, len(all_files)))
        
        for img_name in target_files:
            full_path = os.path.join(sample_path, img_name)
            
            # 1. 이미지 출력
            st.image(full_path, width=400)
            
            # 2. 분석 진행
            with st.spinner("AI 수의사가 체형을 분석 중..."):
                res = analyze_pet_image(full_path)
            
            # 3. 결과 출력 (이제 무조건 결과가 나옵니다)
            bcs = res["bcs"]
            pace = calculate_pace_of_aging(bcs)
            
            st.subheader(f"✅ 분석 결과: BCS {bcs}/9")
            st.metric("현재 노화 속도", f"{pace}배속")
            with st.expander("수의사 소견 보기"):
                st.write(res["reason"])
            st.divider()
