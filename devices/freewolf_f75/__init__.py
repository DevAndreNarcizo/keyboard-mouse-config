"""FreeWolf F75 — teclado 75% sem fio. Único modelo daqui com controle completo.

Protocolo em PROTOCOL.md (engenharia reversa do DeviceDriver.exe 1.0.4.4):
pacote de 64 bytes no canal vendor, sem checksum:

    [0:4] sync AA 55 CC 33   (mesmo nos dois sentidos)
    [4]   comando
    [5:]  payload

Writes em /dev/hidraw precisam do prefixo Report ID 0x00 (o kernel remove).

Este hardware saiu da mesa em 2026-08-07. O código veio inteiro do antigo
`f75ctl.py`/`battlog-f75.py`, sem lógica reescrita — os bytes de cada pacote
estão travados por assert no selftest, que é o que dá para testar sem o teclado.
"""
import json
import os
import select
import time

from .. import Reading, find_iface

NAME = "FreeWolf F75"
KIND = "keyboard"
# IDs do config.xml oficial: 2.4G, cabo, cabo antigo
IDS = ("00001A2C:00008FFF", "00001A2C:0000A073", "00001A2C:0000AFFF")
CAPS = ("battery", "light", "rgb", "off", "remap", "sleep")
WONT = {}

SYNC = bytes.fromhex("aa55cc33")
CMD_STATUS = 0x0E  # -> [5]=bateria %, [6]=flag de estado (não é carga)
CMD_LIGHT = 0x07  # modo/brilho/velocidade/direcao/cor
CMD_CUSTOM_BEGIN = 0x0B  # enviado depois do 0x07 quando modo == MODE_CUSTOM
CMD_CUSTOM_PUSH = 0x09  # precede o stream de cores por tecla
# Dois bancos de frame, 6 pacotes cada, 18 teclas (RGB) por pacote.
# Os DOIS precisam ser enviados: com só um banco a maioria das teclas fica apagada.
KEY_BANKS = (0xF0, 0xF6)
KEYS_PER_PACKET = 18
KEY_SLOTS = 108
MODE_CUSTOM = 24
PACKET_GAP = 0.003  # ponytail: Sleep(3ms) do app; aumentar se faltar tecla

CMD_KEY = 0x04  # remap: [5]=camada+1, [6]=tecla, [7]=alvo (códigos HID usage)
# CUIDADO: 0x0F LIMPA o keymap (o app manda antes de reenviar tudo, não depois).
CMD_CLEAR_KEYS = 0x0F
LAYERS = {"base": 0, "fn": 1}  # "Top layer" / "Fn layer" na UI oficial

CMD_SLEEP = 0x0C  # [5] = valor abaixo (combo "Keyboard sleep time" do app)
SLEEP_VALUES = {"2min": 1, "15min": 2, "30min": 3, "never": 4}

# layouts/kb-k600t.xml + language/1033.lan
MODES = {
    1: "ondas esquerda/direita", 2: "pontos estrelados", 3: "ondas cima/baixo",
    4: "ejecao bidirecional", 5: "ciclo espectral", 6: "caleidoscopio",
    7: "luz estatica", 8: "respiracao geral", 9: "operacao cruzada",
    10: "luz voando", 11: "respiracao por tecla", 12: "pergaminho",
    13: "serpente", 14: "tornado", 15: "tres acima tres abaixo",
    16: "chuva", 17: "moinho", 18: "onda senoidal", 19: "cavalo a galope",
    20: "entrecruzado", 22: "ritmo de musica", 23: "ritmo da tela",
    24: "custom (por tecla)",
}
BRIGHTNESS_MAX = SPEED_MAX = 5

KEY_NAMES = {
    "esc": 0x29, "enter": 0x28, "tab": 0x2B, "space": 0x2C, "backspace": 0x2A,
    "capslock": 0x39, "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
    "insert": 0x49, "home": 0x4A, "pgup": 0x4B, "delete": 0x4C, "end": 0x4D,
    "pgdn": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "menu": 0x65, "none": 0x00,
    **{f"f{n}": 0x39 + n for n in range(1, 13)},
}

# Extraído do layouts/kb-k600t.xml do app Windows do fabricante. Só a tabela
# derivada mora aqui: o XML original é proprietário e não vai no repo.
SLOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key-slots.json")


def find():
    return find_iface(IDS, at_start=True)


def hid_code(name):
    """Nome de tecla -> HID usage code. Aceita 0xNN direto."""
    n = name.lower()
    if n in KEY_NAMES:
        return KEY_NAMES[n]
    if n.startswith("0x") and len(n) <= 4:
        try:
            return int(n, 16)
        except ValueError:
            pass
    if len(n) == 1 and "a" <= n <= "z":
        return 0x04 + ord(n) - ord("a")
    if len(n) == 1 and "1" <= n <= "9":
        return 0x1E + ord(n) - ord("1")
    if n == "0":
        return 0x27
    raise ValueError(f"tecla desconhecida: {name!r} (use um nome, uma letra ou 0xNN)")


def key_slots():
    """Código HID -> slot no frame de cores (o key_index do layout oficial)."""
    with open(SLOTS) as f:
        return {int(code, 16): slot for code, slot in json.load(f).items()}


def build(cmd, payload=b""):
    pkt = bytearray(64)
    pkt[0:4] = SYNC
    pkt[4] = cmd
    pkt[5 : 5 + len(payload)] = payload
    return bytes(pkt)


def hexdump(data, n=12):
    return " ".join(f"{b:02x}" for b in data[:n]) + " ..."


class _Wire:
    """Os pacotes de uma operação. Em dry-run só anota, não abre nada."""

    def __init__(self, path, dry):
        self.dry, self.log = dry, []
        self.fd = None if dry else os.open(path, os.O_RDWR)

    def send(self, pkt):
        self.log.append(">> " + hexdump(pkt))
        if not self.dry:
            os.write(self.fd, b"\x00" + pkt)

    def recv(self, seconds=1.0, cmd=None):
        if self.dry:
            return None
        end = time.time() + seconds
        while (left := end - time.time()) > 0:
            if not select.select([self.fd], [], [], left)[0]:
                break
            data = os.read(self.fd, 64)
            self.log.append("<< " + hexdump(data))
            if data[:4] == SYNC and (cmd is None or data[4] == cmd):
                return data
        return None

    def close(self):
        if self.fd is not None:
            os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def battery(path, wait=0):
    """`0x0E` -> [5] bateria %. O [6] é flag de estado, não de carga."""
    with _Wire(path, dry=False) as w:
        w.send(build(CMD_STATUS))
        r = w.recv(max(wait, 2.0), CMD_STATUS)
    if not r or not 1 <= r[5] <= 100:
        return None
    return Reading(r[5], None, bytes(r[:16]))


def light(path, mode=7, brightness=5, speed=3, direction=0, color=0, dry=False):
    for name, val, lo, hi in (("mode", mode, 1, 24),
                              ("brightness", brightness, 1, BRIGHTNESS_MAX),
                              ("speed", speed, 1, SPEED_MAX),
                              ("direction", direction, 0, 1),
                              ("color", color, 0, 9)):
        if not lo <= val <= hi:
            raise ValueError(f"--{name}={val} fora da faixa {lo}..{hi}")
    payload = bytes([mode - 1, brightness - 1, speed - 1, direction, color])
    with _Wire(path, dry) as w:
        w.send(build(CMD_LIGHT, payload))
        log = w.log
    return (f"modo {mode} ({MODES.get(mode, '?')}), brilho {brightness}, "
            f"vel {speed}, dir {direction}, cor {color}", log)


def rgb(path, color, only=None, brightness=5, speed=4, dry=False):
    """Pinta o teclado com uma cor RGB arbitrária (modo custom, por tecla)."""
    try:
        cor = bytes.fromhex(color.lstrip("#"))
        assert len(cor) == 3
    except (ValueError, AssertionError):
        raise ValueError(f"cor inválida: {color!r} (use RRGGBB, ex: ff0080)")

    frame = bytearray(cor * KEY_SLOTS)
    if only:
        slots = key_slots()
        frame = bytearray(KEY_SLOTS * 3)  # resto apagado
        for name in only.split(","):
            try:
                slot = slots[hid_code(name.strip())]
            except (KeyError, ValueError):
                raise ValueError(f"tecla sem slot no layout: {name!r}")
            frame[slot * 3 : slot * 3 + 3] = cor

    with _Wire(path, dry) as w:
        w.send(build(CMD_LIGHT, bytes([MODE_CUSTOM - 1, brightness - 1,
                                       speed - 1, 0, 0])))
        w.send(build(CMD_CUSTOM_BEGIN))
        w.send(build(CMD_CUSTOM_PUSH))
        chunk = KEYS_PER_PACKET * 3
        for base in KEY_BANKS:
            for i in range(KEY_SLOTS // KEYS_PER_PACKET):
                if not dry:
                    time.sleep(PACKET_GAP)
                w.send(build(base + i, frame[i * chunk : (i + 1) * chunk]))
        log = w.log
    alvo = f"em {only}" if only else f"em {KEY_SLOTS} teclas"
    return f"cor #{cor.hex()} aplicada {alvo} (brilho {brightness})", log


def off(path, dry=False):
    """Apaga as teclas o máximo que o protocolo permite. `010101` e não
    `000000`: preto é transparente no stream (o firmware lê como "não mexe
    nesta tecla"). Brilho 1 porque o brilho é PWM em cima do valor do frame — e
    brilho 0 (byte 0xFF) o firmware ignora. Off de verdade só existe no Fn+X."""
    return rgb(path, "010101", brightness=1, speed=4, dry=dry)


def remap(path, key, to, layer="fn", dry=False):
    """Remapeia uma tecla (por padrão na camada Fn)."""
    k, alvo = hid_code(key), hid_code(to)
    if layer not in LAYERS:
        raise ValueError(f"camada {layer!r}: use {' ou '.join(LAYERS)}")
    with _Wire(path, dry) as w:
        if not dry:
            time.sleep(0.016)  # o app espera 16ms entre teclas
        w.send(build(CMD_KEY, bytes([LAYERS[layer] + 1, k, alvo])))
        log = w.log
    return f"camada {layer}: {key} (0x{k:02x}) -> {to} (0x{alvo:02x})", log


def sleep(path, when, dry=False):
    """Tempo de inatividade antes do teclado dormir."""
    if when not in SLEEP_VALUES:
        raise ValueError(f"{when!r}: use {' | '.join(SLEEP_VALUES)}")
    with _Wire(path, dry) as w:
        w.send(build(CMD_SLEEP, bytes([SLEEP_VALUES[when]])))
        log = w.log
    return f"sleep time: {when}", log
