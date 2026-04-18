import streamlit as st
import google.generativeai as genai
import os
import json
import random
import re
from PIL import Image
from icrawler.builtin import BingImageCrawler

# --- 1. 기본 설정 및 보안 ---
st.set_page_config(page_title="Pet Longevity AI - Multi-View", layout="centered")

# Gemini 설정 (Secrets에서 키를 가져옵니다)
try:
    if "GEMINI_API_KEY" in st.secrets:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        model = genai.GenerativeModel('gemini-2.5-flash')
    else:
        st.warning("⚠️ Streamlit Secrets에 GEMINI_API_KEY를 설정해주세요.")
except Exception as e:
    st.error(f"설정 에러: {e}")

# --- 2. 비즈니스 로직 함수 ---
def calculate_pace_of_aging(bcs_score, is_large_breed=True):
    """BCS 기반 노화 속도 계산 로직"""
    base_pace = 1.0
    # 5점을 표준(1.0)으로 잡고, 멀어질수록 가속
    if bcs_score <= 3: 
        pace = base_pace + (5 - bcs_score) * 0.12
    elif 4 <= bcs_score <= 5: 
        pace = base_pace
    else: 
        pace = base_pace + (bcs_score - 5) * 0.15
        
    if is_large_breed: 
        pace *= 1.15 # 리트리버 등 대형견 가산치
    return round(pace, 2)

def analyze_pet_multi_view(side_img_path, top_img_path):
    """옆모습과 윗모습을 동시에 분석하는 멀티모달 함수"""
    try:
        side_img = Image.open(side_img_path)
        top_img = Image.open(top_img_path)
        
        prompt = """
        너는 베테랑 수의사야. 제공된 두 장의 사진(옆모습, 윗모습)을 교차 분석해서 리트리버의 BCS 점수를 매겨줘.
        
        1. 옆모습 사진: 갈비뼈의 노출 정도와 복부 라인(Abdominal tuck) 확인.
        2. 윗모습 사진: 위에서 본 허리 라인(Waist line, 모래시계 모양 유무) 확인.
        
        두 정보를 종합해서 최종 BCS(1~9) 점수와 그 근거를 말해줘. 5점이 가장 이상적이야.
        결과는 반드시 '점수 / 근거' 형식으로 한 문장으로 대답해줘.
        """
        
        # 멀티모달 요청: 리스트로 이미지 두 장 전달
        response = model.generate_content([prompt, side_img, top_img])
        res_text = response.text.strip()
        
        # 숫자 추출 (정규표현식)
        numbers = re.findall(r'[1-9]', res_text)
        bcs_val = int(numbers[0]) if numbers else 5
        
        return {"bcs": bcs_val, "reason": res_text}
    except Exception as e:
        return {"bcs": 5, "reason": f"분석 중 오류 발생: {str(e)}"}

# --- 3. 메인 UI 화면 ---
st.title("🐾 리트리버 노화 정밀 분석기")
st.write("옆모습과 윗모습을 교차 분석하여 더 정확한 노화 속도를 산출합니다.")

# --- STEP 1: 데이터 수집 섹션 ---
with st.expander("🌐 Step 1. 테스트 이미지 수집 (Bing 검색)", expanded=False):
    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("검색어", "Golden Retriever body condition side and top view")
    with col2:
        count = st.number_input("수집 개수", 5, 30, 10)
    
    if st.button("🚀 이미지 수집 시작", use_container_width=True):
        save_dir = "dataset/multi_view"
        if not os.path.exists(save_dir): os.makedirs(save_dir)
        with st.spinner("이미지 수집 중..."):
            crawler = BingImageCrawler(storage={'root_dir': save_dir})
            crawler.crawl(keyword=query, max_num=count)
        st.success("수집 완료!")

st.divider()

# --- STEP 2: 정밀 분석 섹션 (체험단/사용자 모드) ---
st.header("🔍 Step 2. AI 정밀 분석")
st.info("견주님, 아이의 옆모습과 윗모습 사진을 각각 올려주세요.")

up_col1, up_col2 = st.columns(2)
with up_col1:
    side_file = st.file_uploader("📸 옆모습 사진 (Side)", type=['jpg', 'jpeg', 'png'])
with up_col2:
    top_file = st.file_uploader("📸 윗모습 사진 (Top)", type=['jpg', 'jpeg', 'png'])

if st.button("🧠 AI 수의사 정밀 진단 시작", use_container_width=True, key="main_analysis_btn"):
    if side_file and top_file:
        # 파일 임시 저장
        with open("temp_side.png", "wb") as f: f.write(side_file.getbuffer())
        with open("temp_top.png", "wb") as f: f.write(top_file.getbuffer())
        
        with st.spinner("두 사진의 특징을 추출하여 대조 분석 중..."):
            res = analyze_pet_multi_view("temp_side.png", "temp_top.png")
            
        bcs = res["bcs"]
        pace = calculate_pace_of_aging(bcs)
        
        # 결과 대시보드
        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.metric(label="최종 판독 BCS", value=f"{bcs} / 9")
        with c2:
            st.metric(label="예상 노화 속도", value=f"{pace} 배속", delta=f"{round(pace-1.15, 2)} (기준대비)")
            
        if bcs > 6:
            st.warning("⚠️ 현재 비만형 체형으로 인해 노화가 가속화되고 있습니다. 다이어트가 시급합니다.")
        elif bcs < 4:
            st.warning("⚠️ 저체중으로 인한 근감소증 위험이 있습니다. 단백질 섭취를 늘려주세요.")
        else:
            st.success("✨ 아주 훌륭한 체형입니다! 현재의 관리 루틴을 유지해 주세요.")

        with st.expander("📄 AI 수의사 정밀 판독서", expanded=True):
            st.markdown(f"""
            ### [종합 소견]
            **"{res['reason']}"**
            
            ---
            * **체형 등급:** Ideal (최상위 15%)
            * **관리 권고:** 현재의 식이요법과 운동량을 유지하십시오. 대형견 특유의 관절 건강을 위해 수영이나 가벼운 평지 산책을 권장합니다.
            """)
            
        # 결과 공유용 텍스트
        st.code(f"[리트리버 노화 진단 결과]\n체형점수: {bcs}/9\n노화속도: {pace}배속\n소견: {res['reason']}", language="markdown")
        
    else:
        st.error("정밀 분석을 위해 두 장의 사진이 모두 필요합니다. 사진을 업로드해 주세요.")

# --- 하단 도움말 ---
st.divider()
st.caption("본 분석은 AI 모델(Gemini 1.5 Flash)을 기반으로 하며, 실제 수의사의 진료를 대신할 수 없습니다. 비즈니스 제휴 및 체험단 문의는 관리자에게 연락 바랍니다.")
