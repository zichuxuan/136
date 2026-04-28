from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MYSQL_URL: str
    REDIS_URL: str
    MQTT_HOST: str
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str
    MQTT_PASSWORD: str
    API_TOKEN: str


settings = Settings()
