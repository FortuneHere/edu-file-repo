import json
import os
from io import BytesIO
from typing import Optional
from urllib import error, request

from pypdf import PdfReader


class AIConfigurationError(RuntimeError):
    """Raised when YandexGPT configuration is missing."""


class AISummaryService:
    def __init__(self):
        self.folder_id = os.getenv("YANDEX_GPT_FOLDER_ID")
        self.api_key = os.getenv("YANDEX_GPT_API_KEY")
        self.iam_token = os.getenv("YANDEX_IAM_TOKEN")
        self.model_name = os.getenv("YANDEX_GPT_MODEL", "yandexgpt-lite/latest")
        self.endpoint = os.getenv(
            "YANDEX_GPT_ENDPOINT",
            "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        )

        if not self.folder_id:
            raise AIConfigurationError("YANDEX_GPT_FOLDER_ID is not set")
        if not self.api_key and not self.iam_token:
            raise AIConfigurationError(
                "Set YANDEX_GPT_API_KEY or YANDEX_IAM_TOKEN for YandexGPT access"
            )

    def _extract_pdf_text(self, pdf_bytes: bytes, max_chars: int = 12000) -> str:
        reader = PdfReader(BytesIO(pdf_bytes))
        pages_text = []
        chars_left = max_chars
        for page in reader.pages:
            if chars_left <= 0:
                break
            page_text = page.extract_text() or ""
            if not page_text.strip():
                continue
            chunk = page_text[:chars_left]
            pages_text.append(chunk)
            chars_left -= len(chunk)
        return "\n".join(pages_text).strip()

    def _call_yandex_gpt(self, prompt_text: str) -> str:
        model_uri = "gpt://{folder_id}/{model}".format(
            folder_id=self.folder_id,
            model=self.model_name,
        )
        payload = {
            "modelUri": model_uri,
            "completionOptions": {
                "stream": False,
                "temperature": 0.2,
                "maxTokens": "220",
            },
            "messages": [
                {
                    "role": "system",
                    "text": (
                        "Ты ассистент в образовательной системе. "
                        "Сделай краткое и понятное описание методички на русском языке в 2-3 предложениях."
                    ),
                },
                {
                    "role": "user",
                    "text": prompt_text,
                },
            ],
        }

        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Api-Key {self.api_key}"
        else:
            headers["Authorization"] = f"Bearer {self.iam_token}"

        req = request.Request(self.endpoint, data=body, headers=headers, method="POST")
        with request.urlopen(req, timeout=40) as response:
            raw_response = response.read().decode("utf-8")
            parsed = json.loads(raw_response)
            alternatives = parsed.get("result", {}).get("alternatives", [])
            if not alternatives:
                raise RuntimeError("YandexGPT returned empty alternatives")
            text = alternatives[0].get("message", {}).get("text", "").strip()
            if not text:
                raise RuntimeError("YandexGPT returned empty summary")
            return text

    def summarize_pdf(self, pdf_bytes: bytes) -> Optional[str]:
        if not pdf_bytes:
            return None
        try:
            content = self._extract_pdf_text(pdf_bytes)
            if not content:
                return "Не удалось извлечь текст из PDF для краткого описания."

            prompt = (
                "Содержание методички:\n\n"
                f"{content}\n\n"
                "Верни только краткое описание сути документа."
            )
            return self._call_yandex_gpt(prompt)
        except error.HTTPError as exc:
            raise RuntimeError(f"YandexGPT HTTP error: {exc.code}") from exc
        except error.URLError as exc:
            raise RuntimeError("Cannot reach YandexGPT endpoint") from exc
        except Exception as exc:
            raise RuntimeError(f"Failed to summarize PDF: {str(exc)}") from exc
