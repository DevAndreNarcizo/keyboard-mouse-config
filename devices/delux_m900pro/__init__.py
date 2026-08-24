"""Delux M900Pro — mouse sem fio, receptor 8K.

Só escuta: o receptor não responde a GET_REPORT (dá EPIPE), e só fala com o
mouse em uso. Mouse parado 70 s não produz nada — isso é "parado", não "quebrado".
"""
import os
import select
import time

from .. import Reading, find_iface, pct_ok

NAME = "Delux M900Pro"
KIND = "mouse"
IDS = ("00001D57:0000FA65",)
CAPS = ("battery",)
WONT = {}

REPORTS = (0x03, 0x04)  # 0x04 é o vendor do descritor; quem fala é o 0x03


def find():
    return find_iface(IDS, writable=True)


def battery(path, wait=60):
    """Espera o receptor se anunciar por até `wait` segundos."""
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        end = time.time() + wait
        while (left := end - time.time()) > 0:
            if not select.select([fd], [], [], left)[0]:
                continue
            pkt = os.read(fd, 64)
            if pkt and pkt[0] in REPORTS:
                return parse(pkt[:16])
        return None
    finally:
        os.close(fd)


def parse(frame):
    """`03 50 41 01 PP` -> Reading. O byte 4 é a bateria.

    **Provisório**: foi identificado por descida consistente (85 -> 57 em 5
    dias, 28 decrementos e nenhuma subida), não pelo salto de recarga que
    confirmou o do teclado. O frame inteiro continua no banco, então trocar o
    offset depois não custa histórico.
    """
    if len(frame) < 5 or not pct_ok(frame[4]):
        return None
    return Reading(frame[4], None, frame)
