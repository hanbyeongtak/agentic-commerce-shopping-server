class PaymentError(Exception):
    """결제 진행 중 예상 가능한 실패 (설정 누락, 검증 실패, 외부 API 오류 등)."""
