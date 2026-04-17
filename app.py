import streamlit as st
import os
from icrawler.builtin import BingImageCrawler

# --- 1. 노화 속도 계산 로직 ---
def calculate_pace_of_aging(bcs_score, is_large_breed=True):
    """
    영상 이론 기반: 노화 속도(Pace of Aging) 계산 함수
    """
    base_pace = 1.0
    
    # 비만도(BCS 1~9)에 따른 가중치
    if bcs_score <= 3:
        pace = base_pace + (5 - bcs_score) * 0.1  # 저체중/근감소 위험
    elif 4 <= bcs_score <= 5:
        pace = base_pace  # 이상적
    else:
        # 과체중(6~9): 7점이면 1.25x, 9점이면 1.5x
        pace = base_pace + (bcs_score - 5) * 0.125
        
    # 대형견 가중치 (리트리버 등)
    if is_large_breed:
        pace *= 1.15 
        
    return round(pace, 2)

# --- 2. 이미지 수집 함수 ---
def download_images(keyword, count, save_dir):
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    crawler = BingImageCrawler(storage={'root_dir': save_dir})
    crawler.crawl(keyword=keyword, max_num=count)
    return save_dir

# --- 3. Streamlit UI 구성 ---
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

st.title("🐾 Pet Longevity: Pace of Aging 분석기")
st.write("반려견의 체형을 분석하여 노화 속도를 측정하고 수명을 관리합니다.")

# 사이드바: 데이터 수집 도구
with st.sidebar:
    st.header("Step 1. 데이터 수집 (리트리버)")
    target_view = st.selectbox("수집할 각도", ["side_view", "top_view"])
    download_count = st.slider("수집 개수", 10, 100, 20)
    
    if st.button("이미지 수집 시작"):
        query = f"Golden Retriever standing {target_view.replace('_', ' ')}"
        save_path = f"dataset/{target_view}"
        with st.spinner('이미지를 수집 중입니다...'):
            download_images(query, download_count, save_path)
        st.success(f"{download_count}장의 이미지가 {save_path}에 저장되었습니다!")

# 메인 화면: 노화 속도 계산기 테스트
st.header("Step 2. 노화 속도 로직 테스트")
col1, col2 = st.columns(2)

with col1:
    st.subheader("현재 상태 입력")
    dog_name = st.text_input("아이 이름", "인절미")
    bcs_input = st.slider("BCS 점수 (1:매우 마름 ~ 9:비만)", 1, 9, 5)
    is_large = st.checkbox("대형견인가요?", value=True)

with col2:
    st.subheader("분석 결과")
    pace = calculate_pace_of_aging(bcs_input, is_large)
    
    # 결과 시각화
    st.metric(label="현재 노화 속도", value=f"{pace}x", delta=f"{round(pace-1.0, 2)}x", delta_color="inverse")
    
    if pace > 1.1:
        st.warning(f"⚠️ {dog_name}(은)는 현재 표준보다 {int((pace-1)*100)}% 빠르게 늙고 있습니다!")
        st.info("💡 처방: 일일 급여량을 10% 줄이고 산책 시간을 늘려 '소식 루틴'을 시작하세요.")
    else:
        st.success(f"✨ {dog_name}(은)는 아주 건강한 속도로 나이 들고 있습니다!")

st.divider()
st.caption("본 서비스는 후성 유전학 기반의 노화 속도 개념을 반려견 체형 분석에 적용한 MVP 모델입니다.")

# 수집 버튼 아래쪽이나 메인 화면 적당한 곳에 추가
st.divider()
st.subheader("현재 수집된 데이터 현황")

paths = ["dataset/side_view", "dataset/top_view"]
for p in paths:
    if os.path.exists(p):
        files = os.listdir(p)
        st.write(f"📂 {p}: 현재 **{len(files)}**장의 사진이 모였습니다.")
    else:
        st.write(f"📂 {p}: 아직 폴더가 생성되지 않았습니다.")
