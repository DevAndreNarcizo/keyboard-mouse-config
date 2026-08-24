"""JBL Wave Buds 2 — fone Bluetooth.

Aqui **não há engenharia reversa nenhuma**, e é o ponto: o BlueZ já expõe a
bateria em `org.bluez.Battery1`, normalizada. Todo o conhecimento deste modelo
cabe no `Modalias`; o transporte mora no `find_bluez`/`bluez_pct` do pacote, do
mesmo jeito que o `find_iface` guarda o lado HID.

Consequência boa: um segundo fone é um diretório de 20 linhas. Consequência
honesta: se um dia o BlueZ parar de reportar, não há um plano B aqui — não
sabemos falar o protocolo do fone, e nem precisamos.
"""
import time

from .. import Reading, find_bluez, bluez_pct

NAME = "JBL Wave Buds 2"
KIND = "headset"
IDS = ("v0ECBp2100",)  # de `bluetooth:v0ECBp2100d001F`; sem o `d`, que muda
                       # com revisão de firmware
CAPS = ("battery",)
WONT = {
    "light": "não tem luz controlável, e o BlueZ não expõe nada além de bateria",
    "rgb": "não tem LED endereçável, e o BlueZ só expõe bateria",
    "remap": "os controles de toque são do firmware; o BlueZ não os expõe",
    "sleep": "quem decide desligar é o firmware, no case; nada disso em D-Bus",
}


def find():
    """Só devolve path se o fone estiver **conectado** — desconectado ele
    continua pareado e visível no BlueZ, mas sem bateria para ler."""
    return find_bluez(IDS)


def battery(path, wait=0):
    """Percentual do BlueZ. `wait` cobre o intervalo entre o fone conectar e o
    `Battery1` aparecer, que não é instantâneo.

    `charging` é sempre None: o `org.bluez.Battery1` só tem `Percentage`. O fone
    sabe se está no case carregando, mas não conta ao BlueZ — e inventar isso
    seria pior que omitir.

    `raw` é vazio porque não existe frame: o número já vem decodificado. É a
    diferença em relação aos modelos HID, cujo frame cru alimenta o `kmctl raw`.
    """
    end = time.time() + max(wait, 0)
    while True:
        pct = bluez_pct(path)
        if pct:
            return Reading(pct, None, b"")
        if time.time() >= end:
            return None
        time.sleep(2)
