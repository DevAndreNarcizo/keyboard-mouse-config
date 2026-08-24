"""Qualquer periférico que o kernel já exponha em /sys/class/power_supply.

Fonte genérica. Pega o que fala a página de bateria padrão do HID — muitos
teclados e mouses sem fio com receptor próprio caem aqui — sem precisar de
protocolo de fabricante. Zero dependência: é leitura de arquivo.

**Só `scope=Device`.** A bateria do próprio computador tem `scope=System` (ou
nenhum) e fica de fora de propósito: o GNOME já a mostra, e repeti-la no widget
seria ruído. Carregador (`type=Mains`/`USB`) também sai — é fonte, não bateria.
"""
import glob
import os

from .. import Reading, pct_ok

NAME = "Kernel (power_supply)"
SOURCE = True
CAPS = ("battery",)

PALAVRA_KIND = (
    ("mouse", "mouse"), ("keyboard", "keyboard"), ("teclado", "keyboard"),
    ("headset", "headset"), ("headphone", "headset"), ("gamepad", "gamepad"),
    ("controller", "gamepad"), ("stylus", "other"), ("pen", "other"),
)


def _ler(base, nome):
    try:
        with open(os.path.join(base, nome)) as f:
            return f.read().strip()
    except OSError:
        return ""


def kind_de(texto):
    baixo = texto.lower()
    for palavra, kind in PALAVRA_KIND:
        if palavra in baixo:
            return kind
    return "other"


def nome_de(base):
    """Nome legível: o do aparelho HID pai, se houver; senão o do power_supply."""
    for onde in ("device/uevent", "device/device/uevent"):
        for linha in _ler(base, onde).splitlines():
            if linha.startswith("HID_NAME="):
                return linha.split("=", 1)[1]
    return _ler(base, "model_name") or os.path.basename(base)


def discover():
    out = []
    for base in sorted(glob.glob("/sys/class/power_supply/*")):
        if _ler(base, "scope") != "Device":
            continue
        if _ler(base, "type") in ("Mains", "USB"):
            continue
        if not _ler(base, "capacity"):
            continue
        nome = nome_de(base)
        out.append(("ps_" + os.path.basename(base), nome, kind_de(nome), base))
    return out


def battery(base, wait=0):
    """`capacity` e `status` do sysfs.

    `wait` é ignorado, e não por descuido: aqui o valor está sempre no arquivo,
    sem handshake nem anúncio para esperar. O parâmetro existe porque o contrato
    o passa a todo módulo.
    """
    cap = _ler(base, "capacity")
    if not cap.isdigit() or not pct_ok(int(cap)):
        return None
    status = _ler(base, "status")
    carga = 1 if status == "Charging" else (0 if status else None)
    return Reading(int(cap), carga, b"")
