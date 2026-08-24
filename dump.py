"""`kmctl dump` — tudo o que se precisa saber de um aparelho novo, num comando.

Existe porque mapear o Delux M800 PRO em 2026-08-24 custou dezenas de comandos à
mão: decodificar descritor, achar a interface certa, sondar Feature, capturar o
canal com uma testemunha para separar "mudo" de "parado". Este módulo faz isso
sozinho e cospe um texto para colar.

## O que ele NÃO faz, de propósito

**Não escuta interface que declara teclado.** Ler o stream de uma interface de
teclado é gravar o que o dono digita — foi o risco concreto que o M800 PRO
expôs, porque nele a interface com o canal de fabricante é *também* a de teclado.
Aqui essas interfaces entram no relatório com os flags e o descritor, mas o
`read()` não acontece.

**Não manda opcode desconhecido.** A única escrita é a consulta de status da
família que o repo já conhece (`0x20` no report `0x0c`), e só onde o descritor
declara esse report. Fuzzear opcode em aparelho alheio pode desconfigurá-lo.
"""
import fcntl
import glob
import os
import select
import time

import devices
from devices import vendor_probe

# Assinaturas das famílias que este repo já sabe ler, para o dump dizer
# "isto parece X" em vez de deixar o humano comparar hex na mão.
FAMILIAS_ANUNCIO = (
    ("AJAZZ/Smailwolf", lambda p: len(p) > 10 and p[0] == 0xAA and p[1] == 0xFA),
    ("Delux M900Pro", lambda p: len(p) >= 5 and p[0] == 0x03),
    ("FreeWolf/Semico", lambda p: len(p) >= 5 and bytes(p[:4]) == bytes.fromhex("aa55cc33")),
)

PAG_TECLADO = b"\x05\x07"
PAG_BATERIA = (b"\x05\x06", b"\x09\x20")
PAG_VENDOR = (b"\x06\x00\xff", b"\x06\xff\xff")


def _ler(caminho):
    try:
        with open(caminho) as f:
            return f.read().strip()
    except OSError:
        return ""


def _uevent(caminho):
    try:
        with open(caminho) as f:
            return dict(l.split("=", 1) for l in f.read().splitlines() if "=" in l)
    except OSError:
        return {}


def interfaces():
    """[(hidraw, info)] de tudo, com os flags que importam por interface."""
    out = []
    for uev in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        d = os.path.dirname(uev)
        nome = os.path.basename(os.path.dirname(d))
        info = _uevent(uev)
        try:
            with open(os.path.join(d, "report_descriptor"), "rb") as f:
                desc = f.read()
        except OSError:
            desc = b""
        out.append((nome, {
            "hid_id": info.get("HID_ID", ""),
            "hid_name": info.get("HID_NAME", ""),
            "phys": info.get("HID_PHYS", ""),
            "sysfs": d,
            "desc": desc,
            "teclado": PAG_TECLADO in desc,
            "bateria_hid": all(p in desc for p in PAG_BATERIA),
            "vendor": any(p in desc for p in PAG_VENDOR),
            "familia_0x0c": vendor_probe.declara_canal(desc),
            "power_supply": bool(glob.glob(os.path.join(d, "power_supply", "*"))),
            "perm": _perm("/dev/" + nome),
        }))
    return out


def _perm(dev):
    try:
        st = os.stat(dev)
    except OSError:
        return "ausente"
    return f"{oct(st.st_mode & 0o777)[2:]} " + (
        "legível" if os.access(dev, os.R_OK) else "SEM PERMISSÃO (falta regra udev)")


def usb_de(sysfs):
    """VID:PID, strings e protocolos das interfaces do aparelho USB pai."""
    caminho = os.path.realpath(sysfs)
    for _ in range(6):
        if _ler(os.path.join(caminho, "idVendor")):
            protos = {}
            for iface in sorted(glob.glob(os.path.join(caminho, "*:*.*"))):
                p = _ler(os.path.join(iface, "bInterfaceProtocol"))
                if p:
                    protos[os.path.basename(iface)] = int(p, 10)
            return {
                "vid_pid": f"{_ler(os.path.join(caminho, 'idVendor'))}:"
                           f"{_ler(os.path.join(caminho, 'idProduct'))}",
                "fabricante": _ler(os.path.join(caminho, "manufacturer")),
                "produto": _ler(os.path.join(caminho, "product")),
                "serial": _ler(os.path.join(caminho, "serial")) or "(vazio)",
                "bcd": _ler(os.path.join(caminho, "bcdDevice")),
                "protocolos": protos,
            }
        pai = os.path.dirname(caminho)
        if pai == caminho:
            break
        caminho = pai
    return {}


def escutar(alvos, segundos):
    """{hidraw: [frames]} — só das interfaces SEM teclado declarado.

    A testemunha importa: capturar junto o canal de movimento é o que separa
    "canal mudo" de "aparelho parado". Sem isso, silêncio engana.
    """
    fds, capturado = {}, {}
    for nome in alvos:
        try:
            fds[os.open("/dev/" + nome, os.O_RDONLY | os.O_NONBLOCK)] = nome
        except OSError as e:
            capturado[nome] = [f"(não abriu: {e})"]
    if not fds:
        return capturado
    fim = time.time() + segundos
    contagem = {n: 0 for n in fds.values()}
    try:
        while (resta := fim - time.time()) > 0:
            for fd in select.select(list(fds), [], [], resta)[0]:
                nome = fds[fd]
                try:
                    pkt = os.read(fd, 64)
                except OSError:
                    continue
                if not pkt:
                    continue
                contagem[nome] += 1
                linhas = capturado.setdefault(nome, [])
                if len(linhas) < 8:  # amostra, não log completo
                    familia = [f for f, teste in FAMILIAS_ANUNCIO if teste(pkt)]
                    marca = f"   <- parece {', '.join(familia)}" if familia else ""
                    linhas.append(f"{pkt.hex(' ')}{marca}")
    finally:
        for fd in fds:
            os.close(fd)
    for nome, n in contagem.items():
        capturado.setdefault(nome, []).append(f"(total: {n} frames em {segundos}s)")
    return capturado


def relatorio(segundos=20, echo=print):
    ifaces = interfaces()
    cobertos = {f.handle for f in devices.present()}
    echo("=" * 72)
    echo("kmctl dump — cole isto inteiro ao pedir suporte para um aparelho novo")
    echo("=" * 72)

    grupos = {}
    for nome, i in ifaces:
        grupos.setdefault(i["phys"].split("/")[0] or nome, []).append((nome, i))

    for phys, itens in sorted(grupos.items()):
        primeiro = itens[0][1]
        usb = usb_de(primeiro["sysfs"])
        echo("")
        echo(f"### {primeiro['hid_name'] or '?'}")
        echo(f"    HID_ID     {primeiro['hid_id']}")
        echo(f"    USB        {usb.get('vid_pid', '?')}  "
             f"{usb.get('fabricante', '')} / {usb.get('produto', '')}")
        echo(f"    serial     {usb.get('serial', '?')}   bcdDevice "
             f"{usb.get('bcd', '?')}")
        echo(f"    porta      {phys}")
        if usb.get("protocolos"):
            legenda = {0: "nenhum", 1: "teclado", 2: "mouse"}
            echo("    interfaces " + ", ".join(
                f"{k}={legenda.get(v, v)}" for k, v in usb["protocolos"].items()))
        for nome, i in itens:
            flags = [k for k in ("teclado", "bateria_hid", "vendor",
                                 "familia_0x0c", "power_supply") if i[k]]
            ja = "/dev/" + nome in cobertos
            echo(f"    {nome:9} {i['perm']:34} "
                 f"{'[EM USO PELO REPO] ' if ja else ''}{', '.join(flags) or '—'}")
            echo(f"      descritor ({len(i['desc'])}B): "
                 f"{i['desc'][:48].hex(' ')}{'…' if len(i['desc']) > 48 else ''}")

    echo("")
    echo("### sonda da família conhecida (0x0c / opcode 0x20)")
    achou = False
    for nome, i in ifaces:
        if not i["familia_0x0c"]:
            continue
        achou = True
        got = vendor_probe._perguntar("/dev/" + nome)
        echo(f"    {nome}: {got if got else 'não respondeu (protocolo é outro)'}")
    if not achou:
        echo("    nenhuma interface declara o report 0x0c — nada foi enviado")

    echo("")
    echo(f"### escuta de {segundos}s (interface com teclado é PULADA de propósito)")
    alvos = [n for n, i in ifaces if not i["teclado"] and os.path.exists("/dev/" + n)]
    pulados = [n for n, i in ifaces if i["teclado"]]
    if pulados:
        echo(f"    puladas por declararem teclado: {', '.join(pulados)}")
    echo("    MEXA O MOUSE / USE O APARELHO agora, senão o silêncio não diz nada")
    for nome, linhas in sorted(escutar(alvos, segundos).items()):
        echo(f"    {nome}:")
        for l in linhas:
            echo(f"      {l}")

    echo("")
    echo("### Bluetooth")
    objs = devices.bluez_objects()
    if not objs:
        echo("    BlueZ não respondeu (bluetoothd parado, ou busctl ausente)")
    for path, ifs in sorted(objs.items()):
        dev = ifs.get("org.bluez.Device1")
        if not dev:
            continue
        echo(f"    {dev.get('Address')}  {dev.get('Alias')!r}")
        echo(f"      conectado={dev.get('Connected')}  "
             f"bateria={'org.bluez.Battery1' in ifs}  "
             f"icon={dev.get('Icon')!r}  modalias={dev.get('Modalias')!r}")

    echo("")
    echo("### o que o repo vê agora")
    for f in devices.present():
        echo(f"    {f.ident:24} {f.name:24} {f.kind:9} {f.handle}")
    if not devices.present():
        echo("    nada com bateria")
    echo("")
    echo("=" * 72)
    return 0
