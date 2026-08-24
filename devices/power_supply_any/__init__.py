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


# bInterfaceProtocol da classe HID: é o que o próprio aparelho declara ser, e
# vale mais que adivinhar pelo nome — "MX Master 3" não tem a palavra "mouse".
PROTO_KIND = {"1": "keyboard", "2": "mouse"}


def kind_por_nome(texto):
    """Palpite pelo nome. Último recurso: nome é livre e marca nenhuma promete
    conter a palavra certa."""
    baixo = texto.lower()
    for palavra, kind in PALAVRA_KIND:
        if palavra in baixo:
            return kind
    return "other"


def kind_de(base, nome=""):
    """Categoria do aparelho: primeiro o que ele declara, depois o nome.

    Sobe a árvore do sysfs procurando `bInterfaceProtocol` — a interface USB HID
    diz `1` para teclado e `2` para mouse. É informação do aparelho, não palpite
    sobre a string de marketing dele.
    """
    caminho = os.path.realpath(base)
    for _ in range(6):  # power_supply -> hid -> interface USB, com folga
        proto = _ler(caminho, "bInterfaceProtocol")
        if proto in PROTO_KIND:
            return PROTO_KIND[proto]
        pai = os.path.dirname(caminho)
        if pai == caminho:
            break
        caminho = pai
    return kind_por_nome(nome)


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
        out.append(("ps_" + os.path.basename(base), nome,
                    kind_de(base, nome), base))
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
