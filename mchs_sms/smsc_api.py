import json
import re
import time
from contextlib import suppress
from dataclasses import dataclass, asdict
from urllib.parse import urlencode

import asyncclick as click
import trio
import asks

import warnings
from trio import (
    TrioDeprecationWarning,
    open_memory_channel,
    MemorySendChannel,
    MemoryReceiveChannel,
)

warnings.filterwarnings(action="ignore", category=TrioDeprecationWarning)

SEND_URL = "https://smsc.ru/sys/send.php"
STATUS_URL = "https://smsc.ru/sys/status.php"
MAX_CLIENTS = 1

asks.init("trio")


@dataclass
class Credential:
    login: str
    psw: str


@dataclass
class Message:
    phones: str
    mes: str
    valid: int


@dataclass
class Status:
    phone: str
    id: str
    fmt: int = 3


async def send_message(
    credential: Credential, message: Message, send_channel: MemorySendChannel, /
):
    start = time.time()

    print(asdict(message))
    response = await asks.get(
        SEND_URL, params=urlencode({**asdict(credential), **asdict(message)})
    )
    content = response.text
    print(
        f"Статус ответа {response.status_code}, ответ {content} (выполнено за {time.time() - start})"
    )

    if response.status_code == 200:
        await send_channel.send((message.phones, content))


async def get_status(credential: Credential, receive_channel: MemoryReceiveChannel, /):
    async for (phones, content) in receive_channel:
        if (numbers := re.findall(r"\d+", content)) and len(numbers) == 2:
            sms_count = numbers[0]
            sms_id = numbers[1]
            print(f"Сообщения были отправлены на {sms_count} телефонных номеров")

            for phone in re.split(";|,", phones):
                status = Status(phone=phone, id=sms_id)
                response = await asks.get(
                    STATUS_URL, params={**asdict(credential), **asdict(status)}
                )
                content = response.json()
                print(
                    f"SMS отправлена на телефон {phone}. Статус:\n{json.dumps(content, indent=4)}"
                )
        break


def validate_phones(ctx, param, value):
    """
    Очищает строку с телефонами от 'паразитных' символов и проверяет её на содержание только цифр.
    """
    phones = value.replace("+", "").replace(" ", "")
    for phone in re.split(";|,", phones):
        if not phone.isdigit():
            raise click.BadParameter("Номера телефонов должны содержать только цифры")
    return phones


@click.command()
@click.option("--login", envvar="SMSC_LOGIN", help="Логин клиента sms-сервиса.")
@click.option("--psw", envvar="SMSC_PSW", help="Пароль клиента sms-сервиса.")
@click.option(
    "--valid",
    type=int,
    envvar="SMSC_VALID",
    default=1,
    help="Срок 'жизни' SMS-сообщения. Диапазон от 1 до 24 часов.",
)
@click.option(
    "--phones",
    required=True,
    callback=validate_phones,
    help="Номер телефона или несколько номеров через запятую или точку с запятой.",
)
@click.option("--mes", required=True, type=str, help="Текст сообщения.")
async def main(login, psw, valid, phones, mes):
    credential = Credential(
        login=login,
        psw=psw,
    )
    message = Message(valid=valid, phones=phones, mes=mes)
    send_channel, receive_channel = open_memory_channel(0)
    start = time.time()
    async with trio.open_nursery() as nursery:
        for _ in range(MAX_CLIENTS):
            nursery.start_soon(send_message, credential, message, send_channel)
            nursery.start_soon(get_status, credential, receive_channel)
    print(f"завершено за {time.time() - start}")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        results_list = trio.run(main(_anyio_backend="trio"))
        print(results_list)
