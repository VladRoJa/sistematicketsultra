from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from openpyxl import Workbook

from app.routine_control.providers.runtime import (
    ArtifactStore,
    ArtifactStoreError,
    BrowserPhase,
    BrowserRuntime,
    ProviderBrowserError,
    ProviderLockError,
    ProviderRuntimeConfig,
    provider_lock,
)


class _FakePage:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def set_default_timeout(self, _value: int) -> None:
        pass

    def set_default_navigation_timeout(self, _value: int) -> None:
        pass

    def close(self) -> None:
        self.events.append("page")


class _FakeContext:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.page = _FakePage(events)

    def new_page(self):
        return self.page

    def close(self) -> None:
        self.events.append("context")


class _FakeBrowser:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.context = _FakeContext(events)

    def new_context(self, **_kwargs):
        return self.context

    def close(self) -> None:
        self.events.append("browser")


class _FakeChromium:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def launch(self, **_kwargs):
        return _FakeBrowser(self.events)


class _FakePlaywright:
    def __init__(self, events: list[str]) -> None:
        self.chromium = _FakeChromium(events)


class _FakeManager:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def start(self):
        return _FakePlaywright(self.events)

    def stop(self) -> None:
        self.events.append("manager")


class ProviderRuntimeTestCase(unittest.TestCase):
    def _xlsx(self, path: Path, headers: list[str]) -> bytes:
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.append(headers)
        worksheet.append(["value"] * len(headers))
        workbook.save(path)
        workbook.close()
        return path.read_bytes()

    def test_artifacts_are_unique_and_sha256_is_binary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            first = store.create_run_directory(provider_key="gasca", dataset_key="new_members")
            second = store.create_run_directory(provider_key="gasca", dataset_key="new_members")
            self.assertNotEqual(first, second)
            partial, final = store.prepare_download(
                run_directory=first,
                source_filename="members.xlsx",
            )
            content = self._xlsx(partial, ["IDSocio"])
            artifact = store.finalize_download(
                partial_path=partial,
                final_path=final,
                provider_key="gasca",
                dataset_key="new_members",
                required_headers={"IDSocio"},
                extracted_at_utc=datetime(2026, 7, 23, tzinfo=timezone.utc),
                business_date_from=date(2026, 7, 1),
                business_date_to=date(2026, 7, 23),
                source_filename="members.xlsx",
            )
            self.assertEqual(artifact.sha256, hashlib.sha256(content).hexdigest())
            self.assertEqual(artifact.size_bytes, len(content))

    def test_path_traversal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ArtifactStore(temp_dir)
            run_dir = store.create_run_directory(provider_key="gasca", dataset_key="new_members")
            with self.assertRaises(ArtifactStoreError):
                store.prepare_download(
                    run_directory=run_dir,
                    source_filename="../secret.xlsx",
                )

    def test_invalid_xlsx_and_missing_headers_remove_partial(self) -> None:
        for invalid_kind in ("not-xlsx", "missing-header"):
            with self.subTest(invalid_kind=invalid_kind), tempfile.TemporaryDirectory() as temp_dir:
                store = ArtifactStore(temp_dir)
                run_dir = store.create_run_directory(provider_key="gasca", dataset_key="new_members")
                partial, final = store.prepare_download(
                    run_directory=run_dir,
                    source_filename="members.xlsx",
                )
                if invalid_kind == "not-xlsx":
                    partial.write_bytes(b"not a workbook")
                else:
                    self._xlsx(partial, ["Other"])
                with self.assertRaises(ArtifactStoreError):
                    store.finalize_download(
                        partial_path=partial,
                        final_path=final,
                        provider_key="gasca",
                        dataset_key="new_members",
                        required_headers={"IDSocio"},
                        extracted_at_utc=datetime.now(timezone.utc),
                        business_date_from=date(2026, 7, 1),
                        business_date_to=date(2026, 7, 23),
                        source_filename="members.xlsx",
                    )
                self.assertFalse(partial.exists())
                self.assertFalse(final.exists())

    def test_file_lock_prevents_concurrency_and_releases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with provider_lock(temp_dir, provider_key="gasca", dataset_key="new_members"):
                with self.assertRaises(ProviderLockError):
                    with provider_lock(
                        temp_dir,
                        provider_key="gasca",
                        dataset_key="new_members",
                    ):
                        pass
            with provider_lock(temp_dir, provider_key="gasca", dataset_key="new_members"):
                pass

    def test_browser_resources_close_and_retry_is_bounded(self) -> None:
        events: list[str] = []
        calls = 0

        def operation(_page, tracker, _attempt):
            nonlocal calls
            calls += 1
            tracker.set(BrowserPhase.LOGIN)
            raise RuntimeError("secret-value")

        runtime = BrowserRuntime(
            ProviderRuntimeConfig(
                artifact_root=Path("unused"),
                headless=True,
                timeout_ms=1_000,
                max_attempts=2,
            ),
            playwright_factory=lambda: _FakeManager(events),
            sleeper=lambda _seconds: None,
        )
        with self.assertRaises(ProviderBrowserError) as caught:
            runtime.run(operation)
        self.assertEqual(calls, 2)
        self.assertEqual(caught.exception.attempts, 2)
        self.assertNotIn("secret-value", str(caught.exception))
        self.assertEqual(
            events,
            ["page", "context", "browser", "manager"] * 2,
        )


if __name__ == "__main__":
    unittest.main()
