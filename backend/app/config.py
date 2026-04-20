from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://clusterizer:clusterizer@localhost:5432/clusterizer"

    class Config:
        env_file = ".env"


settings = Settings()
