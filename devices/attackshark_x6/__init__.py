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
    "battery-no-cabo": "com o mouse no cabo de carga não há canal de bateria "
                       "em lugar nenhum — medido; ver PROTOCOL.md",
}

# Texto para humano, não veredito: o `kmctl battery` o acrescenta à mensagem
# quando não veio número. Não passa pelo `estado()`, que tiraria o aparelho da
# lista — e mouse calado há dois minutos deve manter o último valor.
DICA = ("Se estiver no cabo de carga, é o esperado: medido, o dongle fica mudo "
        "e as interfaces do cabo não têm canal de bateria. Desplugue para ler.")

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


# ATENÇÃO — o `parse()` acima está DESLIGADO do `battery()` desde 2026-08-25.
#
# Ele lia o `param2` do frame de anúncio como percentual, e isso foi refutado: o
# mouse passou a noite no carregador, foi desplugado, e o valor continuou 10. O
# `kmctl show` mostra min 10 / max 10 em dois dias — o byte nunca se moveu.
#
# O `parse()` fica porque o selftest trava os bytes do frame e porque o
# significado do `param2` continua sendo pergunta aberta (constante? escala
# 0-10?). O que NÃO fica é afirmar 10% para o dono.
#
# O canal certo está mapeado em PROTOCOL.md: report 0x08, pacote de 16 bytes,
# comando 4, com percentual, flag de carga E tensão — extraído do HUB de
# navegador do fabricante. Falta testá-lo com o mouse fora do cabo de carga,
# porque no cabo o dongle não repassa nada pelo rádio.


def estado(path):
    """Por que o `battery()` não deu número. `None` se não souber dizer.

    Este mouse **só se anuncia**: não há pergunta a fazer. Quando o canal existe
    e não falou dentro da janela, o que se pode afirmar é exatamente isso — e não
    o motivo. Foi medido um caso em que o dongle ficou mudo por 15 s seguidos
    (mouse no cabo de carga), e o driver de referência diz que no modo cabo o
    mouse para de falar pelo rádio; mas **inferir "está no cabo" pela presença do
    PID de cabo seria errado**: em 2026-08-24 o `fa61` era justamente a interface
    que carregava o canal de status, e em 2026-08-25 o mesmo PID apareceu com
    duas interfaces sem canal nenhum. Mesmo PID, configuração USB diferente.

    Então aqui não se adivinha. Devolver `None` deixa a regra da janela decidir,
    que é o comportamento certo: aparelho calado há pouco mantém o último valor,
    calado há muito sai da lista.
    """
    return None
