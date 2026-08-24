"""Sonda genérica da família Delux/TeLink (report `0x0c`, opcode `0x20`).

Serve ao objetivo de "só conectar e funcionar" **por família**, não por modelo:
qualquer aparelho que fale este protocolo aparece sozinho, sem ninguém escrever
um diretório. Foi mapeada byte a byte no Delux M800 PRO em 2026-08-24, e é uma
família comum em mouse sem fio barato — o VID `248a` é da TeLink, que é o chip do
dongle, não a marca do mouse.

## Por que só esta família

Este repo conhece três protocolos de request/response. Sondar às cegas só é
aceitável quando a resposta **se identifica**, porque a alternativa é inventar
percentual:

- **esta** (`0x0c`/`0x20`): valida quatro coisas independentes — o opcode ecoado
  no byte 2, o seq ecoado no byte 4, quatro bytes ASCII imprimíveis em 8..11 (o
  modelo, `M802` no M800 PRO) e o percentual em 1..100. Falso positivo exigiria
  coincidência nos quatro.
- **ROYUAN/Attack Shark** (K86): a resposta valida *só* `1 <= byte[1] <= 100`.
  Sem assinatura nenhuma. Sondar isso daria número para qualquer aparelho que
  devolvesse 65 bytes. **Deliberadamente fora.**
- **FreeWolf/Semico** (`aa 55 cc 33`): tem cabeçalho e eco de comando, seria
  segura — mas o hardware não está aqui para testar a sonda, e sonda que escreve
  em aparelho desconhecido sem teste é o tipo de coisa que este repo não faz.

## Por que a escrita é segura

Antes de mandar qualquer byte, o descritor tem que **declarar o report `0x0c` com
Feature**. Aparelho que não declara nem recebe a escrita: o pedido morre no
kernel ou volta `EPIPE`. Ou seja o filtro é estrutural, não otimista — e o opcode
`0x20` é consulta, não configuração (os opcodes que mudam DPI, cor e remap são
outros, e não estão aqui).

Um diretório de modelo continua valendo a pena para quem tem caps de escrita ou
um `WONT` a declarar; quando existe, ele **ganha** desta sonda, porque o
`present()` deixa os modelos reservarem o handle primeiro.
"""
import fcntl
import glob
import os
import string

from .. import Reading, hid_get_feature, hid_set_feature, modules, pct_ok

NAME = "Sonda de fabricante (família Delux/TeLink)"
SOURCE = True
CAPS = ("battery",)

REPORT, SIZE, OP_STATUS = 0x0C, 33, 0x20
SEQ_TRIES = 4
IMPRIMIVEL = set(bytes(string.ascii_letters + string.digits + "-_ ", "ascii"))

_memo = {}  # {frozenset(candidatos): [(ident, nome, kind, handle)]}


def _uevent(caminho):
    try:
        with open(caminho) as f:
            return dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
    except OSError:
        return {}


def declara_canal(desc):
    """O descritor declara o report 0x0c com item Feature?

    É a pré-condição estrutural que faz a sonda não ser um tiro no escuro:
    `85 0c` é Report ID 0x0c e `b1 02` é Feature. Sem os dois, nada é enviado.
    """
    return b"\x85\x0c" in desc and b"\xb1\x02" in desc


def _reivindicados():
    ids = set()
    for mod in modules():
        if not getattr(mod, "SOURCE", False):
            ids |= set(getattr(mod, "IDS", ()))
    return ids


def candidatos():
    """[(handle, hid_id, base_sysfs)] das interfaces que vale sondar."""
    reivindicados = _reivindicados()
    out = []
    for uev in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        d = os.path.dirname(uev)
        info = _uevent(uev)
        hid_id = info.get("HID_ID", "")
        # modelo com diretório próprio não é sondado: ele já sabe fazer melhor,
        # e escrever à toa num aparelho que já funciona não tem upside
        if any(i in hid_id for i in reivindicados):
            continue
        try:
            with open(os.path.join(d, "report_descriptor"), "rb") as f:
                desc = f.read()
        except OSError:
            continue
        if not declara_canal(desc):
            continue
        out.append(("/dev/" + os.path.basename(os.path.dirname(d)), hid_id, d))
    return out


def valida(frame, seq):
    """(tag, pct) se o frame é resposta desta família; None se não é.

    Quatro condições independentes. É o que separa "identifiquei o protocolo" de
    "achei bytes que cabem".
    """
    if len(frame) < 20 or frame[2] != OP_STATUS or frame[4] != seq:
        return None
    tag = bytes(frame[8:12])
    if not tag or not all(b in IMPRIMIVEL for b in tag):
        return None
    if not pct_ok(frame[18]):
        return None
    return tag.decode("ascii").strip(), frame[18]


def _perguntar(path):
    """(tag, pct) ou None. Um SET_FEATURE de consulta e um GET_FEATURE."""
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return None
    try:
        for seq in range(1, SEQ_TRIES + 1):
            req = bytearray(SIZE)
            req[0], req[1], req[2], req[4] = REPORT, 0x01, OP_STATUS, seq
            try:
                fcntl.ioctl(fd, hid_set_feature(SIZE), req)
                ans = bytearray(SIZE)
                ans[0] = REPORT
                fcntl.ioctl(fd, hid_get_feature(SIZE), ans)
            except OSError:
                return None  # EPIPE: não é desta família
            got = valida(bytes(ans), seq)
            if got:
                return got
        return None
    finally:
        os.close(fd)


def kind_do_usb(base):
    """Categoria pelas interfaces USB do mesmo aparelho.

    Estes receptores expõem mouse **e** teclado (o teclado serve às teclas
    mapeadas em botão), então quando os dois existem a resposta é ambígua e a
    preferência vai para mouse: esta família é de mouse sem fio. Fica registrado
    como heurística — num dongle de teclado que também exponha mouse, erra o
    ícone. Erra o ícone, não o número.
    """
    usb = os.path.realpath(base)
    for _ in range(4):
        protos = set()
        for iface in glob.glob(os.path.join(os.path.dirname(usb), "*:*.*")):
            try:
                with open(os.path.join(iface, "bInterfaceProtocol")) as f:
                    # o sysfs escreve "02", não "2" — comparar string crua não casa
                    protos.add(int(f.read().strip(), 10))
            except (OSError, ValueError):
                pass
        if protos:
            if 2 in protos:
                return "mouse"
            if 1 in protos:
                return "keyboard"
            return "other"
        usb = os.path.dirname(usb)
    return "other"


def discover():
    achados = candidatos()
    chave = frozenset(h for h, _, _ in achados)
    # Memo pelo CONJUNTO de candidatos, não por processo: o `watch` vive muito
    # tempo, e sem invalidação um aparelho novo nunca seria sondado. Mudou o
    # conjunto, sonda de novo; igual, devolve o que já se sabe.
    if chave in _memo:
        return _memo[chave]
    out = []
    for handle, hid_id, base in achados:
        got = _perguntar(handle)
        if not got:
            continue
        tag, _ = got
        # HID_ID vem como "0003:0000248A:00005B2F"; interessa vid:pid em 4 dígitos
        partes = [x[-4:].lower() for x in hid_id.split(":")[1:]]
        vid_pid = ":".join(partes)
        curto = "".join(partes)
        # a tag entra no ident porque dois modelos da mesma família dividem o
        # VID:PID do dongle — é ela que os separa no histórico
        ident = f"vp_{curto}_{tag.lower()}" if tag else f"vp_{curto}"
        out.append((ident, f"{tag} ({vid_pid})", kind_do_usb(base), handle))
    _memo.clear()
    _memo[chave] = out
    return out


def battery(path, wait=0):
    """`wait` é ignorado: a resposta é imediata neste protocolo."""
    got = _perguntar(path)
    if not got:
        return None
    return Reading(got[1], None, b"")
