from app.config import settings


def choose_model(quality: str) -> str:
    if quality == "deep":
        return settings.model_deep

    return settings.model_default