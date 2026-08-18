from app.settings import Settings


def get_settings():
    """
    This dependency function is to allow settings to be overridden in testing via a FastAPI's dependency overrides
    method.
    """
    return Settings()
