#!/usr/bin/env python3
"""battlog - histórico de bateria dos periféricos em SQLite.

Hardware atual: teclado Attack Shark K86 (dongle ROYUAN 3151:4011) e mouse
Delux M900Pro (receptor 8K 1d57:fa65). O hardware anterior (FreeWolf F75 +
AJAZZ AJ139) está em `battlog-f75.py`, que ainda funciona se voltarem à mesa.

Nenhum dos dois tem parser de bateria: o canal é desconhecido. O sharkfin, que
documentou essa família de teclados, registra "No HID command found. The vendor
reads it through a separate helper process". Daí o modo `probe`: grava os bytes
crus do canal vendor a cada rodada, sem interpretar. Depois de algumas horas,
`raw` mostra quais bytes se mexeram — o que cair devagar e quase sempre para
baixo é a bateria. Confirmado o byte, `PARSERS` vira uma linha e o `show` volta
a funcionar como no F75.

    battlog.py probe        # grava uma rodada de bytes crus (é o que o cron roda)
    battlog.py raw          # quais bytes variaram e como
    battlog.py show         # timeline de bateria (só depois de haver parser)
    battlog.py status       # último valor de cada um, e atualiza o cache do painel
    battlog.py selftest     # checa análise, poda e sparkline
"""
import argparse
import fcntl
import glob
import os
import select
import sqlite3
import sys
import time

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battlog.db")
STATUS = os.path.join(os.environ.get("XDG_CACHE_HOME") or
                      os.path.expanduser("~/.cache"), "battlog-status")
KEEP_DAYS = 90

# ioctls do hidraw (linux/hidraw.h): _IOC(READ|WRITE, 'H', nr, tamanho)
_IOWR = lambda nr, n: (3 << 30) | (n << 16) | (0x48 << 8) | nr
HIDIOCSFEATURE = lambda n: _IOWR(0x06, n)
HIDIOCGFEATURE = lambda n: _IOWR(0x07, n)


def find_vendor_iface(hid_id):
    """/dev/hidrawN do canal vendor *gravável* desse VID:PID.

    Os dois periféricos expõem a página vendor (0xFF00/0xFFFF) em mais de uma
    interface, mas só uma aceita escrita — a que tem item Feature (0xB1) ou
    Output (0x91). As outras são só input, e no teclado uma delas carrega o NKRO
    (ou seja: escolher errado seria abrir o que o Victor digita).
    """
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        with open(uevent) as f:
            if hid_id not in f.read():
                continue
        d = os.path.dirname(uevent)
        with open(os.path.join(d, "report_descriptor"), "rb") as f:
            desc = f.read()
        vendor = b"\x06\x00\xff" in desc or b"\x06\xff\xff" in desc
        if vendor and (b"\xb1\x02" in desc or b"\x91\x02" in desc):
            return "/dev/" + os.path.basename(os.path.dirname(d))
    return None


def ck7(pkt):
    """Checksum da família ROYUAN: 0xFF - soma dos bytes 0..6, guardado no 7."""
    pkt[7] = (0xFF - (sum(pkt[:7]) & 0xFF)) & 0xFF
    return pkt


def probe_keyboard(dev, _wait):
    """Lê o frame de status do dongle do K86. O byte 1 é a bateria.

    O opcode não importa: o dongle responde **o mesmo frame a qualquer comando**
    (`00 PP 00 00 01 01 01 ck`) e nunca repassa nada pelo rádio — confirmado por
    varredura própria dos opcodes 0x80-0xFF e, independentemente, pelo data
    bundle do sharkfin, onde os 17 opcodes conhecidos devolvem byte a byte a
    mesma coisa e o `identify` fica sem resposta. É por isso que não existe
    config por 2.4G, e é também o "outro canal" que o software do fabricante usa
    pra ler bateria: o frame é do dongle, não do teclado.

    Byte 1 = percentual. Confirmado em 2026-08-08 por duas leituras
    independentes (este probe e o sharkfin) marcando 33 ao mesmo tempo, depois
    de cair de 34.

    ponytail: teto conhecido — não está provado que isso não acorda o teclado
    pelo rádio (no F75, escrever reiniciava o timer de sono, e o objetivo aqui é
    economizar bateria). As respostas voltam idênticas e instantâneas mesmo com
    esperas de 1 s, o que sugere que quem responde é o dongle sozinho. Se a
    bateria passar a cair rápido demais, este é o primeiro suspeito: tirar do
    cron e voltar a escutar passivo.
    """
    fd = os.open(dev, os.O_RDWR)
    try:
        req = ck7(bytearray(64))
        req[0] = 0xF7
        fcntl.ioctl(fd, HIDIOCSFEATURE(65), bytes([0]) + bytes(req))
        time.sleep(0.05)
        buf = bytearray(65)
        fcntl.ioctl(fd, HIDIOCGFEATURE(65), buf)
        return bytes(buf[1:17])
    finally:
        os.close(fd)


def probe_mouse(dev, wait):
    """Escuta os reports de status do receptor do mouse (passivo).

    O GET_REPORT dele dá EPIPE (não suportado), então só resta escutar. Ele **só
    fala com o mouse em uso**: 70 s de escuta com o mouse parado não dão nada, e
    com ele em uso sai `03 50 41 01 55` no report 0x03. Se voltar None é "mouse
    parado", não "quebrou" — daí a espera longa no cron.

    Aceita 0x03 e 0x04: o 0x04 é o vendor declarado no descritor (e é por onde o
    mouse antigo falava), mas quem realmente apareceu neste foi o 0x03. Guardar
    os dois custa nada e evita perder o único que fala.
    """
    fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
    try:
        end = time.time() + wait
        while (left := end - time.time()) > 0:
            if not select.select([fd], [], [], left)[0]:
                continue
            pkt = os.read(fd, 64)
            if pkt and pkt[0] in (0x03, 0x04):
                return pkt[:16]
        return None
    finally:
        os.close(fd)


DEVICES = (
    ("teclado", "00003151:00004011", probe_keyboard),
    ("mouse", "00001D57:0000FA65", probe_mouse),
)

# device -> (offset do percentual, offset da flag de carga ou None).
#
# teclado: frame de status do dongle. O byte 1 caiu 34→32 na bateria e pulou pra
#   42 no instante em que o cabo entrou; o byte 3 virou 0→1 no mesmo instante (o
#   byte 5 é o inverso dele, redundante). Confirmado.
# mouse: report 0x03, byte 4 descendo 85→84. **Provisório** — é um decremento só,
#   consistente mas com menos evidência que o do teclado. O `raw` continua
#   gravando o frame inteiro, então se esse byte se revelar outra coisa (contador,
#   qualidade de link), dá pra trocar sem ter perdido histórico.
PARSERS = {"teclado": (1, 3), "mouse": (4, None)}


def battery_rows(rows):
    """[(ts, device, hex)] -> [(ts, device, pct, charging)] para os que têm parser."""
    out = []
    for ts, name, h in rows:
        if name not in PARSERS:
            continue
        pct_off, chg_off = PARSERS[name]
        raw = bytes.fromhex(h)
        if raw[pct_off] == 0:
            # Frame desalinhado (um byte a menos), que sai logo depois de o dongle
            # enumerar. Vira um 0% falso no log e um susto no painel. Bateria 0 de
            # verdade não chega aqui: teclado sem carga não reporta nada.
            continue
        chg = None if chg_off is None else int(bool(raw[chg_off]))
        out.append((ts, name, raw[pct_off], chg))
    return out


def db_open(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS battery("
                "ts INTEGER, device TEXT, pct INTEGER, charging INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS battery_ts ON battery(ts, device)")
    con.execute("CREATE TABLE IF NOT EXISTS raw(ts INTEGER, device TEXT, hex TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS raw_ts ON raw(ts, device)")
    return con


def status_text(con):
    """Última leitura de cada device, em linhas `chave valor` — o que o painel lê.

    Lê a última linha do banco, não a rodada atual, de propósito: o mouse só
    fala com o mouse em uso, e mouse parado não gastou bateria, então repetir o
    último número é mais verdadeiro do que apagá-lo. Quem morre de verdade é o
    cron, e isso aparece no `ts`: a extensão compara com o relógio e mostra "—"
    em vez de um número velho.

    Sem flag de carga: a do teclado (byte 3) pisca 0/1 sem cabo nenhum, então
    ela mentiria no painel. Ver README.
    """
    linhas = [f"ts {int(time.time())}"]
    for name, in con.execute("SELECT DISTINCT device FROM battery ORDER BY device"):
        pct, = con.execute("SELECT pct FROM battery WHERE device = ? "
                           "ORDER BY ts DESC LIMIT 1", (name,)).fetchone()
        linhas.append(f"{name} {pct}")
    return "\n".join(linhas) + "\n"


def write_status(con, path=STATUS):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"  # troca atômica: o painel relê a qualquer momento
    with open(tmp, "w") as f:
        f.write(status_text(con))
    os.replace(tmp, path)


def cmd_status(args):
    con = db_open(args.db)
    write_status(con)
    print(status_text(con), end="")
    return 0


def cmd_probe(args):
    rows = []
    for name, hid_id, probe in DEVICES:
        dev = find_vendor_iface(hid_id)
        if not dev:
            print(f"{name}: ausente", file=sys.stderr)
            continue
        try:
            got = probe(dev, args.wait)
        except PermissionError:
            print(f"{name}: sem permissão em {dev} — falta a regra udev "
                  "(../udev/99-attackshark.rules)", file=sys.stderr)
            continue
        except OSError as e:
            print(f"{name}: {dev} respondeu erro {e.errno} ({e.strerror})",
                  file=sys.stderr)
            continue
        if got is None:
            print(f"{name}: nada em {dev} em {args.wait:.0f}s", file=sys.stderr)
            continue
        rows.append((int(time.time()), name, got.hex(" ")))

    con = db_open(args.db)
    con.executemany("INSERT INTO raw VALUES (?,?,?)", rows)
    batt = battery_rows(rows)
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)", batt)
    lidos = {name: (pct, chg) for _, name, pct, chg in batt}
    for _, name, h in rows:
        if name in lidos:
            pct, chg = lidos[name]
            print(f"{name}: {pct}%" + (" (carregando)" if chg else "") + f"  [{h}]")
        else:
            print(f"{name}: {h}")
    cut = int(time.time()) - args.keep * 86400
    dropped = sum(con.execute(f"DELETE FROM {t} WHERE ts < ?", (cut,)).rowcount
                  for t in ("battery", "raw"))
    con.commit()
    write_status(con)
    if dropped:
        print(f"({dropped} amostras com mais de {args.keep} dias apagadas)")
    return 0 if rows else 1


def analyse(samples):
    """samples = [(ts, bytes)] em ordem. Devolve [(offset, valores, veredito)].

    Só interessa byte que se mexeu. O candidato a bateria é o que fica em 1..100
    e quase nunca sobe — descarga é monotônica, tirando os saltos de recarga.
    """
    out = []
    for off in range(len(samples[0][1])):
        vals = [b[off] for _, b in samples]
        if len(set(vals)) < 2:
            continue
        subiu = sum(b > a for a, b in zip(vals, vals[1:]))
        plausivel = all(1 <= v <= 100 for v in vals)
        veredito = ("CANDIDATO a bateria" if plausivel and subiu <= 1
                    else "varia, mas não parece bateria")
        out.append((off, vals, veredito))
    return out


BLOCKS = " ▁▂▃▄▅▆▇█"


def spark(buckets):
    # escala fixa 0-100: altura comparável entre dispositivos e entre dias
    return "".join(" " if v is None else BLOCKS[max(1, round(v / 100 * 8))]
                   for v in buckets)


def cmd_raw(args):
    con = db_open(args.db)
    start = int(time.time()) - args.days * 86400
    for name, in con.execute("SELECT DISTINCT device FROM raw WHERE ts >= ? "
                             "ORDER BY device", (start,)):
        samples = [(ts, bytes.fromhex(h)) for ts, h in con.execute(
            "SELECT ts, hex FROM raw WHERE device = ? AND ts >= ? ORDER BY ts",
            (name, start))]
        span = (samples[-1][0] - samples[0][0]) / 3600
        print(f"\n=== {name} — {len(samples)} amostras em {span:.1f}h ===")
        print(f"  primeira: {samples[0][1].hex(' ')}")
        print(f"  última:   {samples[-1][1].hex(' ')}")
        muda = analyse(samples)
        if not muda:
            print("  nenhum byte mudou ainda — deixe rodar mais tempo")
        for off, vals, veredito in muda:
            resumo = vals if len(vals) <= 12 else vals[:6] + ["..."] + vals[-5:]
            print(f"  byte[{off:2}] {veredito}")
            print(f"           {' '.join(str(v) for v in resumo)}")


def cmd_show(args):
    con = db_open(args.db)
    start = int(time.time()) - args.days * 86400
    step = args.days * 86400 / args.width
    if not con.execute("SELECT 1 FROM battery WHERE ts >= ? LIMIT 1",
                       (start,)).fetchone():
        print("sem dados de bateria — o byte ainda não foi identificado.\n"
              "Rode `battlog.py raw` para ver o que o `probe` já juntou.")
        return 1
    print(f"bateria — últimos {args.days} dia(s), 0-100% em escala fixa\n")
    for name, in con.execute("SELECT DISTINCT device FROM battery "
                             "WHERE ts >= ? ORDER BY device", (start,)):
        sums = [None] * args.width
        for ts, pct in con.execute("SELECT ts, pct FROM battery WHERE "
                                   "device = ? AND ts >= ?", (name, start)):
            i = min(int((ts - start) / step), args.width - 1)
            sums[i] = pct if sums[i] is None else (sums[i] + pct) / 2
        vals = [v for v in sums if v is not None]
        last = con.execute("SELECT pct, charging FROM battery WHERE device = ? "
                           "ORDER BY ts DESC LIMIT 1", (name,)).fetchone()
        agora = f"{last[0]}%" + (" carregando" if last[1] else "")
        print(f"{name:>8} |{spark(sums)}| agora {agora}  "
              f"(min {min(vals):.0f} / max {max(vals):.0f}, "
              f"{len(vals)}/{args.width} intervalos com dado)")
    a = time.strftime("%d/%m %H:%M", time.localtime(start))
    print(f"{'':>8}  {a}" + " " * (args.width - len(a) - 5) + "agora")


def selftest():
    assert ck7(bytearray([0xF7] + [0] * 63))[7] == 0x08  # 0xFF - 0xF7

    def s(*seqs):
        return [(i, bytes(b)) for i, b in enumerate(seqs)]

    # byte 0 constante (ignorado), byte 1 descendo em faixa de bateria
    r = analyse(s([1, 80], [1, 79], [1, 78]))
    assert len(r) == 1 and r[0][0] == 1 and "CANDIDATO" in r[0][2], r
    # descida com um repique de recarga ainda conta
    assert "CANDIDATO" in analyse(s([90], [88], [99], [97]))[0][2]
    # serrilhado não é bateria
    assert "CANDIDATO" not in analyse(s([10], [90], [10], [90]))[0][2]
    # fora de 1..100 não é percentual
    assert "CANDIDATO" not in analyse(s([200], [150], [120]))[0][2]
    # nada muda -> nada a relatar
    assert analyse(s([5, 5], [5, 5])) == []

    # frames reais: teclado na bateria, teclado carregando, mouse
    assert battery_rows([(9, "teclado", "00 20 00 00 01 01 01 7a")]) \
        == [(9, "teclado", 32, 0)]
    assert battery_rows([(9, "teclado", "00 2a 00 01 01 00 01 7a")]) \
        == [(9, "teclado", 42, 1)]
    assert battery_rows([(9, "mouse", "03 50 41 01 54")]) == [(9, "mouse", 84, None)]
    assert battery_rows([(9, "desconhecido", "00 01")]) == []
    # frame desalinhado -> 0%: descartado, não vira ponto no gráfico
    assert battery_rows([(9, "teclado", "00 00 00 01 01 01 01 00")]) == []

    con = db_open(":memory:")
    now = int(time.time())
    con.executemany("INSERT INTO raw VALUES (?,?,?)",
                    [(now - 200 * 86400, "x", "00"), (now, "x", "01")])
    con.execute("DELETE FROM raw WHERE ts < ?", (now - 90 * 86400,))
    assert con.execute("SELECT count(*) FROM raw").fetchone()[0] == 1
    assert spark([None, 0, 50, 100]) == " ▁▄█"

    con.executemany("INSERT INTO battery VALUES (?,?,?,?)",
                    [(1, "teclado", 50, 0), (2, "teclado", 49, 0), (1, "mouse", 70, None)])
    linhas = status_text(con).splitlines()
    assert linhas[0].startswith("ts ") and int(linhas[0][3:]) > 1_700_000_000, linhas
    assert linhas[1:] == ["mouse 70", "teclado 49"], linhas  # o mais recente de cada
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("probe", help="grava os bytes crus do canal vendor")
    pr.add_argument("--wait", type=float, default=60,
                    help="segundos esperando o mouse se anunciar (default: 60)")
    pr.add_argument("--keep", type=int, default=KEEP_DAYS,
                    help=f"dias de histórico a manter (default: {KEEP_DAYS})")
    rw = sub.add_parser("raw", help="quais bytes variaram e como")
    rw.add_argument("--days", type=float, default=7)
    sh = sub.add_parser("show", help="timeline de bateria")
    sh.add_argument("--days", type=float, default=7)
    sh.add_argument("--width", type=int, default=60)
    sub.add_parser("status", help="última leitura de cada device (e atualiza o cache do painel)")
    sub.add_parser("selftest", help="checa análise, poda e sparkline")
    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    return {"probe": cmd_probe, "raw": cmd_raw, "show": cmd_show,
            "status": cmd_status}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
