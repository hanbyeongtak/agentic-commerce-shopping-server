"""배치 공통 실행부: --once 1회 실행 / 기본은 주기 실행."""
import argparse
import logging
from collections.abc import Callable

from apscheduler.schedulers.blocking import BlockingScheduler


def run(name: str, job: Callable[[], None], interval_minutes: float) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger(name)

    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="1회만 실행하고 종료")
    args = parser.parse_args()

    if args.once:
        job()
        return

    def safe_job() -> None:
        # 예외가 스케줄러를 멈추지 않도록 한다
        try:
            job()
        except Exception:
            log.exception("배치 실행 중 오류")

    scheduler = BlockingScheduler()
    # max_instances=1: 이전 실행이 안 끝났으면 겹쳐 실행하지 않는다. 시작 즉시 1회 실행 후 주기마다 반복한다.
    scheduler.add_job(safe_job, "interval", minutes=interval_minutes, max_instances=1, coalesce=True)
    log.info("%s 시작 (%s분 주기)", name, interval_minutes)
    safe_job()
    scheduler.start()
