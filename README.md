# agentic-commerce-shopping-server
## 실행
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # DB_PASSWORD, AGNIC_TOKEN 채우기
.venv/bin/uvicorn app.main:app --reload
```
Swagger: http://localhost:8000/docs

## 결제 흐름 (GoBTC Pay, 메인넷)
1. `batch.merchant_register_batch` — 가입 회원을 머천트로 등록 (`users.user_id`)
2. 판매자 이메일로 온 6자리 코드를 `POST /merchants/{email}/verify-email {"code": "..."}` 로 전달 → 인증, xpub 연결, API 키 발급 (인증 코드는 1회용, 토큰 10분)
3. `batch.buyer_wallet_batch` — 구매자 키 생성 + 지갑 등록 → `GET /users/{email}` 의 `wallet_address` 로 **BTC 를 직접 입금**
4. 주문 생성 시 `buyer_email` 지정 → `batch.payment_batch` 가 결제 (`.env` 의 `BTC_CAD_RATE` 필수)

`ENCRYPTION_KEY` 는 판매자 니모닉/구매자 개인키/API 키 복호화에 쓰이므로 분실하지 않도록 백업한다.
