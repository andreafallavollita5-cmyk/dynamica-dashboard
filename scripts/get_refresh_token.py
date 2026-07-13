from __future__ import annotations

from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from google_ads_common import ENV_PATH, load_settings


SCOPE = ["https://www.googleapis.com/auth/adwords"]


def upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    prefix = f"{key}="
    updated = False
    next_lines = []

    for line in lines:
        if line.startswith(prefix):
            next_lines.append(f"{key}={value}")
            updated = True
        else:
            next_lines.append(line)

    if not updated:
        next_lines.append(f"{key}={value}")

    path.write_text("\n".join(next_lines) + "\n", encoding="utf-8")


def main() -> None:
    settings = load_settings()
    if not settings["client_secrets_path"]:
        raise RuntimeError("GOOGLE_ADS_CLIENT_SECRETS_PATH is missing in .env")

    flow = InstalledAppFlow.from_client_secrets_file(
        settings["client_secrets_path"],
        scopes=SCOPE,
    )
    credentials = flow.run_local_server(
        port=0,
        prompt="consent",
        authorization_prompt_message=(
            "Apri questo URL nel browser e autorizza l'accesso:\n{url}"
        ),
        success_message="Autorizzazione completata. Puoi tornare a Codex.",
    )

    if not credentials.refresh_token:
        raise RuntimeError(
            "Google non ha restituito un refresh token. Riprova con prompt=consent "
            "o revoca prima l'accesso dell'app dalle impostazioni Google."
        )

    upsert_env_value(ENV_PATH, "GOOGLE_ADS_REFRESH_TOKEN", credentials.refresh_token)
    print(f"\nRefresh token salvato in {ENV_PATH}")


if __name__ == "__main__":
    main()
