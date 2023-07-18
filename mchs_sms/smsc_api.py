import time
from dataclasses import dataclass, asdict, field
from urllib.parse import urlencode

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
    login: str = field(repr=False, default="devman")
    psw: str = field(repr=False, default="Ab6Kinhyxquot")
    phones: str = ""
    mes: str = ""

    def __post_init__(self):
        self.mes = self.mes.strip()
        self.phones = self.phones.strip().replace(" ", "")


async def foo(i):
    start = time.time()

    message = Message(phones="79520057575", mes="Завтра хорошая погода")
    print(asdict(message))
    response = await asks.get(URL, params=urlencode(asdict(message)))
    content = response.text
    print(f"{i} | {content} (получено за {time.time() - start})")


async def root():
    start = time.time()
    async with trio.open_nursery() as nursery:
        for i in range(MAX_CLIENTS):
            nursery.start_soon(foo, i)

    print(f"завершено за {time.time() - start}")


if __name__ == "__main__":
    results_list = trio.run(root)
    print(results_list)
