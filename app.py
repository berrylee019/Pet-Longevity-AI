import google.generativeai as genai
from PIL import Image

# 1. Gemini 설정 (Secrets에서 키 가져오기)
try:
    GOOGLE_API_KEY = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-pro') # 최신 멀티모달 모델
except:
    st.error("Secrets에 GEMINI_API_KEY를 설정해주세요.")

# 2. 사진 분석 함수 (AI 수의사 페르소나 적용)
def analyze_pet_image(image_path):
    img = Image.open(image_path)
    
    # 털 많은 견종(말티즈/포메)까지 고려한 정교한 프롬프트
    prompt = """
    너는 20년 경력의 베테랑 수의사야. 이 리트리버 사진을 WSAVA BCS 9단계 기준으로 분석해줘.
    
    1. **품질 검사**: 사진에 강아지의 **몸 전체(갈비뼈, 허리, 복부)**가 명확히 보이니? 얼굴만 나오거나 털에 가려 체형 판단이 불가능하면 점수를 매기지 말고 'INVALID'라고 답해줘.
    2. **채점 (BCS)**: 1~9 사이의 정수로 채점해줘.
    3. **근거**: 갈비뼈의 만져짐 정도(시각적 유추), 위에서 본 허리 굴곡(모래시계 모양), 옆에서 본 복부 수축 라인을 근거로 제시해줘.
    
    결과는 반드시 JSON 형식으로만 출력해줘:
    {
        "status": "VALID" 또는 "INVALID",
        "bcs_score": 5 (VALID일 경우),
        "reason": "갈비뼈가 희미하게 보이며, 허리 라인이 선명함." (VALID일 경우)
    }
    """
    
    try:
        response = model.generate_content([prompt, img])
        # JSON 결과 파싱 (실제 코드에서는 예외처리 필요)
        import json
        result = json.loads(response.text.replace('```json', '').replace('```', ''))
        return result
    except Exception as e:
        return {"status": "ERROR", "reason": str(e)}

# 3. UI에서 분석 실행 (예시)
if st.button("수집된 데이터 AI 채점 시작"):
    sample_path = "dataset/side_view"
    files = [f for f in os.listdir(sample_path) if f.endswith(('.jpg', '.jpeg', '.png'))][:5] # 5장만 먼저 테스트
    
    for img_name in files:
        full_path = os.path.join(sample_path, img_name)
        st.image(full_path, use_column_width=True)
        
        with st.spinner('Gemini 수의사가 분석 중...'):
            analysis = analyze_pet_image(full_path)
            
        if analysis["status"] == "VALID":
            bcs = analysis["bcs_score"]
            pace = calculate_pace_of_aging(bcs) # 아까 만든 함수 활용
            st.success(f"✅ 판독 완료: BCS **{bcs}**/9 (사유: {analysis['reason']})")
            st.metric(label="현재 노화 속도", value=f"{pace}x")
        elif analysis["status"] == "INVALID":
            st.warning("⚠️ 전신 사진이 아니라 판독이 불가능합니다 (노이즈 데이터).")
        else:
            st.error(f"❌ 분석 오류: {analysis['reason']}")
