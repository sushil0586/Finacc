import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "FA.settings")

import django

django.setup()

from django.conf import settings
from helpers.utils.openai_client import generate_text


def main() -> None:
    if not settings.OPENAI_API_KEY:
        raise SystemExit("OPENAI_API_KEY is missing. Set it in your environment first.")

    output = generate_text("Reply with exactly: OpenAI setup is working.")
    print("OpenAI API call succeeded.")
    print(f"Model: {settings.OPENAI_MODEL}")
    print("Response:")
    print(output)


if __name__ == "__main__":
    main()
