/**
 * Google Apps Script (GAS) для интеграции с программой смены кодов BAS-IP.
 * Не требует Google Cloud Console, работает бесплатно в любой стране!
 *
 * Инструкция по установке:
 * 1. В вашей Google Таблице откройте меню: «Расширения» -> «Apps Script»
 * 2. Удалите стандартный код и вставьте содержимое этого файла
 * 3. Нажмите «Сохранить» (иконка дискеты или Ctrl+S)
 * 4. Нажмите синюю кнопку «Развернуть» (Deploy) -> «Новое развертывание» (New deployment)
 * 5. Нажмите на шестеренку слева от «Выберите тип» и выберите «Веб-приложение» (Web app)
 * 6. Настройки:
 *    - Описание: BAS-IP Connector
 *    - Запуск от имени: «Я (ваш@gmail.com)»
 *    - У кого есть доступ: «Все» (Anyone)
 * 7. Нажмите «Развернуть», предоставьте разрешения (если запросит)
 * 8. Скопируйте полученный URL веб-приложения (вида https://script.google.com/macros/s/.../exec)
 *    и вставьте его в config.yaml в поле web_app_url.
 */

// Опционально: можно задать секретный ключ для защиты от посторонних вызовов
var API_KEY = ""; 

function doGet(e) {
  return handleRequest(e ? e.parameter : {});
}

function doPost(e) {
  var params = {};
  if (e && e.postData && e.postData.contents) {
    try {
      params = JSON.parse(e.postData.contents);
    } catch (err) {
      params = e.parameter || {};
    }
  } else if (e && e.parameter) {
    params = e.parameter;
  }
  return handleRequest(params);
}

function handleRequest(params) {
  if (API_KEY && params.api_key !== API_KEY) {
    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: "Unauthorized: invalid api_key"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getActiveSheet();
  var action = params.action || "get_users";

  // 1. Получение списка пользователей
  if (action === "get_users") {
    var data = sheet.getDataRange().getValues();
    if (data.length <= 1) {
      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        users: []
      })).setMimeType(ContentService.MimeType.JSON);
    }

    var headers = data[0].map(function(h) {
      return String(h).trim().toLowerCase();
    });

    function findCol(aliases) {
      for (var i = 0; i < headers.length; i++) {
        for (var a = 0; a < aliases.length; a++) {
          if (headers[i] === aliases[a]) return i;
        }
      }
      return -1;
    }

    var idCol = findCol(["id", "ид", "номер", "user_id"]);
    var nameCol = findCol(["имя", "фио", "name", "fio", "пользователь"]);
    var emailCol = findCol(["email", "e-mail", "почта", "mail"]);
    var aptCol = findCol(["квартира", "офис", "apartment", "flat", "room"]);
    var houseCol = findCol(["дом", "здание", "building", "house", "д."]);
    var entranceCol = findCol(["подъезд", "секция", "entrance", "porch", "section", "п."]);
    var accessCol = findCol(["доступ", "доступ (панели)", "панели", "доступные панели", "access", "access_panels"]);
    var codeCol = findCol(["код", "код доступа", "рабочий код", "текущий код", "code", "pin"]);
    var autoCol = findCol(["автосмена", "ротация", "auto_rotate", "autorotate"]);
    var dateCol = findCol(["дата последней смены", "дата смены", "last_rotated", "last_change"]);
    var intervalCol = findCol(["интервал (дней)", "период (дней)", "интервал", "interval"]);
    var statusCol = findCol(["статус", "status"]);

    var users = [];
    for (var r = 1; r < data.length; r++) {
      var row = data[r];
      if (!row || row.every(function(cell) { return cell === ""; })) continue;

      var name = nameCol >= 0 ? String(row[nameCol] || "") : "";
      var email = emailCol >= 0 ? String(row[emailCol] || "") : "";
      if (!name && !email) continue;

      var dateVal = "";
      if (dateCol >= 0 && row[dateCol]) {
        if (row[dateCol] instanceof Date) {
          dateVal = Utilities.formatDate(row[dateCol], Session.getScriptTimeZone() || "GMT+3", "yyyy-MM-dd HH:mm:ss");
        } else {
          dateVal = String(row[dateCol]);
        }
      }

      users.push({
        row_index: r + 1,
        id: idCol >= 0 && row[idCol] ? String(row[idCol]) : ("user_" + (r + 1)),
        name: name,
        email: email,
        apartment: aptCol >= 0 ? String(row[aptCol] || "") : "",
        house: houseCol >= 0 ? String(row[houseCol] || "") : "",
        entrance: entranceCol >= 0 ? String(row[entranceCol] || "") : "",
        access_panels: accessCol >= 0 ? String(row[accessCol] || "") : "",
        code: codeCol >= 0 ? String(row[codeCol] || "") : "",
        auto_rotate: autoCol >= 0 ? String(row[autoCol] || "Да") : "Да",
        last_rotated: dateVal,
        interval_days: intervalCol >= 0 && row[intervalCol] ? Number(row[intervalCol]) : 14,
        status: statusCol >= 0 ? String(row[statusCol] || "") : ""
      });
    }

    return ContentService.createTextOutput(JSON.stringify({
      success: true,
      users: users
    })).setMimeType(ContentService.MimeType.JSON);
  }

  // 2. Обновление кода доступа
  if (action === "update_code") {
    var data = sheet.getDataRange().getValues();
    var headers = data[0].map(function(h) {
      return String(h).trim().toLowerCase();
    });

    function findCol(aliases) {
      for (var i = 0; i < headers.length; i++) {
        for (var a = 0; a < aliases.length; a++) {
          if (headers[i] === aliases[a]) return i + 1; // 1-based index
        }
      }
      return -1;
    }

    var idCol = findCol(["id", "ид", "номер", "user_id"]);
    var nameCol = findCol(["имя", "фио", "name", "fio", "пользователь"]);
    var codeCol = findCol(["код", "код доступа", "рабочий код", "текущий код", "code", "pin"]);
    var dateCol = findCol(["дата последней смены", "дата смены", "last_rotated", "last_change"]);
    var statusCol = findCol(["статус", "status"]);

    var targetId = String(params.user_id || "");
    var targetName = String(params.name || "").trim().toLowerCase();
    var newCode = String(params.code || "");
    var newStatus = String(params.status || "Успешно обновлен");
    var dateStr = params.timestamp || Utilities.formatDate(new Date(), Session.getScriptTimeZone() || "GMT+3", "yyyy-MM-dd HH:mm:ss");

    var targetRow = -1;
    for (var r = 1; r < data.length; r++) {
      var rowId = idCol > 0 ? String(data[r][idCol - 1]) : "";
      var rowName = nameCol > 0 ? String(data[r][nameCol - 1]).trim().toLowerCase() : "";

      if ((targetId && rowId === targetId) || (targetName && rowName === targetName)) {
        targetRow = r + 1;
        break;
      }
    }

    if (targetRow > 0) {
      if (codeCol > 0) sheet.getRange(targetRow, codeCol).setValue(newCode);
      if (dateCol > 0) sheet.getRange(targetRow, dateCol).setValue(dateStr);
      if (statusCol > 0) sheet.getRange(targetRow, statusCol).setValue(newStatus);

      // Отправка письма прямо из Google Почты аккаунта
      var emailSent = false;
      var recipientEmail = params.email;
      if (params.send_email && recipientEmail) {
        try {
          var subject = "Смена кода доступа домофона";
          var body = 'Добрый день, ваш код доступа изменен на "' + newCode + '"';
          GmailApp.sendEmail(recipientEmail, subject, body);
          emailSent = true;
        } catch (mailErr) {
          // Лог ошибки почты
        }
      }

      return ContentService.createTextOutput(JSON.stringify({
        success: true,
        row: targetRow,
        code: newCode,
        email_sent: emailSent
      })).setMimeType(ContentService.MimeType.JSON);
    }

    return ContentService.createTextOutput(JSON.stringify({
      success: false,
      error: "Пользователь не найден в таблице (ID: " + targetId + ", Имя: " + targetName + ")"
    })).setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({
    success: false,
    error: "Неизвестное действие: " + action
  })).setMimeType(ContentService.MimeType.JSON);
}
