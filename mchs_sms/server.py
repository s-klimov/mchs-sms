import collections
import re
from enum import IntEnum
from unittest.mock import patch
from urllib.error import HTTPError

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
    STATUS_URL,
)
from tests.test_request_smsc import MockSuccessResponse, MockSendStatusResponse

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


class Status(BaseModel):
    class Number(IntEnum):
        """
        Формат ответа сервера:
            0 – (по умолчанию) в виде строки (Status = 1, check_time = 10.10.2010 10:10:10).
            1 – в виде номера статуса и штампа времени через запятую (1,1286524541).
            2 – в xml формате.
            3 – в json формате.
        """

        ZERO = 0
        ONE = 1
        TWO = 2
        THREE = 3

    phone: constr(pattern=r"^[+]?\d{10,11}$")
    id: conint(ge=0)
    fmt: Number = Number.THREE

    @field_serializer("id")
    def serialize_id(self, id: int, _info):
        return str(id)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SMSC_")

    login: str = Field(description="Логин для авторизации на сервисе smsc.ru.")
    psw: str = Field(description="Пароль для авторизации на сервисе smsc.ru.")


@app.route("/")
async def hello():
    return await render_template("index.html")


@app.websocket("/ws")
async def ws():
    """
    Делает регулярные запросы в сторону sms-сервиса для получения статусов отправки sms
    Документация по статусам https://smsc.ru/api/http/status_messages/statuses/#menu
    """

    verbose = (
        lambda _status: "delivered"
        if _status in (1, 2, 4)
        else "pending"
        if _status in (-1, 0)
        else "failed"
    )

    db = app.config["REDIS_DB"]

    pending_sms_list = await trio_asyncio.aio_as_trio(db.get_pending_sms_list)()
    print("pending:")
    print(pending_sms_list)

    statuses = list()

    for pending_sms in pending_sms_list:
        with patch("asks.get") as mock_function:
            mock_function.return_value = MockSendStatusResponse()
            phone, sms_id = pending_sms[1], pending_sms[0]
            status = Status(phone=phone, id=sms_id)
            response = await request_smsc(
                HttpMethod.get, STATUS_URL, payload=status.model_dump()
            )

            if response.status_code == 200:
                statuses.append(
                    [
                        sms_id,
                        phone,
                        verbose(response.content["status"]),
                    ]
                )

    await trio_asyncio.aio_as_trio(db.update_sms_status_in_bulk)(statuses)

    sms_ids = await trio_asyncio.aio_as_trio(db.list_sms_mailings)()
    print("Registered mailings ids", sms_ids)

    sms_mailings = await trio_asyncio.aio_as_trio(db.get_sms_mailings)(*sms_ids)
    print("sms_mailings")
    print(sms_mailings)

    messages = {"msgType": "SMSMailingStatus", "SMSMailings": []}
    for sms_mailing in sms_mailings:
        messages["SMSMailings"].append(
            {
                "timestamp": sms_mailing["created_at"],
                "SMSText": sms_mailing["text"],
                "mailingId": str(sms_mailing["sms_id"]),
                "totalSMSAmount": sms_mailing["phones_count"],
                "deliveredSMSAmount": collections.Counter(
                    sms_mailing["phones"].values()
                )["delivered"],
                "failedSMSAmount": collections.Counter(sms_mailing["phones"].values())[
                    "failed"
                ],
            }
        )
    print(messages)
    await websocket.send_json(messages)


@app.route("/send/", methods=["POST"])
# FIXME сделать декоратор backoff для обработки ошибки HTTPError
async def send_message():
    form = await request.form

    message = Message(
        valid=app.config["VALID"], phones=app.config["PHONES"], mes=form["text"]
    )
    with patch("asks.post") as mock_function:
        mock_function.return_value = MockSuccessResponse()
        try:
            response = await request_smsc(
                HttpMethod.post, SEND_URL, payload=message.model_dump()
            )
        except HTTPError:
            return {"errorMessage": "Потеряно соединение с SMSC.ru"}

    print(f"Статус ответа {response.status_code}, ответ {response.content}")

    db = app.config["REDIS_DB"]

    await trio_asyncio.aio_as_trio(db.add_sms_mailing)(
        response.content["id"], message.phones, message.mes
    )

    sms_ids = await trio_asyncio.aio_as_trio(db.list_sms_mailings)()
    print("Registered mailings ids", sms_ids)

    pending_sms_list = await trio_asyncio.aio_as_trio(db.get_pending_sms_list)()
    print("pending:")
    print(pending_sms_list)

    return pending_sms_list


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
