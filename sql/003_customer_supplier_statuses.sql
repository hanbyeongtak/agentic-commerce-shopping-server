-- delivery_status 를 CUSTOMER_/SUPPLIER_ 결제 상태로 교체하고 PROCESSINGPAYMENT, PAYMENTCOMPLETED 를 제거한다.
-- enum 에서 값을 바로 빼면 그 값을 가진 행이 깨지므로 (1) 새 값 추가 → (2) 기존 행 이관 → (3) 옛 값 제거 순서로 진행한다.

-- 1) 새 값 추가 (옛 값은 아직 유지)
ALTER TABLE agnic.purchase_orders
    MODIFY delivery_status ENUM ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED',
                                 'PROCESSINGPAYMENT', 'PAYMENTCOMPLETED',
                                 'CUSTOMER_PAYMENT_PENDING', 'CUSTOMER_PAYMENT_COMPLETED', 'CUSTOMER_PAYMENT_CANCELLED',
                                 'SUPPLIER_PAYMENT_PENDING', 'SUPPLIER_PAYMENT_PROCESSING', 'SUPPLIER_PAYMENT_COMPLETED')
        NOT NULL DEFAULT 'PENDING';

-- 2) 기존 행 이관: 결제완료 → 고객 결제 완료, 결제중(진행 중이던 건) → 고객 결제 대기
UPDATE agnic.purchase_orders SET delivery_status = 'CUSTOMER_PAYMENT_COMPLETED' WHERE delivery_status = 'PAYMENTCOMPLETED';
UPDATE agnic.purchase_orders SET delivery_status = 'CUSTOMER_PAYMENT_PENDING'   WHERE delivery_status = 'PROCESSINGPAYMENT';

-- 3) 옛 값 제거, 신규 주문 기본값은 고객 결제 대기
ALTER TABLE agnic.purchase_orders
    MODIFY delivery_status ENUM ('PENDING', 'PROCESSING', 'SHIPPED', 'DELIVERED', 'CANCELLED',
                                 'CUSTOMER_PAYMENT_PENDING', 'CUSTOMER_PAYMENT_COMPLETED', 'CUSTOMER_PAYMENT_CANCELLED',
                                 'SUPPLIER_PAYMENT_PENDING', 'SUPPLIER_PAYMENT_PROCESSING', 'SUPPLIER_PAYMENT_COMPLETED')
        NOT NULL DEFAULT 'CUSTOMER_PAYMENT_PENDING';
