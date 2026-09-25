"""
Access Code Rotator for BAS-IP AA-14FB.
Handles secure PIN generation, rotation rule checks (every 14 days),
panel API synchronization, Google Sheets updates, and email notifications.
"""
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Set, Dict, Any

from basip.client import BASIPManager
from basip.models import AccessCodeUser
from core.config import RotationConfig
from google_services.mailer import BaseMailer
from google_services.sheets import BaseSheetsBackend

logger = logging.getLogger(__name__)


def is_trivial_pin(code: str) -> bool:
    """Check if PIN code is trivial/predictable (e.g. 111111, 123456, 654321)."""
    # All same digits (e.g. 000000, 111111)
    if len(set(code)) == 1:
        return True

    # Sequential ascending (e.g. 123456, 234567, 012345)
    digits = [int(c) for c in code]
    if all(digits[i] + 1 == digits[i + 1] for i in range(len(digits) - 1)):
        return True

    # Sequential descending (e.g. 654321, 543210)
    if all(digits[i] - 1 == digits[i + 1] for i in range(len(digits) - 1)):
        return True

    return False


def generate_secure_pin(
    length: int = 6,
    avoid_trivial: bool = True,
    existing_codes: Optional[Set[str]] = None,
    max_attempts: int = 1000,
) -> str:
    """
    Generate a cryptographically secure random numeric PIN code.
    Ensures length, uniqueness against existing active codes, and non-triviality.
    """
    existing = existing_codes or set()
    for _ in range(max_attempts):
        # Generate random digits
        pin = "".join(secrets.choice("0123456789") for _ in range(length))
        if avoid_trivial and is_trivial_pin(pin):
            continue
        if pin in existing:
            continue
        return pin

    # Fallback if max attempts exceeded
    return "".join(secrets.choice("0123456789") for _ in range(length))


@dataclass
class UserRotationResult:
    user_id: str
    name: str
    email: str
    old_code: str
    new_code: str
    success: bool
    email_sent: bool
    message: str


@dataclass
class RotationReport:
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_users_checked: int = 0
    rotated_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    backend_error: bool = False
    results: List[UserRotationResult] = field(default_factory=list)


class PINRotator:
    """Orchestrates access code rotation across BAS-IP, Google Sheets, and Gmail."""

    def __init__(
        self,
        basip_manager: BASIPManager,
        sheets_backend: BaseSheetsBackend,
        mailer: BaseMailer,
        config: RotationConfig,
    ):
        self.basip_manager = basip_manager
        self.sheets_backend = sheets_backend
        self.mailer = mailer
        self.config = config

    def rotate_all_due_users(
        self,
        force: bool = False,
        target_user_ids: Optional[List[str]] = None,
        dry_run: Optional[bool] = None,
    ) -> RotationReport:
        """
        Main execution flow:
        1. Reads users from Google Sheets.
        2. Determines who is due for 14-day rotation (or forced).
        3. Generates new unique PIN code.
        4. Updates BAS-IP AA-14FB panel(s) via local API.
        5. Updates Google Sheet with new working code and timestamp.
        6. Sends notification email to user via Gmail:
           'Добрый день, ваш код доступа изменен на "{new_code}"'
        """
        is_dry_run = self.config.dry_run if dry_run is None else dry_run
        report = RotationReport(started_at=datetime.now())

        logger.info("Fetching users from storage backend...")
        try:
            users = self.sheets_backend.get_users()
        except Exception as e:
            logger.error("Failed to read users from backend: %s", e)
            report.finished_at = datetime.now()
            report.backend_error = True
            return report

        report.total_users_checked = len(users)
        logger.info("Found %d total users in sheet.", len(users))

        # Collect existing codes to guarantee uniqueness
        existing_codes: Set[str] = {u.current_code for u in users if u.current_code}

        now = datetime.now()

        for user in users:
            # Check target filter if provided (matches ID, row number, or user name)
            if target_user_ids:
                matches_target = (
                    user.user_id in target_user_ids
                    or str(user.row_index) in target_user_ids
                    or any(t.lower() in user.name.lower() for t in target_user_ids)
                )
                if not matches_target:
                    report.skipped_count += 1
                    continue

            # Check if user is eligible for rotation
            if not force and not user.is_due_for_rotation(now):
                logger.debug(
                    "User '%s' (ID: %s) is not due for rotation yet (last rotated: %s, interval: %d days).",
                    user.name,
                    user.user_id,
                    user.last_rotated,
                    user.interval_days,
                )
                report.skipped_count += 1
                continue

            if not user.auto_rotate and not force:
                logger.debug("User '%s' has auto_rotate disabled.", user.name)
                report.skipped_count += 1
                continue

            # Generate new unique PIN
            new_code = generate_secure_pin(
                length=self.config.code_length,
                avoid_trivial=self.config.avoid_trivial_codes,
                existing_codes=existing_codes,
            )
            existing_codes.add(new_code)

            old_code = user.current_code
            logger.info(
                "Rotating access code for '%s' (%s): [Old: %s -> New: %s] (DryRun=%s)",
                user.name,
                user.email,
                old_code or "<none>",
                new_code,
                is_dry_run,
            )

            if is_dry_run:
                report.rotated_count += 1
                report.results.append(
                    UserRotationResult(
                        user_id=user.user_id,
                        name=user.name,
                        email=user.email,
                        old_code=old_code,
                        new_code=new_code,
                        success=True,
                        email_sent=False,
                        message=f"[DRY-RUN] Would update BAS-IP, Sheet, and send email: 'Добрый день, ваш код доступа изменен на \"{new_code}\"'",
                    )
                )
                continue

            # 1. Update BAS-IP panel(s) locally (only panels matching user permissions + gates)
            panel_results = self.basip_manager.sync_user_code(
                name=user.name,
                new_code=new_code,
                old_code=old_code,
                user=user,
            )

            failed_panels = []
            succeeded_panels = []
            failed_details = []

            for p, res in panel_results.items():
                if isinstance(res, tuple):
                    ok, detail = res
                else:
                    ok, detail = res, ""
                if ok:
                    succeeded_panels.append(p)
                else:
                    failed_panels.append(p)
                    if detail:
                        failed_details.append(f"{p} ({detail})")

            if not panel_results:
                logger.warning("No target panels found or configured for user '%s'", user.name)
            elif failed_panels and not succeeded_panels:
                detail_summary = "; ".join(failed_details) if failed_details else ", ".join(failed_panels)
                err_msg = f"Failed to update BAS-IP panels: {detail_summary}"
                logger.error("User '%s': %s", user.name, err_msg)
                report.failed_count += 1
                report.results.append(
                    UserRotationResult(
                        user_id=user.user_id,
                        name=user.name,
                        email=user.email,
                        old_code=old_code,
                        new_code=new_code,
                        success=False,
                        email_sent=False,
                        message=err_msg,
                    )
                )
                self.sheets_backend.update_user_code(
                    user=user,
                    new_code=old_code,
                    status=f"Ошибка домофона: {', '.join(failed_panels[:2])}",
                )
                continue

            # 2. Update Google Sheet with new code & timestamp
            status_note = f"Обновлен ({len(succeeded_panels)} пан.)"
            if failed_panels:
                status_note += f" (Ошибки: {len(failed_panels)})"

            try:
                self.sheets_backend.update_user_code(
                    user=user,
                    new_code=new_code,
                    rotation_time=now,
                    status=status_note,
                )
            except Exception as exc:
                logger.error("Failed to update Google Sheet for user '%s': %s", user.name, exc)
                # Keep going to attempt sending mail or log

            # 3. Send email to user via Google Mail
            email_sent = False
            try:
                email_sent = self.mailer.send_access_code_email(
                    to_email=user.email,
                    new_code=new_code,
                    user_name=user.name,
                )
                if not email_sent:
                    logger.warning("Mail sending returned false for '%s' (%s)", user.name, user.email)
            except Exception as exc:
                logger.error("Failed sending email to '%s' (%s): %s", user.name, user.email, exc)

            report.rotated_count += 1
            report.results.append(
                UserRotationResult(
                    user_id=user.user_id,
                    name=user.name,
                    email=user.email,
                    old_code=old_code,
                    new_code=new_code,
                    success=True,
                    email_sent=email_sent,
                    message=f"Код изменен на '{new_code}', письмо {'отправлено' if email_sent else 'ошибка отправки'}",
                )
            )

        report.finished_at = datetime.now()
        logger.info(
            "Rotation finished: checked=%d, rotated=%d, skipped=%d, failed=%d",
            report.total_users_checked,
            report.rotated_count,
            report.skipped_count,
            report.failed_count,
        )
        return report
