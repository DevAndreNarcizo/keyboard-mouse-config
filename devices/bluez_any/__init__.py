"""Qualquer aparelho Bluetooth conectado que reporte bateria.

Fonte genérica, não modelo: não há `IDS` aqui, e é o ponto — um fone, teclado,
mouse ou controle Bluetooth novo aparece sozinho, sem ninguém escrever um
diretório. Quem decodifica é o BlueZ.

Houve um `devices/jbl_wave_buds_2/` por umas horas em 2026-08-24, e ele foi
**removido**: lia o mesmo aparelho pelo mesmo caminho que este módulo, e existir
junto obrigou a inventar dedução em `present()` para o fone não aparecer duas
vezes. O que ele tinha de próprio era um `WONT`, e o `WONT` é mais verdadeiro
aqui — "o BlueZ só expõe bateria" vale para todo aparelho Bluetooth, não para um
modelo. Regra que ficou: **diretório de modelo só quando nenhuma fonte vê o
aparelho, ou quando há caps de controle a declarar.**

O que se sabe do transporte está no `PROTOCOL.md` ao lado.
"""
import time

from .. import Reading, bluez_objects, bluez_pct

NAME = "Bluetooth (via BlueZ)"
SOURCE = True
CAPS = ("battery",)
WONT = {
    "light": "o BlueZ não expõe luz de aparelho Bluetooth — só bateria. Não é "
             "limitação daqui: não há interface D-Bus para isso",
    "rgb": "o D-Bus do BlueZ não tem cor: nenhuma interface dele fala de LED",
    "remap": "botão e toque são resolvidos no firmware do aparelho, antes de "
             "virar evento Bluetooth; nada disso chega ao BlueZ",
    "sleep": "quem decide dormir é o firmware do aparelho; não há como pedir "
             "por D-Bus",
}

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
    """Categoria a partir do `Icon` do BlueZ. Desconhecido vira `other` — um
    ícone de bateria genérico é melhor que um ícone errado."""
    return ICONE_KIND.get(icone, "other")


def achados(objects):
    """[(ident, nome, kind, path)] dos conectados que reportam bateria.

    Função pura sobre o dicionário do BlueZ, para o selftest rodar sem Bluetooth
    ligado. Exige `Connected` **e** `Battery1`: um aparelho pareado e desligado
    continua existindo no BlueZ, e listá-lo daria um slot sem número.
    """
    out = []
    for path in sorted(objects):
        dev = objects[path].get("org.bluez.Device1")
        if not dev or not dev.get("Connected"):
            continue
        if "org.bluez.Battery1" not in objects[path]:
            continue
        addr = dev.get("Address", "")
        nome = dev.get("Alias") or dev.get("Name") or addr or "Bluetooth"
        ident = "bt_" + addr.replace(":", "").lower()
        out.append((ident, nome, kind_de(dev.get("Icon", "")), path))
    return out


def discover():
    return achados(bluez_objects())


def battery(path, wait=0):
    """Percentual do BlueZ. `wait` cobre o intervalo entre o aparelho conectar e
    o `Battery1` aparecer, que não é instantâneo.

    `charging` é sempre None: `org.bluez.Battery1` só tem `Percentage`. Muitos
    aparelhos sabem que estão carregando e não contam ao BlueZ — inventar isso
    seria pior que omitir.

    `raw` é vazio porque não existe frame: o número já vem decodificado. É a
    diferença em relação aos modelos HID, cujo frame cru alimenta o `kmctl raw`.
    """
    end = time.time() + max(wait, 0)
    while True:
        pct = bluez_pct(path)
        if pct is not None:
            return Reading(pct, None, b"")
        if time.time() >= end:
            return None
        time.sleep(2)
