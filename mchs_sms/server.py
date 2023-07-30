import trio
import trio_asyncio
from hypercorn.trio import serve
from hypercorn.config import Config as HyperConfig
from pydantic import BaseModel, field_validator, ValidationError, constr, conint
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
    mes: str
    valid: conint(ge=1, le=24)


@app.route("/")
async def hello():
    return await render_template("index.html")


@app.websocket("/ws")
async def ws():
    while True:
        await websocket.send("hello")
        await websocket.send_json({"hello": "world"})


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
async def run_server(login, psw, valid, phones):
    async with trio_asyncio.open_loop():
        config = HyperConfig()
        config.bind = ["127.0.0.1:5000"]
        config.use_reloader = True

        smsc_login.set(login)
        smsc_password.set(psw)
        app.config["VALID"] = valid
        app.config["PHONES"] = phones

        await serve(app, config)


if __name__ == "__main__":
    trio.run(run_server(_anyio_backend="trio"))
    # https: // github.com / nstonic / sms_for_mchs / blob / main / server.py
