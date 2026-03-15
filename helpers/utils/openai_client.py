from openai import OpenAI

from django.conf import settings


def get_openai_client() -> OpenAI:
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not configured.")
    return OpenAI(api_key=api_key)


def generate_text(prompt: str, model: str | None = None) -> str:
    client = get_openai_client()
    response = client.responses.create(
        model=model or settings.OPENAI_MODEL,
        input=prompt,
    )
    return response.output_text
