from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MYSQL_URL: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    API_TOKEN: str
    PLC_POLL_ENABLED: bool = True
    PLC_POLL_DEFAULT_INTERVAL_S: int = 2
    PLC_POLL_MAX_INFLIGHT: int = 10
    PLC_POLL_TIMEOUT_S: float = 1.0
    PLC_POLL_DB_REFRESH_S: int = 30


settings = Settings()
