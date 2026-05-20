import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from dotenv import dotenv_values


REQUIRED_ENV_VARS = [
    "DATABASE_URL",
    "YANDEX_ENDPOINT",
    "YANDEX_ACCESS_KEY_ID",
    "YANDEX_SECRET_ACCESS_KEY",
    "YANDEX_BUCKET_NAME",
]


def resolve_env_value(
    key: str, file_values: Dict[str, Optional[str]]
) -> Tuple[Optional[str], Optional[str]]:
    runtime_value = os.getenv(key)
    if runtime_value and runtime_value.strip():
        return runtime_value.strip(), "process environment"

    file_value = file_values.get(key)
    if file_value and file_value.strip():
        return file_value.strip(), ".env file"

    return None, None


def main() -> int:
    backend_dir = Path(__file__).resolve().parent.parent
    env_file = backend_dir / ".env"
    env_values: Dict[str, Optional[str]] = dotenv_values(env_file)

    missing: List[str] = []

    print("Checking backend environment for E2E smoke prerequisites...")
    print(f"Using .env path: {env_file}")

    for key in REQUIRED_ENV_VARS:
        value, source = resolve_env_value(key, env_values)
        if value is None:
            missing.append(key)
            print(f"[MISSING] {key}")
            continue
        print(f"[OK] {key} ({source})")

    if missing:
        print("\nEnvironment check failed.")
        print("Please set the missing variables before running E2E smoke test:")
        for key in missing:
            print(f"- {key}")
        return 1

    print("\nEnvironment check passed. Ready for E2E smoke testing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
