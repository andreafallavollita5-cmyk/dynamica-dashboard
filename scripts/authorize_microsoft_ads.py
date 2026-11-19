"""Create and save the one-time Microsoft Ads refresh token."""

from __future__ import annotations

import argparse

from src.microsoft_ads_client import (
    MicrosoftAdsDeliveryError,
    authorize_with_device_code,
    build_authorization_url,
    exchange_authorization_response,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--response-uri",
        help="URL completa mostrata dal browser dopo il consenso Microsoft.",
    )
    parser.add_argument(
        "--device-code",
        action="store_true",
        help="Usa il codice dispositivo ed evita il redirect nativeclient.",
    )
    args = parser.parse_args()
    try:
        if args.device_code:
            authorize_with_device_code()
            print("Autorizzazione Microsoft Ads salvata nel file .env.")
            return 0
        if args.response_uri:
            exchange_authorization_response(args.response_uri)
            print("Autorizzazione Microsoft Ads salvata nel file .env.")
            return 0
        print("Apri questo indirizzo, accedi con l'account Microsoft Ads e autorizza:")
        print(build_authorization_url())
        print("Poi riesegui con --response-uri seguito dall'URL completa di ritorno.")
        return 0
    except MicrosoftAdsDeliveryError as exc:
        print(f"Errore: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
