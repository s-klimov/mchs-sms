import trio
import trio_asyncio
from hypercorn.trio import serve
from hypercorn.config import Config as HyperConfig
from pydantic import BaseModel, constr, conint, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from quart import render_template, redirect, request, url_for, websocket

import asyncclick as click
from quart_trio import QuartTrio

from mchs_sms.smsc_api import (
    validate_phones,
    smsc_login,
    smsc_password,
    HttpMethod,
    SEND_URL,
    request_smsc,
)

app = QuartTrio(__name__)


class Message(BaseModel):
    phones: constr(
        strip_whitespace=True, pattern=r"^[+]?\d{10,11}([;|,][+]?\d{10,11}){0,}$"
    )
    mes: constr(min_length=5)
    valid: conint(ge=1, le=24)


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
    callback=validate_phones,
    help="Номер телефона или несколько номеров через запятую или точку с запятой.",
)
async def run_server(valid, phones):
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

        await serve(app, config)


if __name__ == "__main__":
    trio.run(run_server(_anyio_backend="trio"))
    # https: // github.com / nstonic / sms_for_mchs / blob / main / server.py
