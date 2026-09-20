-- 주문 1건에는 결제가 2건: CUSTOMER_PAYMENT(구매자→판매자), SUPPLIER_PAYMENT(판매자→공급자).
-- 주문당 종류별로 1건만 허용한다. (order_id 가 NULL 인 보존 행은 유니크 대상에서 제외된다)
ALTER TABLE agnic.payments
    ADD CONSTRAINT uq_payments_order_type UNIQUE (order_id, payment_type);

ALTER TABLE agnic.payments
    MODIFY payment_type ENUM ('CUSTOMER_PAYMENT', 'SUPPLIER_PAYMENT') NOT NULL
        COMMENT 'CUSTOMER_PAYMENT: 구매자→판매자, SUPPLIER_PAYMENT: 판매자→공급자',
    MODIFY payer_email VARCHAR(255) NULL COMMENT '지급하는 쪽 (구매자 또는 판매자)',
    MODIFY payee_email VARCHAR(255) NULL COMMENT '받는 쪽 (판매자 또는 공급자)',
    MODIFY external_id VARCHAR(255) NOT NULL COMMENT '결제사에 보낸 멱등키 (order-{order_id}-customer / order-{order_id}-supplier)';
