# Рассылка SMS и её отслеживание

Веб-приложение для рассылки SMS по базе номеров и отслеживания их доставки.

<img src="https://dvmn.org/filer/canonical/1581177685/497/">

## Как запустить

- Скачайте код
- Откройте в браузере файл index.

### Создать виртуальное окружение
```bash
poetry install 
```

### Создание списка рассылки
Запишите перечень номеров телефонов в формате +79998886655 (без скобок и дефисов) через точку с запятой в текстовый файл.

### Запуск сервера
```bash
export SMSC_LOGIN=devman
export SMSC_PSW=Ab6Kinhyxquot
export SMSC_VALID=1
export REDIS_URL=redis://127.0.0.1:6379/0
poetry run python mchs_sms/server.py --phones mchs_sms/phones.txt 
```

## Получение данных из формы

При нажатии кнопки "Отправить" фронтенд шлёт POST запрос на адрес `/send/`. Текст из поля для ввода будет в POST-параметре  `text`. В ответ от сервера ожидается JSON. Если в ответе будет ключ `errorMessage`, то пользователь увидит его в виде всплывающего сообщения. Пример ответа сервера с текстом ошибки:

```json
{
  "errorMessage": "Потеряно соединение с SMSC.ru"
}
```

## Формат данных для вебсокета

Через вебсокет приложение получает информацию о прогрессе рассылки: сколько адресатов уже получили SMS и сколько должны будут получить в будущем. Вебсокет работает на 5000 порту.

Фронтенд ожидает получить от сервера JSON сообщение с информацией о рассылках:

```js
{
  "msgType": "SMSMailingStatus",
  "SMSMailings": [
    {
      "timestamp": 1123131392.734,
      "SMSText": "Сегодня гроза! Будьте осторожны!",
      "mailingId": "1",
      "totalSMSAmount": 345,
      "deliveredSMSAmount": 47,
      "failedSMSAmount": 5,
    },
    {
      "timestamp": 1323141112.924422,
      "SMSText": "Новогодняя акция!!! Приходи в магазин и получи скидку!!!",
      "mailingId": "new-year",
      "totalSMSAmount": 3993,
      "deliveredSMSAmount": 801,
      "failedSMSAmount": 0,
    },
  ]
}
```

Фронтенд накапливает данные о SMS рассылках. Если у вас есть 3 SMS рассылки, а вебсокет получит обновления только по двум, то третья со страницы не пропадёт.

## Цели проекта

Код написан в учебных целях — это урок в курсе по Python и веб-разработке на сайте [Devman](https://dvmn.org).