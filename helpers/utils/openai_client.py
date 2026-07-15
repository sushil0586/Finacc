from __future__ import annotations

import base64
from typing import TYPE_CHECKING

from django.conf import settings

if TYPE_CHECKING:
    from openai import OpenAI


def get_openai_client() -> OpenAI:
    from openai import OpenAI

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


def generate_multimodal_text(
    prompt: str,
    *,
    media_bytes: bytes,
    media_mime_type: str,
    model: str | None = None,
) -> str:
    client = get_openai_client()
    encoded_media = base64.b64encode(media_bytes).decode("ascii")
    response = client.responses.create(
        model=model or settings.OPENAI_MODEL,
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:{media_mime_type};base64,{encoded_media}",
                    },
                ],
            }
        ],
    )
    return response.output_text
