"""Delux M800 PRO — mouse sem fio (receptor 2.4G ou cabo).

Ao contrário do M900Pro, **este não anuncia nada**: o canal de status só
responde depois de perguntar. Um `SET_FEATURE` com o opcode `0x20` no report
`0x0c` e um `GET_FEATURE` em seguida devolvem o frame. Escutar o receptor não
produz frame nenhum — medido, não suposto: 12482 frames de movimento no canal do
mouse contra **zero** no canal de status, na mesma janela.

O canal fica na interface 1, que é também a interface de teclado do dongle.
`find_iface(writable=True)` acerta ela pelo par vendor-page + Feature, e é a
certa — mas isso quer dizer que um `battery()` copiado do M900Pro, que faz
`os.read()` no path, **gravaria o que o dono digita**. Aqui só se fala por
ioctl; ninguém lê o stream de input. Detalhes em PROTOCOL.md.

Só stdlib: o driver de referência (github.com/xb-bx/m800-pro-driver) usa libusb
e desanexa o driver do kernel, mas os dois control transfers dele são
exatamente o que HIDIOCSFEATURE/HIDIOCGFEATURE já fazem pelo hidraw.
"""
import fcntl
import os
import time

from .. import Reading, find_iface

NAME = "Delux M800 PRO"
KIND = "mouse"
IDS = ("0000248A:00005B2F",   # receptor 2.4G
       "0000248A:00005B2E")   # modo cabo
CAPS = ("battery", "rgb", "sleep", "remap")
WONT = {
    "light": "não tem modos de iluminação — o LED só indica o estágio de DPI, "
             "e a cor dele é o `rgb`",
}

REPORT = 0x0C   # report Feature de 32 bytes na interface 1
SIZE = 33       # 1 byte de report id + os 32 do report
OP_STATUS = 0x20
MODEL = b"M802"  # o mouse assina o frame de status; ver PROTOCOL.md
SEQ_TRIES = 8    # o contador é um toggle: converge em 2, a folga é para ruído

# Botões e os 3 bytes de cada função, do driver de referência (buttons.h/keys.h).
BUTTONS = {"lmb": 0, "rmb": 1, "wheel": 2, "middle": 5, "mouse4": 4, "mouse5": 3}
KEYS = {
    "leftclick": (0x10, 0x01, 0x00), "rightclick": (0x10, 0x02, 0x00),
    "middleclick": (0x10, 0x04, 0x00), "forward": (0x10, 0x10, 0x00),
    "backward": (0x10, 0x08, 0x00), "dpiloop": (0x40, 0x01, 0x00),
    "dpi+": (0x40, 0x02, 0x00), "dpi-": (0x40, 0x03, 0x00),
    "select": (0x80, 0x83, 0x01), "prev": (0x80, 0xB6, 0x00),
    "next": (0x80, 0xB5, 0x00), "stop": (0x80, 0xB7, 0x00),
    "playpause": (0x80, 0xCD, 0x00), "mute": (0x80, 0xE2, 0x00),
    "volume+": (0x80, 0xE9, 0x00), "volume-": (0x80, 0xEA, 0x00),
    "mail": (0x80, 0x8A, 0x01), "calculator": (0x80, 0x92, 0x01),
    "tripleclick": (0x30, 0x32, 0x03), "disable": (0x00, 0x00, 0x00),
}
KEYS.update({f"dpilock/{100 * (n + 1)}": (0x50, n, 0x00)
             for n in range(1, 12)})  # DPILock/200..1200, como o keys.h

# Um template por opcode, copiado **byte a byte** do driver de referência. Os
# bytes que sobram do payload (o `len` do byte 6 é maior que o campo que a gente
# escreve) não estão explicados, então são preservados em vez de zerados.
TEMPLATES = {
    "rgb": bytes((0x0C, 0x01, 0x06, 0x00, 0x02, 0x01, 0x18,
                  0x00, 0xFF, 0x00, 0x00, 0xFF, 0x00, 0x00, 0x00, 0xFF,
                  0xFF, 0x00, 0xFF, 0xFF, 0xFF, 0x00, 0x00, 0xFF, 0xFF,
                  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00)),
    "sleep": bytes((0x0C, 0x01, 0x0B, 0x00, 0x02, 0x01, 0x02, 0x03) + (0,) * 25),
    "remap": bytes((0x0C, 0x01, 0x04, 0x00, 0x27, 0x01, 0x04, 0x04,
                    0x50, 0x01) + (0,) * 23),
}


def _ioc(direction, size, nr):
    return (direction << 30) | (size << 16) | (ord("H") << 8) | nr


SFEATURE = _ioc(3, SIZE, 0x06)
GFEATURE = _ioc(3, SIZE, 0x07)


def find():
    return find_iface(IDS, writable=True)


def _ask(fd, packet):
    """Manda um pacote e devolve a resposta do report 0x0c. Nunca lê o stream."""
    fcntl.ioctl(fd, SFEATURE, bytearray(packet))
    ans = bytearray(SIZE)
    ans[0] = REPORT
    fcntl.ioctl(fd, GFEATURE, ans)
    return bytes(ans)


def _handshake(fd):
    """(seq aceito, frame de status). O dispositivo ignora seq que não é o que
    ele espera, e o esperado alterna — daí varrer em vez de assumir 1."""
    for seq in range(1, SEQ_TRIES + 1):
        req = bytearray(SIZE)
        req[0], req[1], req[2], req[4] = REPORT, 0x01, OP_STATUS, seq
        got = parse(_ask(fd, req))
        if got:
            return seq, got
    return None, None


def battery(path, wait=0):
    """Pergunta o status. `wait` é orçamento de repetição para mouse dormindo."""
    fd = os.open(path, os.O_RDWR)
    try:
        end = time.time() + max(wait, 0)
        while True:
            _, got = _handshake(fd)
            if got or time.time() >= end:
                return got
            time.sleep(2)
    finally:
        os.close(fd)


# Byte 19: NÃO é booleano. Foram vistos três valores em 3h de log — 0 sem cabo,
# 1 carregando, e 2 só depois de bater 100% (provavelmente "carga completa").
# Valor fora desses três é estado desconhecido, e aí é `None`: melhor não dizer.
CARGA = {0: 0, 1: 1, 2: 1}


def parse(frame):
    """`0c 01 20 00 SS 01 10 00 'M802' … PP CH …` -> Reading.

    Byte 18 é o percentual e o 19 o estado de carga. Três coisas casam antes de
    acreditar no byte 18, porque este é um canal de request/response e uma
    resposta velha ou de outro opcode tem o mesmo tamanho:

    - byte 2 ecoa o opcode `0x20` — é o mesmo teste "estou falando com o
      aparelho ou com o buffer do dongle?" que o K86 obrigou a aprender;
    - bytes 8..11 são o ASCII `M802`, com que o mouse assina o frame;
    - o percentual tem que estar em 1..100.

    **O percentual não vale enquanto carrega** — ver PROTOCOL.md. Ele empaca e
    depois salta (medido: 90 min cravado em 64%, depois +30 de uma vez). O `raw`
    guarda o frame inteiro, então isso é reanalisável.
    """
    if len(frame) < 20:
        return None
    if frame[0] != REPORT or frame[2] != OP_STATUS:
        return None
    if frame[8:12] != MODEL:
        return None
    if not 1 <= frame[18] <= 100:
        return None
    return Reading(frame[18], CARGA.get(frame[19]), bytes(frame))


def _packet(kind, seq, fields):
    """Template do opcode com o seq e os campos documentados sobrescritos."""
    pkt = bytearray(TEMPLATES[kind])
    pkt[4] = seq
    for off, val in fields.items():
        pkt[off] = val
    return bytes(pkt)


def _send(path, kind, fields, msg, dry):
    """Monta, e (se não for dry) descobre o seq corrente e escreve."""
    if dry:
        return msg, [f">> {_packet(kind, 1, fields).hex(' ')}"]
    fd = os.open(path, os.O_RDWR)
    try:
        seq, got = _handshake(fd)
        if seq is None:
            raise ValueError(f"{NAME} não respondeu ao status — mouse dormindo?")
        # o driver de referência manda comando com o seq seguinte ao aceito
        pkt = _packet(kind, (seq + 1) & 0xFF, fields)
        _ask(fd, pkt)
        return msg, [f">> {pkt.hex(' ')}", f"   (bateria {got.pct}%)"]
    finally:
        os.close(fd)


def _cor(txt):
    try:
        b = bytes.fromhex(txt)
    except ValueError:
        b = b""
    if len(b) != 3:
        raise ValueError(f"cor deve ser RRGGBB, recebi {txt!r}")
    return b


def rgb(path, color, only=None, brightness=5, speed=4, dry=False):
    """Cor dos estágios de DPI. `color` é um `RRGGBB` (vale para os cinco) ou
    cinco separados por vírgula, um por estágio.

    **O `0x06` escreve os cinco estágios de uma vez e não existe opcode que leia
    os atuais.** Então não há como pintar um estágio preservando os outros: com
    `--only`, os que ficaram de fora vão para o padrão de fábrica do template.
    Isso é limitação do protocolo, não da implementação — e é por isso que existe
    a forma de cinco cores, que é a única que dá controle total.

    `brightness` e `speed` existem na assinatura porque o `kmctl rgb` os passa;
    este mouse não tem nenhum dos dois e eles são ignorados.
    """
    cores = [c.strip() for c in str(color).split(",")]
    if len(cores) not in (1, 5):
        raise ValueError("passe 1 cor (vale para os 5 estágios) ou 5 separadas "
                         f"por vírgula, uma por estágio; recebi {len(cores)}")
    if len(cores) == 5:
        if only:
            raise ValueError("--only não combina com 5 cores: a forma de 5 já "
                             "diz o que vai em cada estágio")
        alvo = {e: _cor(c) for e, c in enumerate(cores, 1)}
        msg = "estágios 1..5 = " + " ".join(f"#{c}" for c in cores)
    else:
        uma = _cor(cores[0])
        if only:
            try:
                estagios = [int(x) for x in only.replace(",", " ").split()]
            except ValueError:
                raise ValueError("--only aqui são estágios de DPI 1..5, não "
                                 f"{only!r}")
            if not all(1 <= e <= 5 for e in estagios):
                raise ValueError("estágio de DPI fora de 1..5")
            msg = (f"cor #{cores[0]} em estágio(s) "
                   + ",".join(str(e) for e in estagios)
                   + " — os outros voltam ao padrão de fábrica, porque o "
                     "protocolo escreve os 5 juntos e não dá para ler os atuais")
        else:
            estagios = [1, 2, 3, 4, 5]
            msg = f"cor #{cores[0]} em todos os estágios"
        alvo = {e: uma for e in estagios}
    fields = {}
    for e, b in alvo.items():
        for i in range(3):
            fields[7 + (e - 1) * 3 + i] = b[i]
    return _send(path, "rgb", fields, msg, dry)


def sleep(path, when, dry=False):
    """Minutos até dormir, 3..10. Este mouse não tem "never"."""
    if str(when).strip().lower() in ("never", "nunca"):
        raise ValueError(f"{NAME} não aceita 'never' — o firmware só vai de 3 a "
                         "10 minutos. Use `kmctl sleep 10`.")
    try:
        minutos = int(when)
    except (TypeError, ValueError):
        raise ValueError(f"esperava minutos (3..10), recebi {when!r}")
    if not 3 <= minutos <= 10:
        raise ValueError(f"minutos até dormir deve ser 3..10, recebi {minutos}")
    return _send(path, "sleep", {7: minutos},
                 f"dorme depois de {minutos} min sem uso", dry)


def remap(path, key, to, layer="fn", dry=False):
    """Função de um botão. `layer` existe porque o `kmctl key` passa; um mouse
    não tem camada e o valor é ignorado."""
    botao = BUTTONS.get(key.lower())
    if botao is None:
        raise ValueError(f"botão desconhecido: {key!r} — tem "
                         f"{', '.join(sorted(BUTTONS))}")
    func = KEYS.get(to.lower())
    if func is None:
        raise ValueError(f"função desconhecida: {to!r} — tem "
                         f"{', '.join(sorted(KEYS))}")
    fields = {7: botao, 8: func[0], 9: func[1], 10: func[2]}
    return _send(path, "remap", fields, f"botão {key} = {to}", dry)
