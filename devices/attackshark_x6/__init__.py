"""Attack Shark X6 — mouse sem fio. Bateria por anúncio.

Protocolo em PROTOCOL.md. Resumo: o receptor emite sozinho, no report `0x03`,
um frame de 5 bytes cuja estrutura é `[evento, modelo, código, param1, param2]`.
O código `0x40` é o de bateria, e o percentual é o `param2`.

Aparelho **de anúncio**, não de pergunta: o `battery()` espera o mouse falar.
Com `wait=0` o laço não roda nem uma vez e ele fica invisível sem erro nenhum —
a mesma armadilha documentada no M900Pro e no AJ139.
"""
import os
import select
import time

from .. import Reading, find_iface, pct_ok

NAME = "Attack Shark X6"
KIND = "mouse"
# TRÊS PIDs, porque o X6 é tri-mode e **troca de ID USB conforme o modo** — o
# aparelho some do repo sem erro nenhum quando o dono muda a chavinha.
# Visto aqui: `FA61` ("Xenta USB Gaming Mouse") e depois `FA60`
# ("Xenta 2.4G Wireless Device"), no mesmo mouse, sem reinstalar nada.
# `FA55` vem das regras udev do attack-shark-x11-driver e não foi visto aqui.
IDS = ("00001D57:0000FA60", "00001D57:0000FA61", "00001D57:0000FA55")
CAPS = ("battery",)
WONT = {
    "charging": "o param1 não bate com a tabela de estados do driver de "
                "referência; ver PROTOCOL.md",
}

REPORT = 0x03  # "Event Message" — sempre 0x03 nesta família
DEVICE_ID = 0x10  # identifica o modelo; o X11 usa 0x55, e cada um tem o seu
EV_BATTERY = 0x40  # "Device Connection Message" — apesar do nome, é a bateria
PCT_INDEX = 4

# O aparelho expõe QUATRO interfaces com o mesmo VID:PID e nenhuma página de
# fabricante. O que separa a de status é esta assinatura do descritor:
# Usage Page Ordinal (05 0a), Usage 0, Collection Application, Report ID 3.
DESC_SIG = bytes.fromhex("050a0900a10185 03".replace(" ", ""))


def find():
    return find_iface(IDS, contains=DESC_SIG)


def battery(path, wait=3):
    """Espera o frame de bateria aparecer. `None` se não vier dentro de `wait`.

    Mouse parado não fala, e isso é correto: parado não gastou bateria, e o
    `status_text` mantém o último valor conhecido em vez de apagá-lo.
    """
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        fim = time.time() + max(wait, 0.0)
        # `while True` com a checagem no fim daria uma passada mesmo com wait=0,
        # mas mentiria: o chamador que pediu 0 não quer bloquear. Melhor devolver
        # None e o `--wait` resolver, que é o contrato dos outros anunciantes.
        while time.time() < fim:
            r, _, _ = select.select([fd], [], [], 0.2)
            if not r:
                continue
            try:
                pkt = os.read(fd, 64)
            except OSError:
                continue
            leitura = parse(pkt)
            if leitura:
                return leitura
        return None
    finally:
        os.close(fd)


def parse(pkt):
    """`03 10 40 <estado> <pct>` -> Reading.

    Os três primeiros bytes são conferidos porque esta mesma interface carrega
    outros eventos da família — o `0x50`, por exemplo, é o status de um Feature
    Report e traz um ID de report no byte 4. Sem checar o `0x40`, esse ID viraria
    "bateria" silenciosamente.
    """
    if len(pkt) < PCT_INDEX + 1:
        return None
    if pkt[0] != REPORT or pkt[1] != DEVICE_ID or pkt[2] != EV_BATTERY:
        return None
    if not pct_ok(pkt[PCT_INDEX]):
        return None
    # charging=None de propósito: ver WONT e PROTOCOL.md.
    return Reading(pkt[PCT_INDEX], None, bytes(pkt[:5]))
