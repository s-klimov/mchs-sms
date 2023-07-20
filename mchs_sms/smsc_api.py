import re
import time
from contextlib import suppress
from dataclasses import dataclass, asdict
from urllib.parse import urlencode

import asyncclick as click
import trio
import asks

import warnings
from trio import TrioDeprecationWarning

warnings.filterwarnings(action="ignore", category=TrioDeprecationWarning)

URL = "https://smsc.ru/sys/send.php"
MAX_CLIENTS = 1

asks.init("trio")


@dataclass
class Message:
    login: str
    psw: str
    phones: str
    mes: str
    valid: int


async def send_message(message: Message):
    start = time.time()

    print(asdict(message))
    response = await asks.get(URL, params=urlencode(asdict(message)))
    content = response.text
    print(f"{content} (выполнено за {time.time() - start})")


def validate_phones(ctx, param, value):
    """
    Очищает строку с телефонами от 'паразитных' символов и проверяет её на содержание только цифр.
    """
    phones = value.replace("+", "").replace(" ", "")
    for phone in re.split(';|,', phones):
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
    message = Message(login=login, psw=psw, valid=valid, phones=phones, mes=mes)
    start = time.time()
    async with trio.open_nursery() as nursery:
        for _ in range(MAX_CLIENTS):
            nursery.start_soon(send_message, message)
    print(f"завершено за {time.time() - start}")


if __name__ == "__main__":
    with suppress(KeyboardInterrupt):
        results_list = trio.run(main(_anyio_backend="trio"))
        print(results_list)
