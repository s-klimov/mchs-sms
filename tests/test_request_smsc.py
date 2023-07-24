from unittest.mock import patch

from trio import open_memory_channel

from mchs_sms.smsc_api import SmscResponse, send_message, Message


async def test_send_message():
    with patch("mchs_sms.smsc_api.request_smsc") as mock_function:
        expected = SmscResponse(content={"cnt": 2, "id": 430}, status_code=200)
        mock_function.return_value = expected

        send_channel, receive_channel = open_memory_channel(0)

        await send_message(
            Message(valid=1, phones="+7952", mes="Завтра ожидается гроза"),
            send_channel,
        )

    assert True
