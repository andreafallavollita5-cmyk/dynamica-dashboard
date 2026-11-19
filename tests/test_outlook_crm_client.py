from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.crm_excel_client import read_crm_export_frame
from src.outlook_crm_client import (
    OutlookCRMError,
    OutlookSettings,
    DownloadResult,
    download_crm_with_retries,
    download_latest_crm_attachment,
    load_outlook_settings,
    read_outlook_status,
)


class FakeResponse:
    def __init__(self, payload=None, *, status_code=200, content=b""):
        self._payload = payload
        self.status_code = status_code
        self.content = content

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


def workbook_bytes() -> bytes:
    stream = io.BytesIO()
    with pd.ExcelWriter(stream, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Id Lead": ["L-1"],
                "Campagna": ["CRM"],
                "Data e ora di creazione": [datetime(2026, 8, 10, 12)],
                "Utm campaign": ["utm"],
            }
        ).to_excel(writer, sheet_name="LEAD QUESTO MESE PULITE", index=False)
    return stream.getvalue()


def settings(folder: Path) -> OutlookSettings:
    return OutlookSettings(
        tenant_id="tenant",
        client_id="client",
        client_secret="never-print-this",
        mailbox="dyn.leadgen@tig.it",
        input_dir=folder,
        subject="DYNAMICA CRM",
        attachment_pattern="*.xlsx",
    )


class OutlookCRMClientTests(unittest.TestCase):
    def test_exact_attachment_is_downloaded_validated_and_timestamped(self):
        filename = "482bf6d9-5c52-457b-9fcc-02d9d14dc8f5.xlsx"
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "message-id",
                                "subject": "Any subject is accepted for an exact name",
                                "receivedDateTime": "2026-09-01T04:30:00Z",
                                "hasAttachments": True,
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "attachment-id",
                                "name": filename,
                                "contentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                "size": len(workbook_bytes()),
                                "isInline": False,
                            }
                        ]
                    }
                ),
                FakeResponse(content=workbook_bytes()),
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            result = download_latest_crm_attachment(
                settings=settings(Path(temp)),
                attachment_name=filename,
                session=session,
                token_provider=lambda _settings: "token",
            )
            self.assertTrue(result.downloaded)
            self.assertEqual(result.path.name, filename)
            self.assertEqual(len(read_crm_export_frame(result.path)), 1)
            self.assertEqual(
                datetime.fromtimestamp(result.path.stat().st_mtime).astimezone().date(),
                datetime(2026, 9, 1).date(),
            )
        self.assertTrue(session.calls[2][0].endswith("/$value"))

    def test_generic_download_requires_exact_subject(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "wrong",
                                "subject": "Unrelated spreadsheet",
                                "receivedDateTime": "2026-09-01T05:00:00Z",
                                "hasAttachments": True,
                            },
                            {
                                "id": "right",
                                "subject": "  dynamica crm  ",
                                "receivedDateTime": "2026-09-01T04:30:00Z",
                                "hasAttachments": True,
                            },
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "a",
                                "name": "crm.xlsx",
                                "isInline": False,
                            }
                        ]
                    }
                ),
                FakeResponse(content=workbook_bytes()),
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            result = download_latest_crm_attachment(
                settings=settings(Path(temp)),
                session=session,
                token_provider=lambda _settings: "token",
            )
            self.assertEqual(result.path.name, "crm.xlsx")
        self.assertIn("/messages/right/attachments", session.calls[1][0])

    def test_graph_error_is_safe_and_does_not_expose_secret(self):
        session = FakeSession(
            [
                FakeResponse(
                    {"error": {"code": "ErrorAccessDenied", "message": "secret"}},
                    status_code=403,
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(OutlookCRMError) as caught:
                download_latest_crm_attachment(
                    settings=settings(Path(temp)),
                    session=session,
                    token_provider=lambda _settings: "token",
                )
        self.assertIn("ErrorAccessDenied", str(caught.exception))
        self.assertNotIn("never-print-this", str(caught.exception))
        self.assertNotIn("secret", str(caught.exception))

    def test_invalid_workbook_is_not_saved(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "message",
                                "subject": "DYNAMICA CRM",
                                "receivedDateTime": "2026-09-01T04:30:00Z",
                                "hasAttachments": True,
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {"id": "attachment", "name": "invalid.xlsx", "isInline": False}
                        ]
                    }
                ),
                FakeResponse(content=b"not an xlsx"),
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            result = download_latest_crm_attachment(
                settings=settings(folder),
                session=session,
                token_provider=lambda _settings: "token",
            )
            self.assertIsNone(result.path)
            self.assertEqual(list(folder.iterdir()), [])

    def test_subject_prefix_is_not_accepted(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "message",
                                "subject": "DYNAMICA CRM - extra",
                                "receivedDateTime": "2026-09-01T04:30:00Z",
                                "hasAttachments": True,
                            }
                        ]
                    }
                )
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            result = download_latest_crm_attachment(
                settings=settings(Path(temp)),
                session=session,
                token_provider=lambda _settings: "token",
            )
        self.assertIsNone(result.path)
        self.assertEqual(len(session.calls), 1)

    def test_automatic_download_ignores_matching_email_from_previous_day(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "old-message",
                                "subject": "DYNAMICA CRM",
                                "receivedDateTime": "2026-10-01T09:49:24Z",
                                "hasAttachments": True,
                            },
                            {
                                "id": "today-message",
                                "subject": "DYNAMICA CRM",
                                "receivedDateTime": "2026-10-02T08:30:31Z",
                                "hasAttachments": True,
                            },
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {"id": "attachment", "name": "crm.xlsx", "isInline": False}
                        ]
                    }
                ),
                FakeResponse(content=workbook_bytes()),
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            result = download_latest_crm_attachment(
                settings=settings(Path(temp)),
                received_on=date(2026, 10, 2),
                session=session,
                token_provider=lambda _settings: "token",
            )
        self.assertEqual(result.message_id, "today-message")
        self.assertIn("/messages/today-message/attachments", session.calls[1][0])

    def test_message_pagination_is_followed(self):
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "value": [],
                        "@odata.nextLink": "https://graph.microsoft.com/next",
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {
                                "id": "message",
                                "subject": "DYNAMICA CRM",
                                "receivedDateTime": "2026-09-01T04:30:00Z",
                                "hasAttachments": True,
                            }
                        ]
                    }
                ),
                FakeResponse(
                    {
                        "value": [
                            {"id": "attachment", "name": "crm.xlsx", "isInline": False}
                        ]
                    }
                ),
                FakeResponse(content=workbook_bytes()),
            ]
        )
        with tempfile.TemporaryDirectory() as temp:
            result = download_latest_crm_attachment(
                settings=settings(Path(temp)),
                session=session,
                token_provider=lambda _settings: "token",
            )
        self.assertEqual(result.path.name, "crm.xlsx")
        self.assertEqual(session.calls[1][0], "https://graph.microsoft.com/next")

    def test_retries_then_persists_success_without_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = settings(folder)
            config = OutlookSettings(
                **{
                    **config.__dict__,
                    "retry_attempts": 3,
                    "retry_delay_seconds": 15,
                }
            )
            target = folder / "crm.xlsx"
            target.write_bytes(workbook_bytes())
            results = iter(
                [
                    DownloadResult(None, None, None, False),
                    DownloadResult(None, None, None, False),
                    DownloadResult(
                        target,
                        datetime.fromisoformat("2026-09-30T08:31:31+00:00"),
                        "crm.xlsx",
                        True,
                        "message-id",
                        "hash",
                    ),
                ]
            )
            sleeps = []

            result = download_crm_with_retries(
                settings=config,
                downloader=lambda **_kwargs: next(results),
                sleeper=sleeps.append,
            )

            self.assertTrue(result.downloaded)
            self.assertEqual(sleeps, [15, 15])
            status = read_outlook_status(folder)
            self.assertEqual(status["status"], "ok")
            self.assertEqual(status["last_success"]["message_id"], "message-id")
            self.assertNotIn("never-print-this", json.dumps(status))

    def test_exhausted_retries_mark_status_stale(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            config = settings(folder)
            config = OutlookSettings(
                **{
                    **config.__dict__,
                    "retry_attempts": 3,
                    "retry_delay_seconds": 0,
                }
            )
            calls = []

            result = download_crm_with_retries(
                settings=config,
                downloader=lambda **_kwargs: (
                    calls.append(True) or DownloadResult(None, None, None, False)
                ),
                sleeper=lambda _seconds: None,
            )

            self.assertIsNone(result.path)
            self.assertEqual(len(calls), 3)
            self.assertEqual(read_outlook_status(folder)["status"], "stale")

    def test_dynamics_credentials_are_reused_only_when_explicit(self):
        environment = {
            "OUTLOOK_REUSE_DYNAMICS_CREDENTIALS": "true",
            "OUTLOOK_TENANT_ID": "",
            "OUTLOOK_CLIENT_ID": "",
            "OUTLOOK_CLIENT_SECRET": "",
            "DYNAMICS_TENANT_ID": "tenant",
            "DYNAMICS_CLIENT_ID": "client",
            "DYNAMICS_CLIENT_SECRET": "secret",
            "OUTLOOK_MAILBOX": "dyn.leadgen@tig.it",
        }
        with patch.dict("os.environ", environment, clear=False):
            loaded = load_outlook_settings()
        self.assertEqual(loaded.tenant_id, "tenant")
        self.assertEqual(loaded.client_id, "client")
        self.assertEqual(loaded.client_secret, "secret")


if __name__ == "__main__":
    unittest.main()
