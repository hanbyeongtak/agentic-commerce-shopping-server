"""지갑이 없는 구매자(BUYER)의 키를 만들고 GoBTC Pay 지갑을 등록해 입금 주소(users.wallet_address)를 발급하는 배치.

발급된 주소에는 BTC 를 직접 입금(펀딩)해야 결제가 가능하다. 이 배치는 입금하지 않는다.

실행:
    .venv/bin/python -m batch.buyer_wallet_batch          # 2분 주기로 계속 실행
    .venv/bin/python -m batch.buyer_wallet_batch --once   # 1회만 실행 (cron/테스트용)
"""
import logging

from app.db import get_conn
from app.payments import service
from app.payments.errors import PaymentError
from batch import runner

INTERVAL_MINUTES = 2
BATCH_SIZE = 50
LOCK_NAME = "buyer_wallet_batch"

log = logging.getLogger("buyer_wallet_batch")


def run_once() -> None:
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT GET_LOCK(%s, 0) AS locked", (LOCK_NAME,))
        if not cur.fetchone()["locked"]:
            log.info("다른 배치가 실행 중이라 건너뜁니다")
            return
        try:
            cur.execute(
                "SELECT email FROM users WHERE user_type = 'BUYER' AND wallet_address IS NULL "
                "ORDER BY created_at LIMIT %s",
                (BATCH_SIZE,),
            )
            emails = [row["email"] for row in cur.fetchall()]
            log.info("지갑 미등록 구매자 %d명 조회", len(emails))

            done = failed = 0
            for email in emails:
                try:
                    address = service.setup_buyer_wallet(email)
                except PaymentError as e:
                    log.warning("지갑 등록 실패 email=%s (%s), 다음 주기에 다시 시도합니다", email, e)
                    failed += 1
                    continue
                if address:
                    log.info("지갑 등록 email=%s address=%s", email, address)
                    done += 1
            log.info("등록 %d명, 실패 %d명", done, failed)
        finally:
            cur.execute("SELECT RELEASE_LOCK(%s)", (LOCK_NAME,))


def main() -> None:
    runner.run("buyer_wallet_batch", run_once, INTERVAL_MINUTES)


if __name__ == "__main__":
    main()
