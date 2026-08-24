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

CONFIG = os.path.expanduser("~/.config/keyboard-mouse.conf")
# Vocabulário de categorias. Serve para escolher ícone no painel e para o
# `--device`/config desempatarem; não é uma taxonomia com pretensão. "other" é o
# destino honesto de qualquer coisa que uma fonte genérica ache e não saiba
# classificar — melhor que forçar num rótulo errado.
KINDS = ("keyboard", "mouse", "headset", "phone", "gamepad", "other")


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

_BLUEZ_CACHE = []  # memo por processo; o kmctl é one-shot, então não envelhece


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


def bluez_objects(refresh=False):
    """{path: {interface: {prop: valor}}} de tudo que o BlueZ conhece. {} se
    não der para falar com ele."""
    if _BLUEZ_CACHE and not refresh:
        return _BLUEZ_CACHE[0]
    got = _busctl("call", "org.bluez", "/",
                  "org.freedesktop.DBus.ObjectManager", "GetManagedObjects")
    out = {}
    try:
        for path, ifaces in got["data"][0].items():
            out[path] = {i: {k: v["data"] for k, v in props.items()}
                         for i, props in ifaces.items()}
    except (TypeError, KeyError, IndexError):
        out = {}
    _BLUEZ_CACHE[:] = [out]
    return out


def bluez_match(objects, ids):
    """path do aparelho **conectado** cujo Modalias casa com `ids`, e que
    reporta bateria. None se não estiver conectado.

    `ids` são pedaços de Modalias, ex: `"v0ECBp2100"` para
    `bluetooth:v0ECBp2100d001F` — vendor e produto, sem o `d` de device
    release, que muda com revisão de firmware.

    Separada de `find_bluez` de propósito: é função pura, então o selftest a
    testa sem precisar de Bluetooth ligado.
    """
    for path in sorted(objects):
        dev = objects[path].get("org.bluez.Device1")
        if not dev or not dev.get("Connected"):
            continue
        modalias = dev.get("Modalias", "")
        if not any(i in modalias for i in ids):
            continue
        if "org.bluez.Battery1" not in objects[path]:
            continue
        return path
    return None


def find_bluez(ids):
    """path do BlueZ desse aparelho, se estiver conectado agora."""
    return bluez_match(bluez_objects(), ids)


def bluez_pct(path):
    """Percentual que o BlueZ reporta, ou None."""
    got = _busctl("get-property", "org.bluez", path,
                  "org.bluez.Battery1", "Percentage")
    try:
        pct = int(got["data"])
    except (TypeError, KeyError, ValueError):
        return None
    return pct if 0 <= pct <= 100 else None


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


def present(kind=None):
    """Tudo que está aqui agora e tem bateria, como lista de `Found`.

    Módulos de modelo vêm primeiro e **reservam** o handle deles; depois as
    fontes genéricas entram com o que sobrou. É o que evita o fone aparecer
    duas vezes — uma pelo diretório do modelo, outra pelo `bluez_any`, já que os
    dois devolvem o mesmo object path do BlueZ.

    A dedução só funciona quando os dois lados falam do mesmo handle, o que é o
    caso do Bluetooth. Um aparelho visto por protocolo de fabricante (handle
    `/dev/hidrawN`) e ao mesmo tempo pelo `power_supply` (handle no sysfs) não
    seria pego — não há caso desses hoje, e forçar uma identidade entre
    barramentos diferentes daria mais erro que acerto.
    """
    out, vistos = [], set()
    for fonte in (False, True):
        for mod in modules():
            if bool(getattr(mod, "SOURCE", False)) != fonte:
                continue
            try:
                achados = (list(mod.discover()) if fonte else
                           [(mod.ID, mod.NAME, mod.KIND, mod.find())])
            except Exception as e:  # noqa: BLE001 - fonte de terceiro não derruba o resto
                print(f"devices: {mod.ID}.discover() falhou ({e})", file=sys.stderr)
                continue
            for ident, name, k, handle in achados:
                if not handle or handle in vistos:
                    continue
                if kind and k != kind:
                    continue
                vistos.add(handle)
                out.append(Found(mod, ident, name, k, handle))
    return out


def config():
    """`chave = valor` de ~/.config/keyboard-mouse.conf. {} se não existir."""
    try:
        with open(CONFIG) as f:
            linhas = f.read().splitlines()
    except OSError:
        return {}
    out = {}
    for linha in linhas:
        linha = linha.split("#", 1)[0]
        if "=" in linha:
            k, v = linha.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def pick(kind, recency=None):
    """O modelo daquele tipo que o painel deve mostrar: (mod, path, motivo).

    Um só plugado resolve o caso de todo dia sem configurar nada. Empate cai no
    ~/.config/keyboard-mouse.conf; sem config, vence quem reportou por último —
    assim trocar de hardware ajusta sozinho, sem editar arquivo.
    """
    cands = present(kind)
    if not cands:
        return None, None, "nenhum plugado"
    if len(cands) == 1:
        return cands[0].mod, cands[0].handle, "único plugado"
    escolhido = config().get(kind)
    for f in cands:
        if f.ident == escolhido:
            return f.mod, f.handle, f"escolhido em {CONFIG}"
    if recency:
        f = max(cands, key=lambda c: recency.get(c.ident, 0))
        return f.mod, f.handle, "reportou mais recentemente (empate sem config)"
    f = cands[0]
    return f.mod, f.handle, "primeiro da ordem (empate sem config)"


def check():
    """Valida todo módulo contra o contrato. Chamado pelo selftest — é o que
    diz a quem contribui se o módulo dele está no formato certo."""
    ids = set()
    for mod in modules():
        onde = f"devices/{mod.ID}"
        assert isinstance(mod.NAME, str) and mod.NAME, f"{onde}: falta NAME"
        if getattr(mod, "SOURCE", False):
            # fonte genérica: não tem modelo, não tem IDS, e descobre vários
            assert callable(getattr(mod, "discover", None)), \
                f"{onde}: é SOURCE e precisa de discover()"
            assert callable(getattr(mod, "battery", None)), \
                f"{onde}: falta battery()"
            continue
        assert mod.KIND in KINDS, f"{onde}: KIND deve ser um de {KINDS}"
        assert mod.IDS and all(isinstance(i, str) for i in mod.IDS), \
            f"{onde}: IDS deve ser uma tupla de identificadores (HID_ID no " \
            f"lado HID, pedaço de Modalias no lado Bluetooth)"
        assert "battery" in mod.CAPS, f"{onde}: todo modelo precisa de battery"
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
    return len(modules())
