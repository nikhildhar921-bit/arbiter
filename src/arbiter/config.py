from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    # No user/password: falls back to the OS user (local Postgres)
    database_url: str = "postgresql+psycopg://localhost:5432/arbiter"
    OPEN_AI_KEY: str
    # When true, skip the real OpenAI embeddings call (and Qdrant write) so a
    # load test doesn't cost real money or contend for the local Qdrant lock.
    # Not for normal use — set only for a load-test run.
    load_test_mode: bool = False

settings = Settings()
