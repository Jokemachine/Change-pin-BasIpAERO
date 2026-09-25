"""
Command Line Interface for BAS-IP AA-14FB Access Code Rotator.
"""
import argparse
import logging
import os
import sys
from datetime import datetime

from basip.client import BASIPManager, BASIPClient
from basip.mock_panel import MockBASIPServer
from basip.models import BASIPPanelConfig
from core.config import AppConfig, load_config
from core.rotator import PINRotator
from core.scheduler import RotationScheduler
from google_services.mailer import GmailSMTPMailer, MockMailer, BaseMailer
from google_services.sheets import (
    GoogleSheetsService,
    LocalCSVSheetsBackend,
    GoogleAppsScriptBackend,
    AppSheetBackend,
    BaseSheetsBackend,
)

logger = logging.getLogger("basip_rotator")


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [handler]


def create_components(config: AppConfig, mock_panel_server: bool = False):
    """Factory creating all necessary services based on config."""
    # 1. BAS-IP panel manager
    if config.use_mock_panel or mock_panel_server:
        logger.info("Using built-in Mock BAS-IP AA-14FB server on port %d", config.mock_panel_port)
        mock_server = MockBASIPServer(port=config.mock_panel_port)
        mock_server.start()
        # Create mock configurations for all panels pointing to local mock server
        mock_panels = []
        for p in config.panels:
            mock_panels.append(
                BASIPPanelConfig(
                    panel_id=p.panel_id,
                    name=p.name,
                    building=p.building,
                    entrance=p.entrance,
                    door=p.door,
                    is_gate=p.is_gate,
                    enabled=p.enabled,
                    host="127.0.0.1",
                    port=config.mock_panel_port,
                    username="admin",
                    password="123456",
                )
            )
        manager = BASIPManager(mock_panels)
    else:
        mock_server = None
        manager = BASIPManager(config.panels)

    # 2. Sheets backend
    b_type = config.sheets.backend_type.lower()
    if b_type == "google_apps_script":
        if config.sheets.gas_web_app_url:
            sheets_backend = GoogleAppsScriptBackend(
                web_app_url=config.sheets.gas_web_app_url,
                api_key=config.sheets.gas_api_key,
                worksheet_name=config.sheets.worksheet_name or "Временные коды",
            )
        else:
            logger.warning(
                "google_apps_script backend selected but gas_web_app_url is empty! "
                "Deploy google_apps_script/Code.gs in your Google Sheet and set gas_web_app_url in config.yaml. "
                "Using local CSV '%s' for now.",
                config.sheets.csv_fallback_path,
            )
            sheets_backend = LocalCSVSheetsBackend(config.sheets.csv_fallback_path)
    elif b_type == "appsheet":
        if config.sheets.appsheet_app_id and config.sheets.appsheet_access_key:
            sheets_backend = AppSheetBackend(
                app_id=config.sheets.appsheet_app_id,
                access_key=config.sheets.appsheet_access_key,
                table_name=config.sheets.appsheet_table_name,
            )
        else:
            logger.warning(
                "appsheet backend selected but appsheet_app_id/access_key is empty! Using local CSV '%s'.",
                config.sheets.csv_fallback_path,
            )
            sheets_backend = LocalCSVSheetsBackend(config.sheets.csv_fallback_path)
    elif b_type == "google_sheets":
        if os.path.exists(config.sheets.credentials_json):
            try:
                sheets_backend = GoogleSheetsService(
                    credentials_file=config.sheets.credentials_json,
                    spreadsheet_id_or_title=config.sheets.spreadsheet_id_or_title,
                    worksheet_name=config.sheets.worksheet_name,
                )
            except Exception as e:
                logger.warning(
                    "Could not initialize Google Sheets (%s). Falling back to local CSV '%s'",
                    e,
                    config.sheets.csv_fallback_path,
                )
                sheets_backend = LocalCSVSheetsBackend(config.sheets.csv_fallback_path)
        else:
            logger.warning(
                "Google service account '%s' not found. Using local CSV '%s'. (Tip: use backend_type='google_apps_script' if you don't have Google Cloud Console!)",
                config.sheets.credentials_json,
                config.sheets.csv_fallback_path,
            )
            sheets_backend = LocalCSVSheetsBackend(config.sheets.csv_fallback_path)
    else:
        sheets_backend = LocalCSVSheetsBackend(config.sheets.csv_fallback_path)

    # 3. Mailer backend
    if config.gmail.mock_email or not (config.gmail.user and config.gmail.app_password):
        if not (config.gmail.user and config.gmail.app_password):
            logger.info("Gmail credentials not fully provided; using MockMailer (logs emails to console).")
        mailer = MockMailer(print_to_console=True)
    else:
        mailer = GmailSMTPMailer(
            gmail_user=config.gmail.user,
            gmail_app_password=config.gmail.app_password,
            from_name=config.gmail.from_name,
            subject=config.gmail.subject,
            smtp_host=config.gmail.smtp_host,
            smtp_port=config.gmail.smtp_port,
            use_ssl=config.gmail.use_ssl,
        )

    # 4. Rotator
    rotator = PINRotator(
        basip_manager=manager,
        sheets_backend=sheets_backend,
        mailer=mailer,
        config=config.rotation,
    )

    return manager, sheets_backend, mailer, rotator, mock_server


def cmd_run(args, config: AppConfig):
    """Execute code rotation once."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config, mock_panel_server=args.mock_panel)
    try:
        target_ids = [args.user] if args.user else None
        dry_run = args.dry_run if args.dry_run else None

        print("\n=======================================================")
        print(f"Запуск ротации кодов доступа BAS-IP AA14FB")
        print(f"Режим: {'DRY-RUN (тестовый, без изменений)' if (dry_run or config.rotation.dry_run) else 'БОЕВОЙ'}")
        print(f"Принудительно (force): {args.force}")
        print(f"Целевой пользователь: {args.user or 'Все у кого подошел срок (раз в 14 дней)'}")
        print("=======================================================\n")

        report = rotator.rotate_all_due_users(
            force=args.force,
            target_user_ids=target_ids,
            dry_run=dry_run,
        )

        print("\n---------------- ИТОГИ РОТАЦИИ ----------------")
        print(f"Всего пользователей в таблице: {report.total_users_checked}")
        print(f"Успешно изменено кодов:        {report.rotated_count}")
        print(f"Пропущено (срок не подошел):   {report.skipped_count}")
        print(f"Ошибок:                        {report.failed_count}")
        print("------------------------------------------------\n")

        if report.results:
            for r in report.results:
                status_icon = "✓" if r.success else "✗"
                mail_icon = "✉" if r.email_sent else "-"
                print(f"[{status_icon}] {r.name} ({r.email}): {r.old_code or '<нет>'} -> {r.new_code} | Письмо: {mail_icon} | {r.message}")
        print()
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_daemon(args, config: AppConfig):
    """Run continuously as a service/daemon."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config, mock_panel_server=args.mock_panel)
    try:
        scheduler = RotationScheduler(
            rotator=rotator,
            schedule_time=config.rotation.schedule_time,
            check_interval_hours=config.rotation.check_interval_hours,
        )
        print("\n[ЗАПУСК СЛУЖБЫ АВТОМАТИЧЕСКОЙ СМЕНЫ КОДОВ]")
        print(f"Проверка раз в {config.rotation.check_interval_hours} ч., время ежедневной проверки: {config.rotation.schedule_time}")
        print("Служба активна (для остановки нажмите Ctrl+C)...")
        scheduler.run_daemon(run_immediately=not args.no_initial_run)
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_test_panel(args, config: AppConfig):
    """Check connectivity to BAS-IP AA-14FB panels."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config, mock_panel_server=args.mock_panel)
    try:
        print("\n--- Проверка подключения к панелям BAS-IP AA14FB ---")
        results = manager.test_all_connections()
        available_count = 0
        for panel, res in results.items():
            if isinstance(res, tuple):
                ok, reason = res
            else:
                ok, reason = res, ""
            if ok:
                available_count += 1
                status = "ДОСТУПНА И АВТОРИЗОВАНА"
            else:
                status = f"ОШИБКА ПОДКЛЮЧЕНИЯ -> {reason}"
            print(f"[{'✓' if ok else '✗'}] {panel}: {status}")

        print(f"\nИтого доступно панелей: {available_count} из {len(results)}")
        if available_count == 0:
            print("\nВНИМАНИЕ: Ни одна панель не ответила! Возможные причины:")
            print("1. Компьютер не находится в локальной подсети 172.39.x.x (проверьте IP вашего ПК: ipconfig).")
            print("2. Кабель не подключен к коммутатору домофонов или отключено питание панелей.")
            print("3. Брандмауэр блокирует обращение к подсети 172.39.x.x.\n")

        has_any_ok = any(res[0] if isinstance(res, tuple) else res for res in results.values())
        if has_any_ok:
            # Display current identifiers from first responding panel
            for pid, client in manager.clients.items():
                try:
                    identifiers = client.get_identifiers(limit=5)
                    print(f"\nПример существующих идентификаторов в памяти панели {pid} ({client.config.host}:{client.config.port}):")
                    if not identifiers:
                        print(" - В памяти панели пока нет созданных идентификаторов")
                    for i in identifiers:
                        print(f" - UID: {i.item_uid}, Имя: '{i.name}', Тип: '{i.identifier_type}', Код: '{i.identifier_number}'")
                    break
                except Exception as e:
                    continue
        print()
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_inspect_panel(args, config: AppConfig):
    """Deep inspection of a specific BAS-IP AA-14FB panel's API endpoints."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config, mock_panel_server=args.mock_panel)
    try:
        panel_id = args.panel or "gate_1"
        if panel_id not in manager.clients:
            panel_id = list(manager.clients.keys())[0]

        client = manager.clients[panel_id]
        print(f"\n=======================================================")
        print(f"ГЛУБОКАЯ ДИАГНОСТИКА ПАНЕЛИ: {panel_id}")
        print(f"Адрес: {client.config.host}:{client.config.port}")
        print(f"Расположение: {client.config.location_str}")
        print(f"=======================================================\n")

        print("[1] Авторизация и информация об устройстве (/api/info):")
        try:
            client.login()
            resp = client._request("GET", "/api/info")
            print(f" -> Статус: HTTP {resp.status_code}")
            if resp.status_code == 200:
                print(f" -> Ответ: {resp.text}")
        except Exception as e:
            print(f" -> Ошибка: {e}")

        print("\n[2] Список ВСЕХ идентификаторов в памяти панели:")
        try:
            identifiers = client.get_identifiers(limit=50)
            print(f" -> Всего найдено записей: {len(identifiers)}")
            for idx, ident in enumerate(identifiers, 1):
                print(f"    #{idx}: UID={ident.item_uid} | Имя='{ident.name}' | Тип={ident.identifier_type} | Код='{ident.identifier_number}'")
                if ident.raw_data:
                    import json
                    print(f"         RAW: {json.dumps(ident.raw_data, ensure_ascii=False)}")
            if not identifiers:
                print(" -> Проверка эндпоинтов получения списка:")
                for ep, params in [
                    ("/access/identifiers/items/list", {"page_number": 1, "limit": 50}),
                    ("/access/identifiers/items/list", {}),
                    ("/access/identifier/items", {"current_page": 1, "items_limit": 50}),
                    ("/access/identifier/items", {}),
                ]:
                    try:
                        resp = client._request("GET", ep, params=params)
                        print(f"    {ep}: HTTP {resp.status_code} | {resp.text[:120]}")
                    except Exception as ex:
                        print(f"    {ep}: Ошибка {ex}")
        except Exception as e:
            print(f" -> Ошибка получения списка: {e}")

        if args.test_pin:
            print("\n[3] Тестовое создание и удаление PIN-кода '998877'...")
            try:
                ident = client.create_identifier(code="998877", name="Тестовый Доступ")
                print(f" -> УСПЕХ: Код создан! UID={ident.item_uid}, Тип={ident.identifier_type}")
                if ident.item_uid:
                    del_ok = client.delete_identifier(ident.item_uid)
                    print(f" -> Тестовый код успешно удален из памяти панели: {del_ok}")
            except Exception as e:
                print(f" -> Ошибка создания: {e}")

        print("\nДиагностика завершена.\n")
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_cleanup_codes(args, config: AppConfig):
    """Purge stale/duplicate access codes for a specific user or code from panels."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config, mock_panel_server=args.mock_panel)
    try:
        user_name = args.user
        code = args.code
        uid = getattr(args, "uid", None)
        if not user_name and not code and not uid:
            print("Укажите имя пользователя (--user 'Имя'), код (--code '123456') или UID (--uid 1)")
            return

        if uid:
            print(f"\n--- Принудительное удаление идентификатора UID={uid} на всех панелях ---")
            for pid, client in manager.clients.items():
                ok = client.delete_identifier(uid)
                print(f"[{pid}]: {'Удален' if ok else 'Не найден или ошибка'}")
            print()
            return

        print(f"\n--- Очистка кодов доступа: Пользователь='{user_name or 'Все'}', Код='{code or 'Все'}' ---")
        results = manager.cleanup_user_codes_everywhere(name=user_name, code=code)
        total_deleted = sum(results.values())
        for panel, count in results.items():
            if count > 0:
                print(f"[{panel}]: Удалено {count} старых кодов")
            else:
                print(f"[{panel}]: Нет подходящих кодов для удаления")
        print(f"\nИтого удалено кодов: {total_deleted}\n")
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_list_panels(args, config: AppConfig):
    """List all configured panels with their location and parameters."""
    print("\n--- СПИСОК ВЫЗЫВНЫХ ПАНЕЛЕЙ BAS-IP AA14FB (ВСЕГО 38 ПАНЕЛЕЙ) ---")
    print(f"{'ID':<12} {'Название / Расположение':<42} {'IP-Адрес:Порт':<22} {'Тип':<12}")
    print("-" * 92)

    gates = [p for p in config.panels if p.is_gate]
    houses = {}
    for p in config.panels:
        if not p.is_gate and p.building:
            houses.setdefault(p.building, []).append(p)

    print(f"\n[КАЛИТКИ ОБЩЕГО ДОСТУПА] (Доступны ВСЕМ жильцам): {len(gates)} шт.")
    for p in gates:
        print(f"{p.panel_id:<12} {p.name:<42} {p.host + ':' + str(p.port):<22} {'Калитка':<12}")

    for h_num in sorted(houses.keys()):
        h_panels = houses[h_num]
        print(f"\n[ДОМ {h_num}] ({len(h_panels)} панелей / {len(h_panels)//2} двойных подъезда):")
        for p in h_panels:
            door_desc = f"Подъезд {p.entrance}, Дверь {p.door}"
            print(f"{p.panel_id:<12} {p.name:<42} {p.host + ':' + str(p.port):<22} {door_desc:<12}")

    print(f"\nИТОГО НАСТРОЕНО ПАНЕЛЕЙ: {len(config.panels)} шт.\n")


def cmd_test_sheets(args, config: AppConfig):
    """List users loaded from Google Sheets / CSV with their assigned panels."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config)
    try:
        print(f"\n--- Чтение пользователей из источника: {config.sheets.backend_type} ---")
        users = sheets.get_users()
        print(f"Загружено пользователей: {len(users)}\n")
        print(f"{'ID':<6} {'Имя':<24} {'Email':<24} {'Дом/Подъезд':<14} {'Доступ к панелям':<24} {'Срок'}")
        print("-" * 105)
        now = datetime.now()
        for u in users:
            due = "ДА (пора)" if u.is_due_for_rotation(now) else "НЕТ"
            target_panels = manager.get_target_panels_for_user(u)
            loc = f"Д:{u.house or '-'} П:{u.entrance or '-'}"
            panel_desc = f"{len(target_panels)} пан. (вкл. калитки)"
            print(f"{u.user_id:<6} {u.name:<24} {u.email:<24} {loc:<14} {panel_desc:<24} {due}")
        print()
    finally:
        if mock_srv:
            mock_srv.stop()


def cmd_test_email(args, config: AppConfig):
    """Send test email via Gmail."""
    manager, sheets, mailer, rotator, mock_srv = create_components(config)
    try:
        to_email = args.to or config.gmail.user
        if not to_email:
            print("Ошибка: укажите получателя через --to recipient@example.com")
            return

        test_code = "739154"
        print(f"\nОтправка тестового письма на {to_email}...")
        print(f"Текст письма: 'Добрый день, ваш код доступа изменен на \"{test_code}\"'")
        ok = mailer.send_access_code_email(to_email=to_email, new_code=test_code, user_name="Тестовый Пользователь")
        if ok:
            print("Успех: письмо успешно отправлено!")
        else:
            print("Ошибка: отправка письма не удалась. Проверьте настройки Gmail (логин, пароль приложения).")
        print()
    finally:
        if mock_srv:
            mock_srv.stop()


def main():
    parser = argparse.ArgumentParser(
        description="Автоматическая смена кодов доступа для домофонов BAS-IP AA14FB с интеграцией с Google Sheets и Gmail"
    )
    parser.add_argument("-c", "--config", default="config.yaml", help="Путь к файлу конфигурации (по умолчанию config.yaml)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Подробный вывод (DEBUG уровень)")
    parser.add_argument("--mock-panel", action="store_true", help="Запустить встроенный эмулятор панели BAS-IP для тестирования")

    subparsers = parser.add_subparsers(dest="command", help="Команда для выполнения")

    # Command: run
    run_parser = subparsers.add_parser("run", help="Выполнить проверку и смену кодов")
    run_parser.add_argument("--force", action="store_true", help="Принудительно сменить коды всем пользователям с автосменой")
    run_parser.add_argument("--user", help="Сменить код только для определенного ID пользователя")
    run_parser.add_argument("--dry-run", action="store_true", help="Тестовый запуск без реальных изменений")
    run_parser.add_argument("--mock-panel", action="store_true", help="Использовать mock BAS-IP")

    # Command: daemon
    daemon_parser = subparsers.add_parser("daemon", help="Запустить фоновый процесс (планировщик)")
    daemon_parser.add_argument("--no-initial-run", action="store_true", help="Не запускать смену сразу при старте службы")
    daemon_parser.add_argument("--mock-panel", action="store_true", help="Использовать mock BAS-IP")

    # Command: test-panel
    test_panel_parser = subparsers.add_parser("test-panel", help="Проверить связь с домофоном BAS-IP")
    test_panel_parser.add_argument("--mock-panel", action="store_true", help="Использовать mock BAS-IP")

    # Command: inspect-panel
    inspect_parser = subparsers.add_parser("inspect-panel", help="Подробная диагностика API выбранной панели")
    inspect_parser.add_argument("--panel", default="gate_1", help="ID панели для диагностики (по умолчанию gate_1)")
    inspect_parser.add_argument("--test-pin", action="store_true", help="Попробовать создать и удалить тестовый PIN 998877")
    inspect_parser.add_argument("--mock-panel", action="store_true", help="Использовать mock BAS-IP")

    # Command: cleanup-codes
    cleanup_parser = subparsers.add_parser("cleanup-codes", help="Удалить устаревшие/дублирующиеся коды доступа с панелей")
    cleanup_parser.add_argument("--user", help="Имя пользователя для очистки кодов (например, 'Тест')")
    cleanup_parser.add_argument("--code", help="Конкретный код доступа для удаления")
    cleanup_parser.add_argument("--uid", help="UID конкретного идентификатора для принудительного удаления")
    cleanup_parser.add_argument("--mock-panel", action="store_true", help="Использовать mock BAS-IP")

    # Command: list-panels
    subparsers.add_parser("list-panels", help="Вывести список всех 38 панелей домофонов и их расположение")

    # Command: test-sheets
    subparsers.add_parser("test-sheets", help="Проверить чтение Google Таблицы / CSV")

    # Command: test-email
    test_email_parser = subparsers.add_parser("test-email", help="Отправить тестовое письмо на почту")
    test_email_parser.add_argument("--to", help="Адрес получателя тестового письма")

    args = parser.parse_args()
    setup_logging(args.verbose)

    config = load_config(args.config)

    if args.command == "run" or args.command is None:
        if args.command is None:
            # Default behavior when run with no arguments
            class DefaultArgs:
                force = False
                user = None
                dry_run = False
                mock_panel = args.mock_panel
            cmd_run(DefaultArgs(), config)
        else:
            cmd_run(args, config)
    elif args.command == "daemon":
        cmd_daemon(args, config)
    elif args.command == "list-panels":
        cmd_list_panels(args, config)
    elif args.command == "test-panel":
        cmd_test_panel(args, config)
    elif args.command == "inspect-panel":
        cmd_inspect_panel(args, config)
    elif args.command == "cleanup-codes":
        cmd_cleanup_codes(args, config)
    elif args.command == "test-sheets":
        cmd_test_sheets(args, config)
    elif args.command == "test-email":
        cmd_test_email(args, config)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
