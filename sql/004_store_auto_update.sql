-- 스토어 자동업데이트 설정: 여부(기본 꺼짐)와 주기(일 단위, 1/7/30 중 하나, 기본 1)
ALTER TABLE agnic.stores
    ADD COLUMN auto_update_enabled       TINYINT(1) NOT NULL DEFAULT 0,
    ADD COLUMN auto_update_interval_days INT        NOT NULL DEFAULT 1,
    ADD CONSTRAINT chk_stores_auto_update_interval CHECK (auto_update_interval_days IN (1, 7, 30));
