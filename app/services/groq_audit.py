import os
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

# Load the project's .env regardless of the server's working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def generate_audit_script(objective: str, columns: list[str]) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            f"GROQ_API_KEY is missing. Check {PROJECT_ROOT / '.env'}"
        )

    client = Groq(api_key=api_key)

    response = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
        messages=[
            {
                "role": "system",
                "content": (
                    "Generate proposed Pandas audit-analysis scripts only. "
                    "Return Python code using a DataFrame named df and "
                    "produce a result variable. Do not import modules, "
                    "access files, use networks, or modify source data. "
                    "Never claim an anomaly proves fraud. Do not invent "
                    "financial-year boundaries."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Audit objective: {objective}\n"
                    f"Available columns: {columns}\n"
                    "Generate a read-only Pandas analysis."
                ),
            },
        ],
        temperature=0,
    )

    return response.choices[0].message.content or ""
