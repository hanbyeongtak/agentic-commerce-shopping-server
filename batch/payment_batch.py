"""고객 결제 대기(CUSTOMER_PAYMENT_PENDING) 주문을 결제해 고객 결제 완료(CUSTOMER_PAYMENT_COMPLETED)로 바꾸는 배치.

실행:
    .venv/bin/python -m batch.payment_batch          # 2분 주기로 계속 실행
    .venv/bin/python -m batch.payment_batch --once   # 1회만 실행 (cron/테스트용)

"결제중" 상태가 없으므로 동시 실행은 DB 락으로 막는다. 결제 도중 죽어도 pay_order 가 멱등하게 만들어져 있어
(payment_id / payment_tx_id / externalId) 다음 주기에 이어서 처리해도 이중 결제되지 않는다.
"""
import logging

from app.db import get_conn
from app.payments import service
from app.payments.errors import PaymentError
from batch import runner

INTERVAL_MINUTES = 2
BATCH_SIZE = 100
LOCK_NAME = "payment_batch"

PENDING = "CUSTOMER_PAYMENT_PENDING"
COMPLETED = "CUSTOMER_PAYMENT_COMPLETED"

log = logging.getLogger("payment_batch")


def process_payment(order: dict) -> None:
    """주문 1건을 GoBTC Pay 로 결제한다. 결제가 확인되지 않으면 예외를 던진다."""
    service.pay_order(order["order_id"])


def _complete(cur, order_id: int) -> bool:
    # 결제하는 동안 주문이 취소되는 등 상태가 바뀌었다면 덮어쓰지 않는다
    cur.execute(
        "UPDATE purchase_orders SET delivery_status = %s, updated_at = NOW() "
        "WHERE order_id = %s AND delivery_status = %s",
        (COMPLETED, order_id, PENDING),
    )
    return cur.rowcount == 1


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
    cur.execute(
        "SELECT * FROM purchase_orders WHERE delivery_status = %s AND buyer_email IS NOT NULL "
        "ORDER BY order_id LIMIT %s",
        (PENDING, BATCH_SIZE),
    )
    orders = cur.fetchall()
    log.info("고객 결제 대기 주문 %d건 조회", len(orders))

    done = failed = 0
    for order in orders:
        order_id = order["order_id"]
        try:
            process_payment(order)
        except PaymentError as e:
            # 예상 가능한 실패(설정 누락, 잔액 부족, 결제 확인 대기 등)는 스택트레이스 없이 남기고 다음 주기에 재시도한다
            log.warning("결제 실패 order_id=%s: %s (다음 주기에 재시도)", order_id, e)
            failed += 1
            continue
        except Exception:
            log.exception("결제 실패 order_id=%s (다음 주기에 재시도)", order_id)
            failed += 1
            continue
        if not _complete(cur, order_id):
            log.warning("order_id=%s 는 결제 중 상태가 바뀌어 완료 처리하지 않았습니다", order_id)
            continue
        done += 1
    log.info("결제완료 %d건, 실패 %d건", done, failed)


def main() -> None:
    runner.run("payment_batch", run_once, INTERVAL_MINUTES)


if __name__ == "__main__":
    main()
