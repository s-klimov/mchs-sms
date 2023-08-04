import re
from unittest.mock import patch

import aioredis
import trio
import trio_asyncio
from hypercorn.trio import serve
from hypercorn.config import Config as HyperConfig
from pydantic import BaseModel, constr, conint, Field, field_serializer
from pydantic_settings import BaseSettings, SettingsConfigDict
from quart import render_template, redirect, request, url_for, websocket

import asyncclick as click
from quart_trio import QuartTrio

from mchs_sms.db import Database
from mchs_sms.smsc_api import (
    smsc_login,  # FIXME убрать импорт контекстной переменной
    smsc_password,  # FIXME убрать импорт контекстной переменной
    HttpMethod,
    SEND_URL,
    request_smsc,
)
from tests.test_request_smsc import MockSuccessResponse

app = QuartTrio(__name__)

PHONE_DELIMITERS = r";|,"
PHONES_PATTERN = re.compile(
    r"^[+]?\d{10,11}([" + PHONE_DELIMITERS + r"][+]?\d{10,11}){0,}$"
)


def convert_phones(ctx, param, value):
    """
    Очищает строку с телефонами от пробельных символов, проверяет её на валидность и
    возвращает список телефонов для рассылки.
    """
    phones = re.sub(r"\s+", "", value)

    if not PHONES_PATTERN.match(phones):
        raise click.BadParameter("Номера телефонов должны содержать только цифры")

    return re.split(PHONE_DELIMITERS, phones)


class Message(BaseModel):
    phones: list[constr(pattern=r"^[+]?\d{10,11}$")]
    mes: constr(min_length=5)
    valid: conint(ge=1, le=24)

    @field_serializer("phones")
    def serialize_phones(self, phones: list, _info):
        return ",".join(phones)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMSC_")

    login: str = Field(description="Логин для авторизации на сервисе smsc.ru.")
    psw: str = Field(description="Пароль для авторизации на сервисе smsc.ru.")


@app.route("/")
async def hello():
    return await render_template("index.html")


@app.websocket("/ws")
async def ws():
    messages = {
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
        ],
    }

    while True:
        await websocket.send_json(messages)
        await trio.sleep(1)


@app.route("/send/", methods=["POST"])
async def send_message():
    form = await request.form

    message = Message(
        valid=app.config["VALID"], phones=app.config["PHONES"], mes=form["text"]
    )
    with patch("asks.post") as mock_function:
        mock_function.return_value = MockSuccessResponse()
        response = await request_smsc(
            HttpMethod.post, SEND_URL, payload=message.model_dump()
        )
    print(f"Статус ответа {response.status_code}, ответ {response.content}")

    return redirect(url_for("hello"))


@click.command()
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
    callback=convert_phones,
    help="Номер телефона или несколько номеров через запятую или точку с запятой.",
)
@click.option(
    "-r",
    "--redis",
    "redis_uri",
    help="Адрес сервера REDIS для хранения информации о рассылках.",
    default="redis://localhost",
)
async def run_server(valid, phones, redis_uri):
    async with trio_asyncio.open_loop():
        config = HyperConfig()
        config.bind = ["127.0.0.1:5000"]
        config.use_reloader = True

        conf = Settings().model_dump()

        smsc_login.set(conf["login"])
        smsc_password.set(conf["psw"])
        app.config.from_prefixed_env()
        app.config["VALID"] = valid
        app.config["PHONES"] = phones

        redis = aioredis.from_url(redis_uri, decode_responses=True)
        app.config["REDIS_DB"] = Database(redis)

        await serve(app, config)


if __name__ == "__main__":
    trio.run(run_server(_anyio_backend="trio"))
    # https: // github.com / nstonic / sms_for_mchs / blob / main / server.py
