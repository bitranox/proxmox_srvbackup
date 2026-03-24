"""Unit tests for build_summary_report and build_summary_subject.

Covers all branches: success, partial failure, total failure,
skipped backup types, and error message formatting.
"""

from __future__ import annotations

from proxmox_srvbackup.domain.behaviors import build_summary_report, build_summary_subject
from proxmox_srvbackup.domain.models import BackupResult, BackupSummary

# ---------------------------------------------------------------------------
# build_summary_report
# ---------------------------------------------------------------------------


class TestBuildSummaryReport:
    """Verify human-readable backup report formatting."""

    def test_all_ok_single_server(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="px01", config_ok=True, zfs_ok=True, duration_seconds=42.5),),
            total_duration_seconds=42.5,
        )
        report = build_summary_report(summary)
        assert "Backup completed in 42.5s" in report
        assert "1 total, 0 failed" in report
        assert "px01: OK (42.5s)" in report

    def test_all_ok_multiple_servers(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(server="px01", config_ok=True, zfs_ok=True, duration_seconds=10.0),
                BackupResult(server="px02", config_ok=True, zfs_ok=True, duration_seconds=20.0),
            ),
            total_duration_seconds=20.0,
        )
        report = build_summary_report(summary)
        assert "2 total, 0 failed" in report
        assert "px01: OK" in report
        assert "px02: OK" in report

    def test_config_error_shown(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(
                    server="px01",
                    config_ok=False,
                    config_error="Connection refused",
                    zfs_ok=True,
                    duration_seconds=5.0,
                ),
            ),
            total_duration_seconds=5.0,
        )
        report = build_summary_report(summary)
        assert "px01: FAILED" in report
        assert "config error: Connection refused" in report
        assert "1 total, 1 failed" in report

    def test_zfs_error_shown(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(
                    server="px01",
                    config_ok=True,
                    zfs_ok=False,
                    zfs_error="snapshot creation failed",
                    duration_seconds=3.0,
                ),
            ),
            total_duration_seconds=3.0,
        )
        report = build_summary_report(summary)
        assert "px01: FAILED" in report
        assert "zfs error: snapshot creation failed" in report

    def test_config_skipped_shown(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="fw", config_skipped=True, zfs_ok=True, duration_seconds=1.0),),
            total_duration_seconds=1.0,
        )
        report = build_summary_report(summary)
        assert "config: skipped (disabled)" in report
        assert "fw: OK" in report

    def test_zfs_skipped_shown(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="fw", config_ok=True, zfs_skipped=True, duration_seconds=1.0),),
            total_duration_seconds=1.0,
        )
        report = build_summary_report(summary)
        assert "zfs: skipped (disabled)" in report
        assert "fw: OK" in report

    def test_mixed_success_and_failure(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(server="px01", config_ok=True, zfs_ok=True, duration_seconds=10.0),
                BackupResult(
                    server="px02",
                    config_ok=False,
                    config_error="timeout",
                    zfs_ok=False,
                    zfs_error="pool busy",
                    duration_seconds=5.0,
                ),
                BackupResult(server="px03", config_ok=True, zfs_skipped=True, duration_seconds=2.0),
            ),
            total_duration_seconds=15.0,
        )
        report = build_summary_report(summary)
        assert "3 total, 1 failed" in report
        assert "px01: OK" in report
        assert "px02: FAILED" in report
        assert "config error: timeout" in report
        assert "zfs error: pool busy" in report
        assert "px03: OK" in report
        assert "zfs: skipped (disabled)" in report


# ---------------------------------------------------------------------------
# build_summary_subject
# ---------------------------------------------------------------------------


class TestBuildSummarySubject:
    """Verify email subject line tag selection."""

    def test_all_ok_returns_ok_tag(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="a", config_ok=True, zfs_ok=True),),
        )
        assert build_summary_subject(summary) == "[OK] Proxmox Backup Summary"

    def test_all_failed_returns_error_tag(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(server="a", config_ok=False, config_error="fail"),
                BackupResult(server="b", zfs_ok=False, zfs_error="fail"),
            ),
        )
        assert build_summary_subject(summary) == "[ERROR] Proxmox Backup Summary"

    def test_partial_failure_returns_warning_tag(self) -> None:
        summary = BackupSummary(
            results=(
                BackupResult(server="a", config_ok=True, zfs_ok=True),
                BackupResult(server="b", config_ok=False, config_error="fail"),
            ),
        )
        assert build_summary_subject(summary) == "[WARNING] Proxmox Backup Summary"

    def test_single_server_failure_is_error(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="a", config_ok=False, config_error="fail"),),
        )
        assert build_summary_subject(summary) == "[ERROR] Proxmox Backup Summary"

    def test_skipped_only_counts_as_ok(self) -> None:
        summary = BackupSummary(
            results=(BackupResult(server="a", config_ok=True, zfs_skipped=True),),
        )
        assert build_summary_subject(summary) == "[OK] Proxmox Backup Summary"
