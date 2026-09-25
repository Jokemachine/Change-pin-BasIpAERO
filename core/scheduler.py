"""
Scheduler for automated periodic access code rotation (every 14 days).
Runs as a background daemon or cron-compatible task.
"""
import logging
import signal
import sys
import time
from typing import Optional
import schedule

from core.rotator import PINRotator

logger = logging.getLogger(__name__)


class RotationScheduler:
    """Runs periodic checks to rotate access codes for due users."""

    def __init__(self, rotator: PINRotator, schedule_time: str = "03:00", check_interval_hours: int = 12):
        self.rotator = rotator
        self.schedule_time = schedule_time
        self.check_interval_hours = check_interval_hours
        self._running = False

    def _schedule_fast_retry(self, seconds: int = 60):
        """Schedule a one-off retry when the previous cycle failed due to network/backend error."""
        if getattr(self, "_has_pending_retry", False):
            return

        self._has_pending_retry = True

        def _retry_job():
            self._has_pending_retry = False
            logger.info("Повторная попытка проверки ротации после сбоя сети...")
            self._job_wrapper()
            return schedule.CancelJob

        schedule.every(seconds).seconds.do(_retry_job)
        logger.info("Запланирована однократная повторная проверка через %d секунд.", seconds)

    def _job_wrapper(self):
        logger.info("Scheduler triggered automatic access code rotation check...")
        try:
            report = self.rotator.rotate_all_due_users(force=False)
            logger.info(
                "Rotation cycle completed: rotated=%d, skipped=%d, failed=%d",
                report.rotated_count,
                report.skipped_count,
                report.failed_count,
            )
            if getattr(report, "backend_error", False):
                logger.warning("Проверка не смогла прочитать таблицу. Повторная попытка через 60 секунд...")
                self._schedule_fast_retry(60)
        except Exception as exc:
            logger.exception("Error during scheduled rotation job: %s", exc)
            logger.warning("Произошла ошибка при выполнении задания. Повторная попытка через 60 секунд...")
            self._schedule_fast_retry(60)

    def run_daemon(self, run_immediately: bool = True):
        """Start scheduler loop."""
        self._running = True

        def handle_signal(sig, frame):
            logger.info("Received signal %s, stopping scheduler...", sig)
            self._running = False

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

        # Schedule daily check at configured time
        if self.schedule_time:
            schedule.every().day.at(self.schedule_time).do(self._job_wrapper)
            logger.info("Scheduled daily rotation check at %s", self.schedule_time)

        # Also schedule periodic interval check (e.g. every 12 hours)
        if self.check_interval_hours and self.check_interval_hours > 0:
            schedule.every(self.check_interval_hours).hours.do(self._job_wrapper)
            logger.info("Scheduled interval rotation check every %d hours", self.check_interval_hours)

        if run_immediately:
            logger.info("Running initial rotation check on startup...")
            self._job_wrapper()

        logger.info("Scheduler daemon started. Waiting for jobs...")
        while self._running:
            schedule.run_pending()
            time.sleep(1)

        logger.info("Scheduler daemon terminated.")
