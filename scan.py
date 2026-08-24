"""`kmctl scan` — este aparelho vai aparecer no painel? E se não, por quê?

Existe porque a resposta a "meu próximo mouse funciona?" é **depende da marca**, e
sem uma ferramenta a única saída seria perguntar a alguém. Aqui a máquina
responde, e diz qual dos caminhos falta:

1. **Bluetooth** — funciona sozinho se o firmware reportar bateria. A maioria dos
   aparelhos modernos reporta.
2. **Página de bateria padrão do HID** — funciona sozinho: o kernel cria a
   entrada em `/sys/class/power_supply` e a fonte genérica a lista. Muito
   teclado/mouse de receptor 2.4G segue o padrão.
3. **Protocolo de fabricante** — não funciona sozinho, e não há como funcionar:
   a bateria só sai por opcode que ninguém documentou. Precisa de um diretório em
   `devices/`, ou seja engenharia reversa. É o caso do Delux M800 PRO e do
   Attack Shark K86 — e é a razão de este repo existir.

O scan não conserta nada; ele diz em qual dos três o aparelho caiu.
"""
import glob
import os

import devices

# Página 0x06 (Generic Device Controls) + usage 0x20 (Battery Strength). É o que
# faz o kernel criar power_supply sozinho — ver hidinput_setup_battery no kernel.
BAT_HID = (b"\x05\x06", b"\x09\x20")
VENDOR = (b"\x06\x00\xff", b"\x06\xff\xff")


def _uevent(caminho):
    try:
        with open(caminho) as f:
            return dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
    except OSError:
        return {}


def hid_fisicos():
    """Um registro por aparelho USB/HID físico, não por interface.

    Agrupa pelo prefixo do `HID_PHYS` (`usb-...-11/input1` -> `usb-...-11`):
    um receptor expõe três ou quatro interfaces e listá-las soltas transformaria
    a saída em ruído, quando a pergunta é sobre o aparelho.
    """
    grupos = {}
    for uev in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        d = os.path.dirname(uev)
        info = _uevent(uev)
        phys = info.get("HID_PHYS", "").split("/")[0] or d
        try:
            with open(os.path.join(d, "report_descriptor"), "rb") as f:
                desc = f.read()
        except OSError:
            desc = b""
        g = grupos.setdefault(phys, {
            "nome": info.get("HID_NAME", "?"), "hid_id": info.get("HID_ID", ""),
            "bat_hid": False, "vendor": False, "power_supply": False,
            "ifaces": [],
        })
        g["ifaces"].append(os.path.basename(os.path.dirname(d)))
        if all(p in desc for p in BAT_HID):
            g["bat_hid"] = True
        if any(p in desc for p in VENDOR):
            g["vendor"] = True
        if glob.glob(os.path.join(d, "power_supply", "*")):
            g["power_supply"] = True
    return grupos


def _ids_dos_modelos():
    """Todo HID_ID que algum diretório de modelo já reivindica."""
    ids = set()
    for mod in devices.modules():
        if not getattr(mod, "SOURCE", False):
            ids |= set(getattr(mod, "IDS", ()))
    return ids


def varrer():
    """[(nome, detalhe, veredito)] — a resposta completa, pronta para imprimir."""
    cobertos = {f.handle for f in devices.present()}
    nomes_cobertos = {f.name for f in devices.present()}
    reivindicados = _ids_dos_modelos()
    out = []

    for phys, g in sorted(hid_fisicos().items()):
        hid_id = g["hid_id"]
        curto = ":".join(p.lstrip("0") or "0" for p in hid_id.split(":")[1:])
        detalhe = f"{curto}  {phys}"
        ja = any(f"/dev/{i}" in cobertos for i in g["ifaces"])
        if ja:
            out.append((g["nome"], detalhe, "APARECE — por diretório de modelo"))
        elif g["power_supply"]:
            out.append((g["nome"], detalhe, "APARECE — o kernel expõe a bateria"))
        elif g["bat_hid"]:
            out.append((g["nome"], detalhe,
                        "declara bateria no HID mas o kernel não criou "
                        "power_supply — caso estranho, vale investigar"))
        elif any(i in reivindicados for i in (hid_id,)):
            out.append((g["nome"], detalhe,
                        "tem diretório de modelo, mas não está respondendo agora"))
        elif g["vendor"]:
            out.append((g["nome"], detalhe,
                        "NÃO aparece — tem canal de fabricante e não declara "
                        "bateria: candidato a diretório em devices/ "
                        "(precisa de engenharia reversa)"))
        else:
            out.append((g["nome"], detalhe,
                        "NÃO aparece — não expõe bateria por caminho nenhum. "
                        "Pode ser com fio, ou simplesmente não ter bateria"))

    for path, ifaces in sorted(devices.bluez_objects().items()):
        dev = ifaces.get("org.bluez.Device1")
        if not dev:
            continue
        nome = dev.get("Alias") or dev.get("Address", "?")
        detalhe = f"{dev.get('Address', '?')}  bluetooth"
        if path in cobertos or nome in nomes_cobertos:
            out.append((nome, detalhe, "APARECE — Bluetooth com bateria"))
        elif not dev.get("Connected"):
            out.append((nome, detalhe,
                        "pareado e desconectado — conecte para ver a bateria"))
        elif "org.bluez.Battery1" not in ifaces:
            out.append((nome, detalhe,
                        "NÃO aparece — conectado, mas o firmware dele não "
                        "reporta bateria ao BlueZ. Não há o que fazer daqui"))
        else:
            out.append((nome, detalhe, "APARECE — Bluetooth com bateria"))
    return out
