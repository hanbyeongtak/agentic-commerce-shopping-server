"""가입한 회원(users.user_id 가 NULL)을 gobtcpay 머천트로 등록하고, 응답의 userId 를 users.user_id 에 저장하는 배치.

실행:
    .venv/bin/python -m batch.merchant_register_batch          # 2분 주기로 계속 실행
    .venv/bin/python -m batch.merchant_register_batch --once   # 1회만 실행 (cron/테스트용)
"""
import logging
import secrets

import httpx

from app.config import settings
from app.db import get_conn
from batch import runner

INTERVAL_MINUTES = 2
BATCH_SIZE = 50
REQUEST_TIMEOUT = 30
# 여러 배치 프로세스가 동시에 떠도 같은 회원을 두 번 등록하지 않도록 하는 DB 락 이름
LOCK_NAME = "merchant_register_batch"

log = logging.getLogger("merchant_register_batch")


def register_merchant(email: str, display_name: str, merchant_name: str) -> str:
    """gobtcpay 에 머천트를 등록하고 발급된 userId 를 반환한다. 실패하면 예외를 던진다."""
    resp = httpx.post(
        settings.gobtcpay_register_url,
        json={
            "email": email,
            "password": "1q2w3e4r5t!",#secrets.token_urlsafe(32),
            "displayName": display_name,
            "merchantName": merchant_name,
        },
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["userId"]


def run_once() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, 0) AS locked", (LOCK_NAME,))
        if not cur.fetchone()["locked"]:
            log.info("다른 배치가 실행 중이라 건너뜁니다")
            return
        try:
            _process(cur)
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))


def _process(cur) -> None:
    # merchantName: 판매자는 첫 스토어명, 없으면 displayName
    cur.execute(
        "SELECT u.email, "
        "       (SELECT s.store_name FROM stores s WHERE s.seller_email = u.email ORDER BY s.store_id LIMIT 1) AS store_name "
        "FROM users u WHERE u.user_id IS NULL ORDER BY u.created_at LIMIT %s",
        (BATCH_SIZE,),
    )
    users = cur.fetchall()
    log.info("머천트 미등록 회원 %d명 조회", len(users))

    done = failed = 0
    for user in users:
        email = user["email"]
        display_name = email.split("@")[0]
        try:
            user_id = register_merchant(email, display_name, user["store_name"] or display_name)
        except (httpx.HTTPError, KeyError, ValueError) as e:
            # 외부 API 장애(503 등)나 응답 형식 오류는 예상 가능한 실패라 스택트레이스 없이 남긴다
            log.warning("머천트 등록 실패 email=%s (%s: %s), 다음 주기에 다시 시도합니다", email, type(e).__name__, e)
            failed += 1
            continue
        cur.execute("UPDATE users SET user_id = %s WHERE email = %s AND user_id IS NULL", (user_id, email))
        done += 1
    log.info("등록 %d명, 실패 %d명", done, failed)


def main() -> None:
    runner.run("merchant_register_batch", run_once, INTERVAL_MINUTES)


if __name__ == "__main__":
    main()
