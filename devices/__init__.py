"""Descoberta dos modelos suportados e o que eles têm em comum.

Um diretório por modelo em `devices/`. Este arquivo não conhece nenhum deles:
varre o diretório, importa o que achar e usa o que o módulo declarar. Adicionar
um modelo é criar uma pasta — não há lista para editar aqui.

O contrato está em `devices/README.md`.
"""
import collections
import glob
import importlib
import os
import pkgutil
import sys

# O que uma leitura de bateria devolve. `raw` é o frame cru (b"" se o modelo não
# expõe um): é ele que alimenta a tabela `raw` do histórico e o `kmctl raw`,
# que é como se descobre o byte de bateria de um modelo novo.
Reading = collections.namedtuple("Reading", "pct charging raw")

CONFIG = os.path.expanduser("~/.config/keyboard-mouse.conf")
KINDS = ("keyboard", "mouse")


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
    """Os modelos que estão plugados agora, com o /dev/hidrawN de cada um."""
    out = []
    for mod in modules():
        if kind and mod.KIND != kind:
            continue
        path = mod.find()
        if path:
            out.append((mod, path))
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
        return cands[0][0], cands[0][1], "único plugado"
    escolhido = config().get(kind)
    for mod, path in cands:
        if mod.ID == escolhido:
            return mod, path, f"escolhido em {CONFIG}"
    if recency:
        mod, path = max(cands, key=lambda c: recency.get(c[0].ID, 0))
        return mod, path, "reportou mais recentemente (empate sem config)"
    mod, path = cands[0]
    return mod, path, "primeiro da ordem (empate sem config)"


def check():
    """Valida todo módulo contra o contrato. Chamado pelo selftest — é o que
    diz a quem contribui se o módulo dele está no formato certo."""
    ids = set()
    for mod in modules():
        onde = f"devices/{mod.ID}"
        assert isinstance(mod.NAME, str) and mod.NAME, f"{onde}: falta NAME"
        assert mod.KIND in KINDS, f"{onde}: KIND deve ser um de {KINDS}"
        assert mod.IDS and all(isinstance(i, str) for i in mod.IDS), \
            f"{onde}: IDS deve ser uma tupla de HID_ID"
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
