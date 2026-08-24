"""Qualquer aparelho Bluetooth conectado que reporte bateria.

Fonte genérica, não modelo: não há `IDS` aqui, e é o ponto — um fone, teclado ou
mouse Bluetooth novo aparece sozinho, sem ninguém escrever um diretório. Quem
decodifica é o BlueZ.

Um diretório de modelo só se justifica ao lado desta fonte quando há algo a
declarar que o BlueZ não sabe: um `WONT` explicando por que aquele aparelho não
faz RGB, por exemplo. Quando existir esse diretório, o `present()` dá preferência
a ele e suprime o achado genérico — os dois devolvem o mesmo object path.
"""
from .. import bluez_objects, bluez_pct, Reading
import time

NAME = "Bluetooth (via BlueZ)"
SOURCE = True
CAPS = ("battery",)

# O `Icon` que o BlueZ publica é a melhor dica de categoria que existe de graça.
ICONE_KIND = {
    "audio-headset": "headset",
    "audio-headphones": "headset",
    "audio-card": "headset",
    "input-mouse": "mouse",
    "input-keyboard": "keyboard",
    "input-gaming": "gamepad",
    "input-tablet": "other",
    "phone": "phone",
    "computer": "other",
}


def kind_de(icone):
    return ICONE_KIND.get(icone, "other")


def achados(objects):
    """Função pura sobre o dicionário do BlueZ, para o selftest não precisar de
    Bluetooth ligado."""
    out = []
    for path in sorted(objects):
        dev = objects[path].get("org.bluez.Device1")
        if not dev or not dev.get("Connected"):
            continue
        if "org.bluez.Battery1" not in objects[path]:
            continue
        addr = dev.get("Address", "")
        ident = "bt_" + addr.replace(":", "").lower()
        nome = dev.get("Alias") or dev.get("Name") or addr or "Bluetooth"
        out.append((ident, nome, kind_de(dev.get("Icon", "")), path))
    return out


def discover():
    return achados(bluez_objects())


def battery(path, wait=0):
    end = time.time() + max(wait, 0)
    while True:
        pct = bluez_pct(path)
        if pct:
            return Reading(pct, None, b"")
        if time.time() >= end:
            return None
        time.sleep(2)
