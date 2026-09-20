-- 판매자(머천트) 정보 / 구매자(지갑) 정보. *_enc 컬럼은 ENCRYPTION_KEY(Fernet)로 암호화된 값.
-- 머천트 API 키는 이미 있는 users.prefix / secret(암호화 저장) / type 컬럼을 사용한다.
ALTER TABLE agnic.users
    ADD COLUMN merchant_id            VARCHAR(255) NULL,
    ADD COLUMN merchant_xpub          VARCHAR(255) NULL,
    ADD COLUMN merchant_mnemonic_enc  TEXT         NULL,
    ADD COLUMN wallet_pubkey          VARCHAR(66)  NULL,
    ADD COLUMN wallet_address         VARCHAR(255) NULL,
    ADD COLUMN wallet_private_key_enc TEXT         NULL;

-- 주문: 결제하는 구매자와 결제 추적 정보
ALTER TABLE agnic.purchase_orders
    ADD COLUMN buyer_email    VARCHAR(255) NULL,
    ADD COLUMN payment_id     VARCHAR(255) NULL,
    ADD COLUMN payment_tx_id  VARCHAR(255) NULL,
    ADD COLUMN amount_sats    BIGINT       NULL,
    ADD CONSTRAINT fk_orders_buyer
        FOREIGN KEY (buyer_email) REFERENCES agnic.users (email)
            ON UPDATE CASCADE ON DELETE CASCADE;
