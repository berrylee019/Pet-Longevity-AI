"""
Lemon Squeezy 체크아웃 URL 생성 헬퍼
------------------------------------
Streamlit 앱에서 "Buy Now" 버튼을 누르면 이 함수를 호출해서
Lemon Squeezy 결제 페이지 URL을 받아온 뒤 사용자를 그 URL로 보냅니다.

필요한 환경변수:
- LEMONSQUEEZY_API_KEY   : Lemon Squeezy 대시보드 > Settings > API 에서 발급
- LEMONSQUEEZY_STORE_ID  : 대시보드 상단에서 확인 가능한 Store ID

주의:
- Lemon Squeezy는 JSON:API 스펙을 사용합니다 (Content-Type: application/vnd.api+json).
- variant_id는 상품(구독 플랜/크레딧 팩) 각각에 대해 대시보드에서 확인할 수 있습니다.
- API 스펙은 변경될 수 있으니, 실제 연동 전 https://docs.lemonsqueezy.com/api/checkouts 로 최신 필드를 한 번 확인하세요.
"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import requests
from typing import Optional

LEMONSQUEEZY_API_KEY = os.environ["LEMONSQUEEZY_API_KEY"]
STORE_ID = os.environ["LEMONSQUEEZY_STORE_ID"]
BASE_URL = "https://api.lemonsqueezy.com/v1"


def create_checkout_url(
    variant_id: str,
    user_id: str,
    credits: int,
    user_email: Optional[str] = None,
    redirect_url: Optional[str] = None,
) -> str:
    """
    Lemon Squeezy 체크아웃 세션을 생성하고 결제 페이지 URL을 반환합니다.

    custom_data에 user_id와 credits를 실어 보내는 것이 핵심입니다.
    결제가 완료되면 Lemon Squeezy가 보내는 웹훅 payload 안에
    이 custom_data가 그대로 담겨 돌아오기 때문에,
    FastAPI 웹훅 서버에서 "누구에게 크레딧 몇 개를 충전해야 하는지"를
    이 값으로 판단합니다.
    """
    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
    }

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user_email or "",
                    "custom": {
                        "user_id": user_id,
                        "credits": str(credits),
                    },
                },
                "product_options": {
                    # 결제 완료 후 사용자를 다시 Streamlit 앱으로 되돌려보낼 URL
                    # redirect_url을 명시적으로 넘기면(예: uid를 쿼리파라미터로 포함) 그 값을 우선 사용
                    "redirect_url": redirect_url or os.environ.get("CHECKOUT_REDIRECT_URL", ""),
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": STORE_ID}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    resp = requests.post(f"{BASE_URL}/checkouts", json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    return data["data"]["attributes"]["url"]
