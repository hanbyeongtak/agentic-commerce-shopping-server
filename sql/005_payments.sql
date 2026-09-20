-- 결제 내역(원장). 주문 1건당 2건: 고객 결제(구매자→판매자), 공급사 결제(판매자→공급자)를 모두 쌓는다.
-- 금융 기록이라 주문/회원이 삭제돼도 남도록 order_id 는 SET NULL, 당사자는 이메일 스냅샷으로 보관한다.
CREATE TABLE agnic.payments
(
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    order_id            INT                                                                 NULL,
    payment_type        ENUM ('CUSTOMER_PAYMENT', 'SUPPLIER_PAYMENT')                       NOT NULL,
    status              ENUM ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')  NOT NULL DEFAULT 'PENDING',
    payer_email         VARCHAR(255)                                                        NULL,
    payee_email         VARCHAR(255)                                                        NULL,
    from_address        VARCHAR(255)                                                        NULL,
    to_address          VARCHAR(255)                                                        NULL,
    amount_sats         BIGINT                                                              NOT NULL CHECK (amount_sats > 0),
    fee_sats            BIGINT                                                              NULL,
    fiat_amount_minor   INT                                                                 NULL,
    fiat_currency       VARCHAR(10)                                                         NULL,
    exchange_rate       DECIMAL(18, 2)                                                      NULL COMMENT '1 BTC = ? fiat_currency (결제 시점 환율)',
    provider            VARCHAR(50)                                                         NOT NULL DEFAULT 'GOBTCPAY',
    external_id         VARCHAR(255)                                                        NOT NULL COMMENT '결제사에 보낸 멱등키 (예: order-12-customer)',
    provider_payment_id VARCHAR(255)                                                        NULL,
    tx_id               VARCHAR(255)                                                        NULL,
    failure_reason      TEXT                                                                NULL COMMENT '가장 최근 실패 사유 (성공하면 NULL)',
    completed_at        TIMESTAMP                                                           NULL,
    created_at          TIMESTAMP                                                           NOT NULL DEFAULT current_timestamp(),
    updated_at          TIMESTAMP                                                           NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
    CONSTRAINT uq_payments_provider_external UNIQUE (provider, external_id),
    INDEX idx_payments_order (order_id),
    INDEX idx_payments_type_status (payment_type, status),
    INDEX idx_payments_payer (payer_email),
    INDEX idx_payments_payee (payee_email),
    CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES agnic.purchase_orders (order_id)
        ON UPDATE CASCADE ON DELETE SET NULL
) COLLATE = utf8mb4_unicode_ci;
