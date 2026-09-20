-- 공급자 이메일. 공급자 결제(SUPPLIER_PAYMENT)의 payee_email 로 사용한다.
ALTER TABLE agnic.products
    ADD COLUMN merchant_email VARCHAR(255) NULL AFTER merchant_id;
