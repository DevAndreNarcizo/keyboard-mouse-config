"""AJAZZ AJ139 — mouse sem fio (família Smailwolf/YJX).

Só escuta: o mouse anuncia a bateria sozinho no canal vendor, num `0xFA`.
Protocolo da família em github.com/0LostConnection/Smailwolf-RS7.

Fora da mesa desde 2026-08-07. Código movido do antigo `battlog-f75.py`, sem
lógica reescrita; o parser está travado por assert no selftest.
"""
import os
import select
import time

from .. import Reading, find_iface

NAME = "AJAZZ AJ139"
KIND = "mouse"
IDS = ("0000A8A5:00002255",)
CAPS = ("battery",)
WONT = {}


def find():
    return find_iface(IDS, at_start=True)


def battery(path, wait=60):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        end = time.time() + wait
        while (left := end - time.time()) > 0:
            if not select.select([fd], [], [], left)[0]:
                continue
            got = parse(os.read(fd, 64))
            if got:
                return got
        return None
    finally:
        os.close(fd)


def parse(pkt):
    """`AA FA .. ck .. D0 PP CH` -> Reading.

    O marker `0xD0` no byte 8 é obrigatório: o mesmo `0xFA` também carrega o
    slot de DPI, e sem o marker um pacote de DPI viraria um percentual falso.
    O checksum pega pacote picado.
    """
    if len(pkt) < 11 or pkt[0] != 0xAA or pkt[1] != 0xFA:
        return None
    if pkt[8] != 0xD0 or not 1 <= pkt[9] <= 100:
        return None
    if sum(pkt[4:64]) & 0xFF != pkt[3]:
        return None
    return Reading(pkt[9], 1 if pkt[10] else 0, bytes(pkt[:16]))
