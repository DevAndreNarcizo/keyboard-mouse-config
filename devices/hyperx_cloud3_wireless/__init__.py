"""HyperX Cloud III Wireless — fone. Bateria por request/response.

Protocolo em PROTOCOL.md. Resumo: report `0x66` na página vendor `0xff13`,
escreve 52 bytes `66 89 00…`, e a resposta traz o percentual no byte 4 e a
tensão da célula nos bytes 2..3.

O fone tem bateria, mas **não a declara em lugar nenhum que o kernel entenda**:
o descritor não tem página de bateria, ele cai em `hid_generic`, e por isso não
aparece no `power_supply` nem no UPower. Era o caso clássico de "tem bateria e o
Linux não vê" — daí este diretório existir.

Fonte do protocolo: auto94/HyperX-Cloud-2-Battery-Monitor, que declara o PID
3229 (= 0x0C9D) como "Cloud III rev 4106" e a interface como usage page 65299
(= 0xFF13). Confirmado aqui contra o hardware.
"""
import os
import select
import time

from .. import Reading, find_iface, pct_ok

NAME = "HyperX Cloud III Wireless"
KIND = "headset"
IDS = ("000003F0:00000C9D",)
CAPS = ("battery",)
WONT = {
    "charging": "nenhum byte da resposta mudou com o cabo ligado; ver PROTOCOL.md",
}

REPORT = 0x66  # Output 61B + Input 61B, os dois na página 0xff13
OP_STATUS = 0x89
REQ_SIZE = 52  # tamanho do app de referência; o descritor aceita até 61
PCT_INDEX = 4
MV_HI, MV_LO = 2, 3  # tensão da célula, big-endian, em mV


def find():
    # writable=True: a interface certa é a que tem o Output do report 0x66. As
    # outras três do fone são áudio (classe 01) e nem viram hidraw.
    return find_iface(IDS, writable=True)


def battery(path, wait=0):
    """`66 89 VV VV PP` -> Reading. Byte 4 é o percentual.

    `wait` é ignorado de propósito: este aparelho **responde a pergunta**, não se
    anuncia. Esperar não traz nada — a resposta chega em milissegundos ou não
    chega. Ver a distinção em SETUP.md ("Dois tipos de aparelho").
    """
    req = bytearray(REQ_SIZE)
    req[0] = REPORT
    req[1] = OP_STATUS

    fd = os.open(path, os.O_RDWR | os.O_NONBLOCK)
    try:
        try:
            os.write(fd, bytes(req))
        except OSError:
            return None
        # 1s é o timeout do app de referência. Medido aqui: responde em <50ms.
        fim = time.time() + 1.0
        while time.time() < fim:
            r, _, _ = select.select([fd], [], [], 0.1)
            if not r:
                continue
            try:
                pkt = os.read(fd, 64)
            except OSError:
                continue
            r = parse(pkt)
            if r:
                return r
        return None
    finally:
        os.close(fd)


def parse(pkt):
    """Só aceita o eco `66 89` — o fone também emite frames de mídia nesta mesma
    interface, e sem conferir os dois bytes qualquer um deles viraria "bateria".
    """
    if len(pkt) < PCT_INDEX + 1:
        return None
    if pkt[0] != REPORT or pkt[1] != OP_STATUS:
        return None
    pct = pkt[PCT_INDEX]
    # >100 é o que o fone devolve desligado (0xff visto no Cloud III S). O
    # pct_ok já corta isso e o 0; fica explícito porque o motivo não é óbvio.
    if not pct_ok(pct):
        return None
    return Reading(pct, None, bytes(pkt[:8]))


def millivolts(pkt):
    """Tensão da célula, em mV. Não entra no Reading — serve de conferência.

    Foi ela que deu confiança no byte 4 sem precisar carregar o fone: 0x0f74 =
    3956 mV com o byte 4 marcando 79%, e 3,956 V é exatamente onde uma Li-ion de
    célula única está com ~79%. Dois sinais independentes concordando.
    """
    if len(pkt) < MV_LO + 1:
        return None
    return (pkt[MV_HI] << 8) | pkt[MV_LO]
