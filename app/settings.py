import os
import json
import re
from typing import List, Optional


from pydantic import BaseSettings, Field, validator
# from pydantic import Field, field_validator
# from pydantic_settings import BaseSettings


DEFAULT_TRUSTED_ORIGINS = [
    "https://dandjoo.bio.wa.gov.au",
    "https://test.bdr.wa.gov.au",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]


class Settings(BaseSettings):
    """
    Application settings

    Pydantic will look up the settings from `os.environ` every time this class is instantiated,
    env variables will be matched with the attribute name (unless `env=` is defined), in a case-insensitive manner.
    In addition, the `os.getenv()` calls below happen at import-time to create default values for some settings.
    """
    mongodb_host: str = os.getenv('MONGODB_HOST', '127.0.0.1')
    mongodb_port: int = os.getenv('MONGODB_PORT', 27017)
    mongondb_direct_connection: bool = os.getenv('MONGODB_DIRECT_CONNECTION', True)
    db_name: str = Field(env='MONGODB_NAME', default='local-public')
    root_path: str = os.getenv('ROOT_PATH', '')
    # In production "TEMPORARY_FILE_STORAGE_PATH" points to a volume backed by Blob storage,
    # so files written there are persistent.
    temp_file_storage_path: str = Field(env='TEMPORARY_FILE_STORAGE_PATH', default='/tmp')
    geoserver_url: str = os.getenv('GEOSERVER_URL', 'http://localhost:8080/geoserver/dandjoo/')
    dandjoo_curation_api_url: str = os.getenv('DANDJOO_CURATION_API_URL')
    max_export_size: int = Field(env='EXPORT_MAX', default=500000)
    origins: List[str] = Field(env='TRUSTED_ORIGINS', default=DEFAULT_TRUSTED_ORIGINS)
    authz_api_url: str = os.getenv('AUTHZ_API_URL')
    local_timezone: str = os.getenv('LOCAL_TIMEZONE', 'Australia/West')
    dev_auth: bool = os.getenv('DEV_AUTH', False)
    dev_auth_user_id: str = os.getenv('DEV_AUTH_USER_ID', 'testing')
    cluster_radius: int = os.getenv('CLUSTER_RADIUS', 250)
    cluster_extent: int = os.getenv('CLUSTER_EXTENT', 512)
    cluster_min_zoom_threshold: int = os.getenv('CLUSTER_MIN_ZOOM_THRESHOLD', 8)
    cluster_min_zoom_limit: int = os.getenv('CLUSTER_MIN_ZOOM_LIMIT', 10000)
    cluster_max_zoom_without_records: int = os.getenv('CLUSTER_MAX_ZOOM_WITHOUT_RECORDS', 15)
    obfuscation_grid_size: float = os.getenv('OBFUSCATION_GRID_SIZE', 0.1)
    redis_password: str = os.getenv('REDIS_PASSWORD', None)
    redis_host: str = os.getenv('REDIS_HOST', None)
    redis_port: int = os.getenv('REDIS_PORT', None)
    redis_cache_ttl_seconds: int = os.getenv('REDIS_CACHE_TTL_SECONDS', 180)
    # wkhtml_path : str =  os.getenv('WKHTML_PATH', 'C:/Program Files/wkhtmltopdf/bin/wkhtmltopdf.exe')
    wkhtml_path : str =  os.getenv('WKHTML_PATH', 'default')

    azure_account_name: Optional[str] = Field(env='AZURE_ACCOUNT_NAME', default=None)
    azure_account_key: Optional[str] = Field(env='AZURE_ACCOUNT_KEY', default=None)

    class Config:
        @classmethod
        def parse_env_var(cls, field_name, raw_value):
            if field_name == "origins":
                return raw_value

            return json.loads(raw_value)

    @validator("origins", pre=True)
    # @field_validator("origins", mode="before")
    def parse_trusted_origins(cls, value):
        if value is None:
            return DEFAULT_TRUSTED_ORIGINS

        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []

            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                parsed_value = re.split(r"[\s,]+", value)

            value = parsed_value

        origins = [origin.strip() for origin in value if origin and origin.strip()]
        if "*" in origins:
            raise ValueError(
                "TRUSTED_ORIGINS cannot contain '*' because CORS allows credentials. "
                "Configure explicit trusted origins instead."
            )

        return origins


# fastapi-auth directly uses API_SYSTEM_KEY environment variable rather than settings
if os.getenv('API_SYSTEM_KEY') is None:
    os.environ['API_SYSTEM_KEY'] = 'password'  # use default for local dev
