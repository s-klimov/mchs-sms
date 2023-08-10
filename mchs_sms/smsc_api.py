"""Консольный скрипт отправки sms-сообщений через сервис smsc.ru"""

import json
import re
import time
from contextlib import suppress
from contextvars import ContextVar
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional, NamedTuple, Mapping
from urllib.parse import urlencode, urljoin

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

SMSC_HOST = "https://smsc.ru"
SEND_URL = "rest/send/"
STATUS_URL = "sys/status.php"
MAX_CLIENTS = 1

asks.init("trio")


smsc_login: ContextVar[str] = ContextVar("smsc_login")
smsc_password: ContextVar[str] = ContextVar("smsc_password")


class HttpMethod(str, Enum):
    """Список используемых http-методов"""

    get = "get"
    post = "post"


class SmscResponse(NamedTuple):
    """Ответ сервиса по отправке sms-сообщений"""

    content: Mapping
    status_code: int


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


async def request_smsc(
    http_method: HttpMethod,
    api_method: str,
    *,
    login: Optional[str] = None,
    password: Optional[str] = None,
    payload: dict = {},
) -> SmscResponse:
    payload["login"] = login or smsc_login.get()
    payload["psw"] = password or smsc_password.get()

    if http_method.value == "get":
        param_key = "params"
        param_value = urlencode(payload)
    else:
        param_key = "json"
        param_value = payload

    response = await getattr(asks, http_method.value)(
        urljoin(SMSC_HOST, api_method), **{param_key: param_value}
    )

    return SmscResponse(content=response.json(), status_code=response.status_code)


class SmscApiError(Exception):
    pass


async def send_message(message: Message, send_channel: MemorySendChannel, /):
    start = time.time()

    print(asdict(message))
    response = await request_smsc(HttpMethod.post, SEND_URL, payload=asdict(message))
    print(
        f"Статус ответа {response.status_code}, ответ {response.content} (выполнено за {time.time() - start})"
    )

    if response.status_code == 200 and response.content.get("error_code", 0) == 0:
        await send_channel.send((message.phones, response.content))
    else:
        raise SmscApiError(
            "Ошибка отправки sms: ошибка %s, код ошибки %d, статус ответа %d"
            % (
                response.content.get("error"),
                response.content.get("error_code"),
                response.status_code,
            )
        )


async def get_status(receive_channel: MemoryReceiveChannel, /):
    async with receive_channel:
        phones, content = await receive_channel.receive()

        sms_id = content["id"]
        print(f"Сообщения были отправлены на {content['cnt']} телефонных номеров")

        for phone in re.split(";|,", phones):
            status = Status(phone=phone, id=sms_id)
            response = await request_smsc(
                HttpMethod.get, STATUS_URL, payload=asdict(status)
            )
            print(
                f"SMS отправлена на телефон {phone}. Статус:\n{json.dumps(response.content, indent=4)}"
            )


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
    smsc_login.set(login)
    smsc_password.set(psw)

    message = Message(valid=valid, phones=phones, mes=mes)
    send_channel, receive_channel = open_memory_channel(0)
    start = time.time()
    async with trio.open_nursery() as nursery:
        for _ in range(MAX_CLIENTS):
            nursery.start_soon(send_message, message, send_channel)
            nursery.start_soon(get_status, receive_channel)
    print(f"завершено за {time.time() - start}")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        results_list = trio.run(main(_anyio_backend="trio"))
        print(results_list)
