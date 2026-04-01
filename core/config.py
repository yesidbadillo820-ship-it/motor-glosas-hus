from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Base de datos (Por defecto usa SQLite si no encuentra la de Render)
    database_url: str = "sqlite:///./glosas.db"
    
    # Seguridad JWT
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    
    # Llaves de IA (Se llenarán automáticamente en Render)
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    
    # Metadatos de la App
    app_name: str = "Motor Glosas HUS"
    app_version: str = "5.0.0"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> Settings:
    """
    Usa lru_cache para leer las variables de entorno una sola vez 
    y no saturar la memoria del servidor en cada petición.
    """
    return Settings()
