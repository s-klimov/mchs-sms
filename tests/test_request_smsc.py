from random import randint, choice
from unittest.mock import patch

from mchs_sms.smsc_api import request_smsc, HttpMethod, SEND_URL


class MockSuccessResponse:
    """Пример успешного ответа sms-сервиса после отправки сообщений"""

    status_code = 200

    @staticmethod
    def json():
        return {"id": 430, "cnt": 2}


class MockSendStatusResponse:
    status_code = 200

    @staticmethod
    def json():
        return {
            "status": choice([randint(-3, 4), randint(20, 25)]),
            "last_date": "28.12.2019 19:20:22",
            "last_timestamp": 1577550022,
        }


async def test_success_request_smsc():
    """Тест функции request_smsc, проверяющий на выходе ответ сообщения от sms-сервиса"""
    with patch("asks.post") as mock_function:
        mock_function.return_value = MockSuccessResponse()
        expected = await mock_function()
        response = await request_smsc(
            HttpMethod.post,
            SEND_URL,
            login="test_user",
            password="test_password",
            payload={
                "phones": "79999999999",
                "mes": "Завтра ожидается гроза",
                "valid": 1,
            },
        )
    assert expected.json() == response.content
    assert expected.status_code == response.status_code
