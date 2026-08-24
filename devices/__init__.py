"""Descoberta do que está plugado e tem bateria.

Dois tipos de módulo moram em `devices/`, e este arquivo não conhece nenhum
deles pelo nome — varre o diretório e usa o que cada um declarar:

- **modelo** (`delux_m800pro`, `attackshark_k86`, …): sabe falar um protocolo
  proprietário que mais ninguém no sistema entende. Declara `IDS` e um `find()`.
  É a razão de o repo existir: o M800 PRO não aparece no UPower nem no
  `power_supply`, porque a bateria dele só sai por opcode de fabricante.
- **fonte** (`bluez_any`, `power_supply_any`): não sabe modelo nenhum, sabe um
  barramento. Declara `discover()` e devolve **quantos aparelhos achar**. É o que
  faz um teclado sem fio novo aparecer sozinho, sem ninguém escrever um
  diretório para ele.

Aparelho com fio, ou sem bateria, não aparece em nenhuma das duas — não por
regra especial, mas porque não tem o que reportar.

O contrato está em `devices/README.md`.
"""
import collections
import glob
import importlib
import json
import os
import pkgutil
import subprocess
import sys

# O que uma leitura de bateria devolve. `raw` é o frame cru (b"" se o modelo não
# expõe um): é ele que alimenta a tabela `raw` do histórico e o `kmctl raw`,
# que é como se descobre o byte de bateria de um modelo novo.
Reading = collections.namedtuple("Reading", "pct charging raw")

# Um aparelho concreto que está aqui agora. `mod` é quem sabe ler a bateria dele,
# `handle` é o que o `mod.battery()` precisa (um /dev/hidrawN, um object path do
# BlueZ, um diretório do sysfs — opaco de propósito), e `ident` é a chave estável
# que vai para o banco e para o cache do painel.
Found = collections.namedtuple("Found", "mod ident name kind handle")

# Vocabulário de categorias. Serve para o painel escolher ícone; não é taxonomia
# com pretensão. "other" é o destino honesto de qualquer coisa que uma fonte
# genérica ache e não saiba classificar — melhor que forçar num rótulo errado.
KINDS = ("keyboard", "mouse", "headset", "phone", "gamepad", "other")


def hid_ioc(nr, size):
    """Número de ioctl do hidraw (`linux/hidraw.h`): `_IOC(READ|WRITE,'H',nr,n)`.

    Estava calculado em dois módulos — no K86 com `0x48`, no M800 PRO com
    `ord("H")`, que é a mesma constante escrita de dois jeitos. Mora aqui porque
    é transporte HID, que é o que este arquivo já guarda (`find_iface`).
    """
    return (3 << 30) | (size << 16) | (ord("H") << 8) | nr


def hid_set_feature(size):
    """HIDIOCSFEATURE: escreve um report Feature."""
    return hid_ioc(0x06, size)


def hid_get_feature(size):
    """HIDIOCGFEATURE: lê um report Feature."""
    return hid_ioc(0x07, size)


def pct_ok(v):
    """Percentual crível: 1..100.

    Uma regra num lugar. Estava copiada em seis parsers, e o lado Bluetooth
    tinha divergido para `0..100` — o que fazia `bluez_pct` aceitar 0 e os
    chamadores dele descartarem, cada um com a sua ideia.

    **Zero fica de fora de propósito.** Em todo aparelho visto aqui, 0 é o valor
    que aparece quando o canal não sabe responder, não uma bateria realmente
    zerada — aparelho com 0% de verdade está desligado e não reporta nada.
    """
    return isinstance(v, int) and 1 <= v <= 100


def find_iface(ids, writable=False, at_start=False):
    """/dev/hidrawN do canal vendor desses HID_ID. None se não estiver plugado.

    Os periféricos expõem a página vendor em mais de uma interface e escolher
    errado tem consequência real: no K86 uma delas carrega o NKRO, ou seja,
    tudo o que o dono digita.

    - `writable`: só serve a interface com item Feature (`0xB1`) ou Output
      (`0x91`). É a regra dos modelos que precisam de escrita (K86, M900Pro).
    - `at_start`: o descritor tem que **começar** com a página vendor. Regra
      original do F75 e do AJ139. A versão solta pode casar com outra interface,
      e esse hardware não está na mesa para conferir — quem tem, que afrouxe.
    """
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        with open(uevent) as f:
            if not any(i in f.read() for i in ids):
                continue
        d = os.path.dirname(uevent)
        with open(os.path.join(d, "report_descriptor"), "rb") as f:
            desc = f.read()
        if at_start:
            if not (desc[0] == 0x06 and desc[2] == 0xFF):
                continue
        elif not (b"\x06\x00\xff" in desc or b"\x06\xff\xff" in desc):
            continue
        if writable and not (b"\xb1\x02" in desc or b"\x91\x02" in desc):
            continue
        return "/dev/" + os.path.basename(os.path.dirname(d))
    return None


# ---------------------------------------------------------------- Bluetooth
#
# O segundo transporte. Aqui não há engenharia reversa: o BlueZ já normaliza a
# bateria de qualquer aparelho que exponha `org.bluez.Battery1`, então o que mora
# no diretório do modelo é só o identificador — o `Modalias`, que é o análogo
# Bluetooth do VID:PID. É a mesma divisão do lado HID: `find_iface` sabe o
# transporte, o diretório sabe qual aparelho é.
#
# Falar D-Bus em stdlib puro não é razoável, então isto chama o `busctl`, que vem
# com o systemd — não é pacote Python, é uma CLI que está em qualquer Ubuntu. Se
# ela não existir, ou o bluetoothd estiver parado, tudo aqui devolve vazio e o
# resto do repo segue funcionando.

_bluez_memo = None


def _busctl(*args):
    try:
        out = subprocess.run(("busctl", "--json=short") + args,
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    try:
        return json.loads(out.stdout)
    except ValueError:
        return None


def bluez_objects():
    """{path: {interface: {prop: valor}}} de tudo que o BlueZ conhece. {} se não
    der para falar com ele.

    Memoizado por processo. O `kmctl` é one-shot, então não envelhece; num
    processo longo envelheceria, e é por isso que quem lê **percentual** usa
    `bluez_pct`, que sempre vai ao barramento.
    """
    global _bluez_memo
    if _bluez_memo is not None:
        return _bluez_memo
    got = _busctl("call", "org.bluez", "/",
                  "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    try:
        crus = got["data"][0]
    except (TypeError, KeyError, IndexError):
        _bluez_memo = {}
        return _bluez_memo
    # Um `try` por objeto, e não um em volta de tudo: uma propriedade malformada
    # num objeto qualquer da árvore (um adaptador, uma baliza LE) apagaria todos
    # os aparelhos Bluetooth de uma vez, em silêncio e sem nova tentativa,
    # porque o resultado vazio fica memoizado.
    out = {}
    for path, ifaces in crus.items():
        try:
            out[path] = {i: {k: v["data"] for k, v in props.items()}
                         for i, props in ifaces.items()}
        except (TypeError, KeyError, AttributeError) as e:
            print(f"devices: objeto {path} do BlueZ ignorado ({e})",
                  file=sys.stderr)
    _bluez_memo = out
    return _bluez_memo


def bluez_pct(path):
    """Percentual que o BlueZ reporta agora, ou None. Não usa o memo."""
    got = _busctl("get-property", "org.bluez", path,
                  "org.bluez.Battery1", "Percentage")
    try:
        pct = int(got["data"])
    except (TypeError, KeyError, ValueError):
        return None
    return pct if pct_ok(pct) else None


def modules():
    """Todos os modelos suportados, em ordem de id. Um que estoure ao importar
    é pulado com aviso: o modelo de outra pessoa não derruba o seu cron."""
    out = []
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"{__name__}.{info.name}")
        except Exception as e:  # noqa: BLE001 - qualquer coisa, é código de terceiro
            print(f"devices: {info.name} não carregou ({e})", file=sys.stderr)
            continue
        if hasattr(mod, "NAME"):
            mod.ID = info.name
            out.append(mod)
    return out


def _achados_de(mod, fonte):
    """O que este módulo diz que está aqui, como [(ident, nome, kind, handle)].

    Erro de um módulo não derruba os outros: o `probe` do cron não pode morrer
    porque o diretório de outra pessoa estourou.
    """
    qual = "discover()" if fonte else "find()"
    try:
        if fonte:
            return list(mod.discover())
        handle = mod.find()
        return [(mod.ID, mod.NAME, mod.KIND, handle)] if handle else []
    except Exception as e:  # noqa: BLE001 - módulo de terceiro, qualquer coisa
        print(f"devices: {mod.ID}.{qual} falhou ({e})", file=sys.stderr)
        return []


def present():
    """Tudo que está aqui agora e tem bateria, como lista de `Found`.

    Módulos de modelo vêm primeiro e **reservam** o handle deles; depois as
    fontes genéricas entram com o que sobrou. É o que garante que um aparelho
    visto pelos dois lados apareça uma vez, com o nome e as caps do modelo.

    Houve um parâmetro `kind` aqui. Foi removido: ficou sem chamador quando o
    `pick()` saiu, **e carregava um bug** — o filtro rodava antes do
    `vistos.add`, então um modelo descartado pela categoria não reservava o
    handle dele, e a fonte genérica entrava com o mesmo aparelho. Quem precisa
    filtrar filtra na lista devolvida.

    A dedução só funciona quando os dois lados falam do mesmo handle. Forçar
    identidade entre barramentos diferentes daria mais erro que acerto.
    """
    mods = modules()
    out, vistos = [], set()
    for fonte in (False, True):
        for mod in mods:
            if bool(getattr(mod, "SOURCE", False)) != fonte:
                continue
            for ident, name, k, handle in _achados_de(mod, fonte):
                if not handle or handle in vistos:
                    continue
                vistos.add(handle)
                out.append(Found(mod, ident, name, k, handle))
    return out


def check():
    """Valida todo módulo contra o contrato. Chamado pelo selftest — é o que
    diz a quem contribui se o módulo dele está no formato certo."""
    ids = set()
    mods = modules()
    for mod in mods:
        onde = f"devices/{mod.ID}"
        assert isinstance(mod.NAME, str) and mod.NAME, f"{onde}: falta NAME"
        assert isinstance(getattr(mod, "CAPS", None), tuple) and mod.CAPS, \
            f"{onde}: falta CAPS"
        assert "battery" in mod.CAPS, f"{onde}: todo módulo precisa de battery"
        if getattr(mod, "SOURCE", False):
            # fonte genérica: não tem modelo, não tem IDS, e descobre vários
            assert callable(getattr(mod, "discover", None)), \
                f"{onde}: é SOURCE e precisa de discover()"
            assert callable(getattr(mod, "battery", None)), \
                f"{onde}: falta battery()"
            # o kind que ela emite precisa existir: o painel escolhe ícone por
            # ele, e o selftest do formato do cache o valida contra KINDS
            for _, _, kind, _ in _achados_de(mod, True):
                assert kind in KINDS, \
                    f"{onde}: discover() devolveu kind {kind!r}, fora de {KINDS}"
            continue
        assert mod.KIND in KINDS, f"{onde}: KIND deve ser um de {KINDS}"
        assert mod.IDS and all(isinstance(i, str) for i in mod.IDS), \
            f"{onde}: IDS deve ser uma tupla de identificadores (HID_ID no " \
            f"lado HID, pedaço de Modalias no lado Bluetooth)"
        for cap in mod.CAPS:
            assert callable(getattr(mod, cap, None)), \
                f"{onde}: declara {cap!r} em CAPS mas não tem a função"
        for cap in getattr(mod, "WONT", {}):
            assert cap not in mod.CAPS, \
                f"{onde}: {cap!r} está em CAPS e em WONT ao mesmo tempo"
        assert callable(mod.find), f"{onde}: falta find()"
        for i in mod.IDS:
            assert i not in ids, f"{onde}: HID_ID {i} já é de outro modelo"
            ids.add(i)
    return len(mods)
