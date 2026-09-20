from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "agnic"

    agnic_api_url: str = "https://api.agnic.ai/api/autofill/products/search"
    agnic_token: str = ""

    jwt_secret: str = ""
    jwt_expire_minutes: int = 60

    gobtcpay_register_url: str = "https://api.gobtcpay.com/public/api/v1.2/merchant/auth/register"

    gobtcpay_base_url: str = "https://api.gobtcpay.com/public/api/v1.2"

    # 판매자 니모닉/구매자 개인키를 DB에 저장할 때 쓰는 Fernet 키. 분실하면 복호화할 수 없다.
    encryption_key: str = ""
    # 1 BTC = ? CAD. 비어 있으면 결제를 진행하지 않는다.
    btc_cad_rate: str = ""

    cors_origins: list[str] = ["http://localhost:5500"]


settings = Settings()
