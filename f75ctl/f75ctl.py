#!/usr/bin/env python3
"""f75ctl - controla o teclado FreeWolf F75 no Linux (stdlib apenas).

Protocolo (engenharia reversa do DeviceDriver.exe 1.0.4.4, ver PROTOCOL.md):
pacote de 64 bytes no canal vendor do teclado, sem checksum:

    [0:4] sync AA 55 CC 33   (mesmo nos dois sentidos)
    [4]   comando
    [5:]  payload

Writes em /dev/hidraw precisam do prefixo Report ID 0x00 (o kernel remove).
"""
import argparse
import glob
import json
import os
import select
import sys
import time

SYNC = bytes.fromhex("aa55cc33")
# IDs do config.xml oficial: 2.4G, cabo, cabo antigo
HID_IDS = ("00001A2C:00008FFF", "00001A2C:0000A073", "00001A2C:0000AFFF")

CMD_STATUS = 0x0E  # -> [5]=bateria %, [6]=flag
CMD_LIGHT = 0x07  # modo/brilho/velocidade/direcao/cor
CMD_CUSTOM_BEGIN = 0x0B  # enviado depois do 0x07 quando modo == MODE_CUSTOM
CMD_CUSTOM_PUSH = 0x09  # precede o stream de cores por tecla
# Dois bancos de frame, 6 pacotes cada, 18 teclas (RGB) por pacote.
# Os DOIS precisam ser enviados: com so um banco a maioria das teclas fica apagada.
KEY_BANKS = (0xF0, 0xF6)
KEYS_PER_PACKET = 18
KEY_SLOTS = 108
MODE_CUSTOM = 24
PACKET_GAP = 0.003  # ponytail: Sleep(3ms) do app; aumentar se faltar tecla

CMD_KEY = 0x04  # remap: [5]=camada+1, [6]=tecla, [7]=alvo (codigos HID usage)
# CUIDADO: 0x0F LIMPA o keymap (o app manda antes de reenviar tudo, nao depois).
# Mandar 0x0F depois de um 0x04 desfaz o remap. Use `raw 0f` se quiser limpar.
CMD_CLEAR_KEYS = 0x0F
LAYERS = {"base": 0, "fn": 1}  # "Top layer" / "Fn layer" na UI oficial

CMD_SLEEP = 0x0C  # [5] = valor abaixo (combo "Keyboard sleep time" do app)
SLEEP_VALUES = {"2min": 1, "15min": 2, "30min": 3, "never": 4}

# HID usage codes (letras/digitos sao calculados em hid_code)
KEY_NAMES = {
    "esc": 0x29, "enter": 0x28, "tab": 0x2B, "space": 0x2C, "backspace": 0x2A,
    "capslock": 0x39, "printscreen": 0x46, "scrolllock": 0x47, "pause": 0x48,
    "insert": 0x49, "home": 0x4A, "pgup": 0x4B, "delete": 0x4C, "end": 0x4D,
    "pgdn": 0x4E, "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "menu": 0x65, "none": 0x00,
    **{f"f{n}": 0x39 + n for n in range(1, 13)},
}


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
    raise ValueError(f"tecla desconhecida: {name!r} (use um nome, uma letra "
                     "ou 0xNN)")

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


def find_device():
    """Retorna o /dev/hidrawN do canal vendor do F75 (page 0xFFxx)."""
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        if not any(i in open(uevent).read() for i in HID_IDS):
            continue
        d = os.path.dirname(uevent)
        desc = open(os.path.join(d, "report_descriptor"), "rb").read()
        if desc[0] == 0x06 and desc[2] == 0xFF:
            return "/dev/" + os.path.basename(os.path.dirname(d))
    return None


def build(cmd, payload=b""):
    pkt = bytearray(64)
    pkt[0:4] = SYNC
    pkt[4] = cmd
    pkt[5 : 5 + len(payload)] = payload
    return bytes(pkt)


def hexdump(data, n=12):
    return " ".join(f"{b:02x}" for b in data[:n]) + " ..."


def send(fd, pkt, verbose=True):
    if verbose:
        print(">>", hexdump(pkt))
    os.write(fd, b"\x00" + pkt)


def recv(fd, seconds=1.0, cmd=None, verbose=True):
    """Le respostas ate achar a do comando pedido (ou expirar)."""
    end = time.time() + seconds
    while (left := end - time.time()) > 0:
        if not select.select([fd], [], [], left)[0]:
            break
        data = os.read(fd, 64)
        if verbose:
            print("<<", hexdump(data))
        if data[:4] == SYNC and (cmd is None or data[4] == cmd):
            return data
    return None


def cmd_status(fd, args):
    send(fd, build(CMD_STATUS))
    r = recv(fd, 2.0, CMD_STATUS)
    if not r:
        sys.exit("sem resposta do teclado")
    print(f"bateria: {r[5]}%   flag[6]: {r[6]}")


def cmd_light(fd, args):
    for name, val, lo, hi in (
        ("mode", args.mode, 1, 24),
        ("brightness", args.brightness, 1, BRIGHTNESS_MAX),
        ("speed", args.speed, 1, SPEED_MAX),
        ("direction", args.direction, 0, 1),
        ("color", args.color, 0, 9),
    ):
        if not lo <= val <= hi:
            sys.exit(f"--{name}={val} fora da faixa {lo}..{hi}")
    payload = bytes([args.mode - 1, args.brightness - 1, args.speed - 1,
                     args.direction, args.color])
    send(fd, build(CMD_LIGHT, payload))
    print(f"modo {args.mode} ({MODES.get(args.mode, '?')}), brilho "
          f"{args.brightness}, vel {args.speed}, dir {args.direction}, "
          f"cor {args.color}")


# Extraido do layouts/kb-k600t.xml do app Windows do fabricante. Só a tabela
# derivada mora aqui: o XML original é proprietario e nao vai no repo.
SLOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "key-slots.json")


def key_slots():
    """Codigo HID -> slot no frame de cores (o key_index do layout oficial)."""
    with open(SLOTS) as f:
        return {int(code, 16): slot for code, slot in json.load(f).items()}


def cmd_rgb(fd, args):
    """Pinta o teclado com uma cor RGB arbitraria (modo custom, por tecla)."""
    try:
        rgb = bytes.fromhex(args.color.lstrip("#"))
        assert len(rgb) == 3
    except (ValueError, AssertionError):
        sys.exit(f"cor invalida: {args.color!r} (use RRGGBB, ex: ff0080)")

    frame = bytearray(rgb * KEY_SLOTS)
    if args.only:
        slots = key_slots()
        frame = bytearray(KEY_SLOTS * 3)  # resto apagado
        for name in args.only.split(","):
            try:
                slot = slots[hid_code(name.strip())]
            except (KeyError, ValueError):
                sys.exit(f"tecla sem slot no layout: {name!r}")
            frame[slot * 3 : slot * 3 + 3] = rgb

    send(fd, build(CMD_LIGHT, bytes([MODE_CUSTOM - 1, args.brightness - 1,
                                     args.speed - 1, 0, 0])),
         verbose=args.verbose)
    send(fd, build(CMD_CUSTOM_BEGIN), verbose=args.verbose)
    send(fd, build(CMD_CUSTOM_PUSH), verbose=args.verbose)
    chunk = KEYS_PER_PACKET * 3
    for base in KEY_BANKS:
        for i in range(KEY_SLOTS // KEYS_PER_PACKET):
            time.sleep(PACKET_GAP)
            send(fd, build(base + i, frame[i * chunk : (i + 1) * chunk]),
                 verbose=args.verbose)
    alvo = f"em {args.only}" if args.only else f"em {KEY_SLOTS} teclas"
    print(f"cor #{rgb.hex()} aplicada {alvo} (brilho {args.brightness})")


def cmd_off(fd, args):
    """Apaga as teclas o maximo que o protocolo permite. 010101 e nao 000000:
    preto e' transparente no stream (o firmware le como "nao mexe nesta tecla").
    Brilho 1 porque o brilho e' PWM em cima do valor do frame -- e brilho 0
    (byte 0xFF) o firmware ignora. Off de verdade so existe no Fn+X."""
    args.color, args.only = "010101", None
    args.brightness, args.speed, args.verbose = 1, 4, False
    cmd_rgb(fd, args)


def cmd_key(fd, args):
    """Remapeia uma tecla (por padrao na camada Fn)."""
    try:
        key, target = hid_code(args.key), hid_code(args.to)
    except ValueError as e:
        sys.exit(str(e))
    layer = LAYERS[args.layer]
    time.sleep(0.016)  # o app espera 16ms entre teclas
    send(fd, build(CMD_KEY, bytes([layer + 1, key, target])))
    print(f"camada {args.layer}: {args.key} (0x{key:02x}) -> "
          f"{args.to} (0x{target:02x})")


def cmd_sleep(fd, args):
    """Tempo de inatividade antes do teclado dormir."""
    send(fd, build(CMD_SLEEP, bytes([SLEEP_VALUES[args.when]])))
    print(f"sleep time: {args.when}")


def cmd_listen(fd, args):
    print(f"escutando {args.seconds}s...")
    end = time.time() + args.seconds
    while (left := end - time.time()) > 0:
        if not select.select([fd], [], [], left)[0]:
            break
        print("<<", hexdump(os.read(fd, 64), 16))


def cmd_raw(fd, args):
    """Envia um pacote arbitrario. Para experimentos de mapeamento."""
    payload = bytes(int(x, 16) for x in args.payload)
    send(fd, build(int(args.rawcmd, 16), payload))
    recv(fd, args.wait)


def main():
    # self-check do framing (sync + posicao do comando/payload)
    p = build(CMD_LIGHT, bytes([6, 4, 2, 0, 1]))
    assert len(p) == 64 and p[:4] == SYNC
    assert p[4] == 7 and p[5:10] == bytes([6, 4, 2, 0, 1]) and p[10] == 0

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--device", help="/dev/hidrawN (default: detecta)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="bateria / estado")
    pl = sub.add_parser("light", help="configura a iluminacao")
    pl.add_argument("--mode", type=int, default=7,
                    help="1..24 (7=luz estatica; ver --list-modes)")
    pl.add_argument("--brightness", type=int, default=5, help=f"1..{BRIGHTNESS_MAX}")
    pl.add_argument("--speed", type=int, default=4, help=f"1..{SPEED_MAX}")
    pl.add_argument("--direction", type=int, default=0, help="0 ou 1")
    pl.add_argument("--color", type=int, default=1,
                    help="indice de cor 0..8 (0 costuma ser arco-iris)")
    pr = sub.add_parser("rgb", help="pinta tudo com uma cor RGB arbitraria")
    pr.add_argument("color", help="RRGGBB, ex: ff0080")
    pr.add_argument("--brightness", type=int, default=5, help=f"1..{BRIGHTNESS_MAX}")
    pr.add_argument("--speed", type=int, default=4, help=f"1..{SPEED_MAX}")
    pr.add_argument("--only", metavar="TECLAS",
                    help="acende so estas teclas (ex: esc ou esc,tab), o resto "
                         "fica apagado")
    pr.add_argument("--verbose", action="store_true", help="mostra cada pacote")
    sub.add_parser("off", help="apaga as teclas (a strip lateral e' firmware, "
                              "continua acesa e serve de indicador de ligado)")
    pk = sub.add_parser("key", help="remapeia uma tecla")
    pk.add_argument("key", help="tecla fisica (ex: z, f5, 0x1d)")
    pk.add_argument("to", help="funcao nova (ex: printscreen, home, 0x46)")
    pk.add_argument("--layer", choices=list(LAYERS), default="fn")
    ps = sub.add_parser("sleep", help="tempo para o teclado dormir")
    ps.add_argument("when", choices=list(SLEEP_VALUES))
    sub.add_parser("modes", help="lista os modos de iluminacao")
    ls = sub.add_parser("listen", help="escuta o canal vendor")
    ls.add_argument("--seconds", type=float, default=15)
    rw = sub.add_parser("raw", help="envia pacote arbitrario (experimental)")
    # nao pode ser "cmd": colidiria com o dest do subparser e quebra o dispatch
    rw.add_argument("rawcmd", metavar="CMD", help="byte de comando em hex, ex: 0e")
    rw.add_argument("payload", nargs="*", help="bytes hex do payload")
    rw.add_argument("--wait", type=float, default=1.5)
    args = ap.parse_args()

    if args.cmd == "modes":
        for m, name in MODES.items():
            print(f"{m:3d}  {name}")
        return

    dev = args.device or find_device()
    if not dev:
        sys.exit("F75 nao encontrado (2.4G ou cabo). Dongle plugado?")
    try:
        fd = os.open(dev, os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        sys.exit(f"sem permissao em {dev} — instale 99-freewolf-f75.rules")
    try:
        {"status": cmd_status, "light": cmd_light, "rgb": cmd_rgb,
         "off": cmd_off, "key": cmd_key, "sleep": cmd_sleep,
         "listen": cmd_listen, "raw": cmd_raw}[args.cmd](fd, args)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
