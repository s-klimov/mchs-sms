from unittest.mock import patch

from trio import open_memory_channel

from mchs_sms.smsc_api import SmscResponse, send_message, Message


async def test_success_send_message():
    """Тест функции send_message проверяет результат отправки сообщения в очереди"""

    send_channel, receive_channel = open_memory_channel(0)

    with patch("mchs_sms.smsc_api.request_smsc") as mock_function:
        mock_function.return_value = SmscResponse(
            content={"id": 430, "cnt": 2000}, status_code=200
        )

        message = Message(valid=1, phones="79999999999", mes="Завтра ожидается гроза")

        await send_message(
            message, send_channel
        )  # FIXME RuntimeError: must be called from async context

        phones, content = await receive_channel.receive()

    assert phones == "79999999999"
    assert content == {"id": 430, "cnt": 2}
