"""Attack Shark K86 — teclado 75% sem fio, dongle ROYUAN.

Bateria: byte 1 do frame de status do dongle. **Leia o PROTOCOL.md antes de
confiar no número** — ele não vale com o teclado no carregador.

Sem controle de propósito: o dongle 2.4G não repassa nada pelo rádio, e por
cabo o sharkfin já faz tudo. Ver WONT.
"""
import fcntl
import os
import time

from .. import Reading, find_iface

NAME = "Attack Shark K86"
KIND = "keyboard"
IDS = ("00003151:00004011",)  # dongle 2.4G; por cabo ele enumera como 4015
CAPS = ("battery",)
WONT = {
    "light": "o dongle 2.4G responde todo opcode com o próprio frame de status "
             "e não repassa nada ao teclado — não é limitação de software. "
             "Por cabo, use o sharkfin (app.getsharkfin.com)",
    "rgb": "idem light",
    "remap": "idem light",
    "sleep": "idem light",
}

# ioctls do hidraw (linux/hidraw.h): _IOC(READ|WRITE, 'H', nr, tamanho)
_IOWR = lambda nr, n: (3 << 30) | (n << 16) | (0x48 << 8) | nr
HIDIOCSFEATURE = lambda n: _IOWR(0x06, n)
HIDIOCGFEATURE = lambda n: _IOWR(0x07, n)

OPCODE = 0xF7  # qualquer um serve: o dongle responde o mesmo frame a todos


def find():
    return find_iface(IDS, writable=True)


def ck7(pkt):
    """Checksum da família ROYUAN: 0xFF - soma dos bytes 0..6, guardado no 7.
    Vale para o que se **manda**; a resposta do dongle traz 0 aí."""
    pkt[7] = (0xFF - (sum(pkt[:7]) & 0xFF)) & 0xFF
    return pkt


def battery(path, wait=0):
    """Frame de status do dongle. `wait` é ignorado: a resposta é imediata.

    ponytail: teto conhecido — não está provado que escrever aqui não acorda o
    teclado pelo rádio (no F75 isso reiniciava o timer de sono, e economizar
    bateria é o objetivo). A favor: a resposta volta idêntica e instantânea
    mesmo com espera de 1 s, o que sugere que quem responde é o dongle sozinho.
    Se a bateria passar a cair rápido demais, o primeiro suspeito é este código.
    """
    fd = os.open(path, os.O_RDWR)
    try:
        req = ck7(bytearray(64))
        req[0] = OPCODE
        fcntl.ioctl(fd, HIDIOCSFEATURE(65), bytes([0]) + bytes(req))
        time.sleep(0.05)
        buf = bytearray(65)
        fcntl.ioctl(fd, HIDIOCGFEATURE(65), buf)
        return parse(bytes(buf[1:17]))
    finally:
        os.close(fd)


def parse(frame):
    """`00 PP 00 CC 01 01 01 00` -> Reading. None se o frame não presta.

    Sem flag de carga: o byte 3 oscila 0/1 sem cabo nenhum (medido em 1389
    amostras), então reportá-lo mentiria metade do tempo.

    Percentual 0 é o frame desalinhado (um byte a menos) que sai logo depois de
    o dongle enumerar. Bateria 0 de verdade não chega aqui: teclado sem carga
    não reporta nada.
    """
    if len(frame) < 8 or not 1 <= frame[1] <= 100:
        return None
    return Reading(frame[1], None, frame)
