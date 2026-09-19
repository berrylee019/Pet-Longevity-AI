import streamlit as st
import os

try:
    # 로컬 개발 환경: .env 파일이 있으면 읽어온다.
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Streamlit Cloud 등 배포 환경에는 python-dotenv가 없을 수 있는데,
    # 없어도 앱이 죽지 않고 계속 진행되도록 한다 (Secrets로 대체됨).
    pass

# Streamlit Cloud의 "Secrets" 설정(.streamlit/secrets.toml 또는 앱 대시보드의
# Secrets 입력창)에 넣은 값은 st.secrets로만 들어오고 os.environ에는 자동으로
# 안 실립니다. payments/lemonsqueezy_checkout.py 등 일부 모듈이 os.environ을
# 직접 읽으므로, 여기서 필요한 값들을 os.environ에도 복사해둡니다.
for _key in ["LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_STORE_ID", "CHECKOUT_REDIRECT_URL", "PAYMENT_SERVER_URL"]:
    if _key in st.secrets and _key not in os.environ:
        os.environ[_key] = str(st.secrets[_key])

from google import genai
import sqlite3
import datetime
import re
import pandas as pd
import time
import hashlib
import requests
from PIL import Image
from fpdf import FPDF

from payments.lemonsqueezy_checkout import create_checkout_url

# payment-verify-server(main.py)의 배포 주소.
# 기존 pet-longevity-toss(인앱토스)가 쓰던 것과 동일한 서버를 가리켜야 함.
PAYMENT_SERVER_URL = os.environ["PAYMENT_SERVER_URL"].rstrip("/")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# [CRITICAL] set_page_config MUST be the first Streamlit command
st.set_page_config(page_title="Pet Longevity AI", layout="wide")

# --- 0. Monetization config ---
DIAGNOSIS_COST = 1  # credits consumed per diagnosis run

# variant_id는 Lemon Squeezy 대시보드 > Products 에서 각 플랜의 실제 값으로 교체하세요.
CREDIT_PLANS = {
    "10 credits — $4.99": {"variant_id": "VARIANT_ID_1", "credits": 10},
    "50 credits — $19.99": {"variant_id": "VARIANT_ID_2", "credits": 50},
}

# --- 1. System Initialization ---
def init_db():
    # NOTE: Streamlit Cloud / Render 같은 호스팅은 재배포·재시작 시
    # 로컬 디스크가 초기화될 수 있습니다. 장기적으로는 SQLite/이미지 파일을
    # 영구 스토리지(예: 별도 DB, S3 등)로 옮기는 것을 고려하세요.
    for folder in ["dataset/multi_view", "reports", "database_images"]:
        os.makedirs(folder, exist_ok=True)

    conn = sqlite3.connect('pet_health.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS health_logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, breed TEXT, bcs INTEGER, pace REAL, opinion TEXT, date TEXT)''')
    conn.commit()
    conn.close()


@st.cache_resource
def get_ai_client():
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
        return genai.Client(api_key=api_key)
    except Exception as e:
        st.error(f"Failed to load AI Client: {e}")
        return None


init_db()
client = get_ai_client()

# --- 1b. Identity via email (free-credit farming 방지) ---
# 이전 버전은 URL의 랜덤 UUID를 deviceId로 썼는데, 사용자가 URL의 uid만
# 지우고 새로고침하면 새 UUID가 생성돼 무료 크레딧을 무한정 받을 수 있는
# 허점이 있었습니다. 이를 막기 위해 "이메일 해시값"을 deviceId로 사용합니다.
# 같은 이메일이면 어떤 브라우저/URL로 와도 같은 크레딧 잔액을 보게 되고,
# 부수적으로 이메일 리스트도 확보됩니다(추후 마케팅에 활용 가능).
def email_to_device_id(email: str) -> str:
    normalized = email.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def get_or_create_uid():
    """세션에 식별된 사용자가 없으면 None을 반환 (이메일 게이트에서 처리)."""
    qp = st.query_params
    uid = qp.get("uid")
    if uid:
        return uid
    return st.session_state.get("uid")


def get_credits(uid: str) -> int:
    try:
        resp = requests.get(f"{PAYMENT_SERVER_URL}/credits/{uid}", timeout=30)
        resp.raise_for_status()
        return int(resp.json().get("balance", 0))
    except Exception as e:
        st.warning(f"Credit system unavailable: {e}")
        return 0


def deduct_credit(uid: str) -> int:
    try:
        resp = requests.post(f"{PAYMENT_SERVER_URL}/consume", json={"deviceId": uid}, timeout=30)
        resp.raise_for_status()
        return int(resp.json().get("balance", 0))
    except Exception as e:
        st.warning(f"Failed to update credits: {e}")
        return 0


uid = get_or_create_uid()

if not uid:
    # 아직 이메일로 식별되지 않은 방문자 -> 이메일 게이트 화면만 보여주고 여기서 멈춘다.
    st.title("🐾 Pet Longevity AI (Global)")
    st.caption("A fun, AI-powered pet wellness companion — for general awareness only, not a substitute for veterinary care.")
    st.subheader("Start with 3 free credits")
    st.write("Enter your email to unlock 3 free AI wellness checks for your pet.")

    with st.form("email_gate", clear_on_submit=False):
        email_input = st.text_input("Email address")
        submitted = st.form_submit_button("Get 3 Free Credits & Continue")

    if submitted:
        if EMAIL_RE.match(email_input or ""):
            new_uid = email_to_device_id(email_input)
            st.session_state["uid"] = new_uid
            st.session_state["user_email"] = email_input.strip().lower()
            st.query_params["uid"] = new_uid
            st.rerun()
        else:
            st.error("Please enter a valid email address.")

    st.stop()

user_email = st.session_state.get("user_email")

# --- 2. PDF Generation ---
class PetPDF(FPDF):
    def header(self):
        if os.path.exists("card_bg1_edited.png"):
            self.image("card_bg1_edited.png", x=10, y=10, w=190)
            self.ln(35)
        else:
            self.set_font('Helvetica', 'B', 20)
            self.cell(0, 15, 'Pet Wellness Report', ln=True, align='C')
            self.ln(5)


def create_report(breed, bcs, pace, opinion):
    pdf = PetPDF()
    pdf.add_page()
    pdf.set_font('Helvetica', 'B', 12)

    pdf.set_fill_color(240, 240, 240)
    pdf.cell(50, 10, 'Target Breed', border=1, fill=True)
    pdf.cell(140, 10, f'{breed}', border=1, ln=True)
    pdf.cell(50, 10, 'Body Score (BCS)', border=1, fill=True)
    pdf.cell(140, 10, f'{bcs} / 9', border=1, ln=True)
    pdf.cell(50, 10, 'Aging Pace', border=1, fill=True)
    pdf.cell(140, 10, f'{pace}x speed', border=1, ln=True)

    pdf.ln(10)
    pdf.set_font('Helvetica', 'B', 14)
    pdf.cell(0, 10, '[ AI Wellness Insight ]', ln=True)
    pdf.set_font('Helvetica', '', 10)
    pdf.multi_cell(0, 6, opinion.replace('*', ''))

    pdf.ln(4)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.multi_cell(0, 5, "This report is an AI-generated wellness estimate for informational and entertainment "
                          "purposes only. It is not a medical diagnosis and is not a substitute for professional "
                          "veterinary advice, examination, or treatment.")

    pdf.set_y(265)
    pdf.set_font('Helvetica', 'I', 8)
    pdf.cell(0, 10, "Inquiry: bslee@yahoo.com", align='C')

    report_name = f"reports/Report_{datetime.datetime.now().strftime('%Y%m%d%H%M')}.pdf"
    pdf.output(report_name)
    return report_name


# --- 3. AI Analysis Logic ---
def analyze_pet_vision(side_path, top_path, breed, max_retries=3):
    result = {"bcs": 5, "opinion": "Starting analysis..."}

    if client is None:
        result["opinion"] = "AI Client not initialized. Please check API Key."
        return result

    try:
        side_img = Image.open(side_path)
        top_img = Image.open(top_path)

        prompt = f"""
        You are a friendly pet wellness assistant that gives casual, informational
        body condition insights based on photos — this is NOT a medical or veterinary diagnosis.
        Look at the side and top view images of this {breed} and give an estimated
        Body Condition Score (BCS) on a scale of 1-9, purely for general wellness awareness.
        Keep the tone warm and non-clinical, and end your explanation with a short reminder
        that this is not a substitute for a real veterinary check-up.
        Format your response exactly as:
        Score: [Number]
        Opinion: [Friendly explanation in English, ending with the reminder above]
        """

        for attempt in range(max_retries):
            try:
                # NOTE: gemini-1.5-flash / gemini-1.5-pro는 2025-09-29부로
                # Google이 완전히 종료(shut down)한 모델입니다. 반드시 아래처럼
                # 현재 서비스 중인 모델로 교체하세요.
                # "-latest" 별칭(alias)은 Google이 계속 최신 모델을 가리키도록
                # 관리해주므로, 향후 모델 세대교체에 따른 breaking change를
                # 줄이는 데 도움이 됩니다.
                model_names = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-pro"]
                text = ""
                success = False

                for m_name in model_names:
                    try:
                        response = client.models.generate_content(
                            model=m_name,
                            contents=[prompt, side_img, top_img]
                        )
                        text = response.text
                        success = True
                        break
                    except Exception as inner_e:
                        if "404" in str(inner_e):
                            continue
                        else:
                            raise inner_e

                if not success:
                    raise Exception("All models failed with 404.")

                score = 5
                match = re.search(r'Score:\s*(\d)', text)
                if match:
                    score = int(match.group(1))

                opinion = text.split("Opinion:")[1].strip() if "Opinion:" in text else text

                result["bcs"] = score
                result["opinion"] = opinion
                return result

            except Exception as e:
                err_msg = str(e).upper()
                if "429" in err_msg:
                    wait_time = (attempt + 1) * 15
                    st.warning(f"Quota exceeded. Retrying in {wait_time}s... ({attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    result["opinion"] = f"AI Error: {str(e)[:100]}"
                    break

    except Exception as e:
        result["opinion"] = f"System Error: {str(e)[:100]}"

    return result


# --- 4. Main UI ---
st.title("🐾 Pet Longevity AI (Global)")
st.caption("A fun, AI-powered pet wellness companion — for general awareness only, not a substitute for veterinary care.")

with st.sidebar:
    st.header("Settings")
    breed = st.selectbox("Select Breed", ["Retriever", "Maltese", "Poodle", "Pomeranian", "King Charles Spaniel",
    "German Shepherd"])

    # 관리자 코드는 secrets.toml에 ADMIN_CODE로 저장하세요 (하드코딩 금지)
    admin_code = st.text_input("Admin Code", type="password")

    st.divider()
    st.subheader("💳 Credits")
    if user_email:
        st.caption(f"Signed in as {user_email}")
        if st.button("Use a different email"):
            st.session_state.pop("uid", None)
            st.session_state.pop("user_email", None)
            st.query_params.pop("uid", None)
            st.rerun()
    current_credits = get_credits(uid)
    st.metric("Balance", current_credits)

    with st.expander("Buy more credits"):
        plan_choice = st.selectbox("Plan", list(CREDIT_PLANS.keys()), key="plan_select")
        if st.button("Buy Now", key="buy_now_btn"):
            plan = CREDIT_PLANS[plan_choice]
            base_redirect = os.environ.get("CHECKOUT_REDIRECT_URL", "")
            # 결제 완료 후 같은 uid를 달고 이 앱으로 되돌아오도록 redirect_url에 붙여준다
            redirect_url = f"{base_redirect}?uid={uid}" if base_redirect else None
            checkout_url = create_checkout_url(
                variant_id=plan["variant_id"],
                user_id=uid,
                credits=plan["credits"],
                user_email=user_email,
                redirect_url=redirect_url,
            )
            st.link_button("Proceed to Payment →", checkout_url)
            st.caption("Complete payment, then return to this page — your credits will update automatically.")

t1, t2 = st.tabs(["Wellness Check", "Data Logs"])

with t1:
    if current_credits < DIAGNOSIS_COST:
        st.warning(f"You need at least {DIAGNOSIS_COST} credit to run a wellness check. Please buy credits from the sidebar.")

    col1, col2 = st.columns(2)
    with col1:
        side_f = st.file_uploader("Side View Image", type=['jpg', 'jpeg', 'png'])
    with col2:
        top_f = st.file_uploader("Top View Image", type=['jpg', 'jpeg', 'png'])

    run_disabled = current_credits < DIAGNOSIS_COST
    if st.button("Run Wellness Check", type="primary", use_container_width=True, disabled=run_disabled):
        if side_f and top_f:
            with st.spinner("Analyzing wellness insights..."):
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                s_path, t_path = f"database_images/{ts}_s.png", f"database_images/{ts}_t.png"
                with open(s_path, "wb") as f:
                    f.write(side_f.getbuffer())
                with open(t_path, "wb") as f:
                    f.write(top_f.getbuffer())

                res = analyze_pet_vision(s_path, t_path, breed)
                pace = round(1.0 + (abs(5 - res['bcs']) * 0.15), 2)

                st.subheader("Results")
                st.write(res['opinion'])
                st.caption("ℹ️ This is an AI-generated wellness estimate, not a medical diagnosis. "
                           "Please consult a licensed veterinarian for any health concerns.")

                pdf_file = create_report(breed, res['bcs'], pace, res['opinion'])
                with open(pdf_file, "rb") as f:
                    st.download_button("📩 Download PDF Report", f, file_name=f"{breed}_Report.pdf")

                conn = sqlite3.connect('pet_health.db')
                conn.cursor().execute("INSERT INTO health_logs (breed, bcs, pace, opinion, date) VALUES (?,?,?,?,?)",
                                     (breed, res['bcs'], pace, res['opinion'], datetime.datetime.now().strftime('%Y-%m-%d %H:%M')))
                conn.commit()
                conn.close()

                deduct_credit(uid)
                st.rerun()
        else:
            st.warning("Please upload both images.")

if admin_code and admin_code == st.secrets.get("ADMIN_CODE", ""):
    with t2:
        conn = sqlite3.connect('pet_health.db')
        df = pd.read_sql_query("SELECT * FROM health_logs ORDER BY id DESC", conn)
        st.dataframe(df)
        conn.close()

st.divider()
st.caption("Contact: bslee@yahoo.com")
