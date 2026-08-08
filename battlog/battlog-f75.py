#!/usr/bin/env python3
"""battlog - registra a bateria do teclado F75 e do mouse AJAZZ num SQLite.

Amostragem passiva: os dois periféricos anunciam a bateria sozinhos no canal
vendor deles (o F75 manda `0x0E` a cada ~5,5 s; o mouse manda `0xFA`). Nada é
escrito no dispositivo — escrever mexeria no timer de sono do teclado.

    battlog.py sample          # grava uma amostra de cada (para o cron)
    battlog.py show            # timeline no terminal
"""
import argparse
import glob
import os
import select
import sqlite3
import sys
import time

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battlog.db")
KEEP_DAYS = 90


def parse_f75(pkt):
    """Teclado FreeWolf F75: status espontâneo (ver ../f75ctl/PROTOCOL.md)."""
    if pkt[:4] == b"\xaa\x55\xcc\x33" and pkt[4] == 0x0E and pkt[5] <= 100:
        return pkt[5], None  # [6] é uma flag de estado, não de carga
    return None


def parse_yjx(pkt):
    """Mouse AJAZZ/Smailwolf: 0xFA com marker 0xD0 (github.com/0LostConnection
    /Smailwolf-RS7). O mesmo 0xFA também carrega o slot de DPI — daí o marker."""
    if pkt[0] != 0xAA or pkt[1] != 0xFA or pkt[8] != 0xD0 or pkt[9] > 100:
        return None
    if sum(pkt[4:64]) & 0xFF != pkt[3]:  # pacote picado/garbage
        return None
    return pkt[9], 1 if pkt[10] else 0


DEVICES = (
    ("teclado", ("00001A2C:00008FFF", "00001A2C:0000A073"), parse_f75),
    ("mouse", ("0000A8A5:00002255",), parse_yjx),
)


def find_vendor_iface(hid_ids):
    """/dev/hidrawN do canal vendor (Usage Page 0xFFxx) desses VID:PID."""
    for uevent in sorted(glob.glob("/sys/class/hidraw/hidraw*/device/uevent")):
        with open(uevent) as f:
            if not any(i in f.read() for i in hid_ids):
                continue
        d = os.path.dirname(uevent)
        with open(os.path.join(d, "report_descriptor"), "rb") as f:
            desc = f.read(4)
        if desc[0] == 0x06 and desc[2] == 0xFF:
            return "/dev/" + os.path.basename(os.path.dirname(d))
    return None


def db_open(path):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS battery("
                "ts INTEGER, device TEXT, pct INTEGER, charging INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS battery_ts ON battery(ts, device)")
    return con


def cmd_sample(args):
    """Escuta os canais vendor até cada dispositivo se anunciar (ou estourar)."""
    fds, pending = {}, {}
    for name, hid_ids, parser in DEVICES:
        dev = find_vendor_iface(hid_ids)
        if not dev:
            print(f"{name}: ausente", file=sys.stderr)
            continue
        try:
            fd = os.open(dev, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            print(f"{name}: sem permissão em {dev} — falta a regra udev",
                  file=sys.stderr)
            continue
        fds[fd] = (name, parser)
        pending[name] = dev

    rows, end = [], time.time() + args.wait
    while pending and (left := end - time.time()) > 0:
        for fd in select.select(list(fds), [], [], left)[0]:
            name, parser = fds[fd]
            got = parser(os.read(fd, 64))
            if got and name in pending:
                del pending[name]
                rows.append((int(time.time()), name, got[0], got[1]))
    for fd in fds:
        os.close(fd)

    con = db_open(args.db)
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)", rows)
    cut = int(time.time()) - args.keep * 86400
    dropped = con.execute("DELETE FROM battery WHERE ts < ?", (cut,)).rowcount
    con.commit()
    for ts, name, pct, chg in rows:
        print(f"{name}: {pct}%" + (" (carregando)" if chg else ""))
    for name, dev in pending.items():
        print(f"{name}: nada em {dev} em {args.wait:.0f}s", file=sys.stderr)
    if dropped:
        print(f"({dropped} amostras com mais de {args.keep} dias apagadas)")
    return 0 if rows else 1


BLOCKS = " ▁▂▃▄▅▆▇█"


def spark(buckets):
    # escala fixa 0-100: altura comparável entre dispositivos e entre dias
    return "".join(" " if v is None else BLOCKS[max(1, round(v / 100 * 8))]
                   for v in buckets)


def cmd_show(args):
    con = db_open(args.db)
    start = int(time.time()) - args.days * 86400
    step = args.days * 86400 / args.width
    print(f"bateria — últimos {args.days} dia(s), 0-100% em escala fixa\n")
    for name, in con.execute("SELECT DISTINCT device FROM battery "
                             "WHERE ts >= ? ORDER BY device", (start,)):
        sums = [None] * args.width
        for ts, pct in con.execute("SELECT ts, pct FROM battery WHERE "
                                   "device = ? AND ts >= ?", (name, start)):
            i = min(int((ts - start) / step), args.width - 1)
            sums[i] = pct if sums[i] is None else (sums[i] + pct) / 2
        vals = [v for v in sums if v is not None]
        last = con.execute("SELECT pct, ts FROM battery WHERE device = ? "
                           "ORDER BY ts DESC LIMIT 1", (name,)).fetchone()
        print(f"{name:>8} |{spark(sums)}| agora {last[0]}%  "
              f"(min {min(vals):.0f} / max {max(vals):.0f}, "
              f"{len(vals)}/{args.width} intervalos com dado)")
    a = time.strftime("%d/%m %H:%M", time.localtime(start))
    print(f"{'':>8}  {a}" + " " * (args.width - len(a) - 5) + "agora")


def selftest():
    ok = bytearray(64)
    ok[:4] = b"\xaa\x55\xcc\x33"
    ok[4], ok[5] = 0x0E, 77
    assert parse_f75(bytes(ok)) == (77, None)
    ok[4] = 0x07
    assert parse_f75(bytes(ok)) is None  # outro comando não é bateria
    m = bytearray(64)
    m[0], m[1], m[2], m[8], m[9], m[10] = 0xAA, 0xFA, 0xAE, 0xD0, 64, 1
    m[3] = sum(m[4:64]) & 0xFF
    assert parse_yjx(bytes(m)) == (64, 1)
    m[8] = 0x10  # 0xFA de slot de DPI, não de bateria
    m[3] = sum(m[4:64]) & 0xFF
    assert parse_yjx(bytes(m)) is None
    m[8], m[3] = 0xD0, 0x00  # checksum errado
    assert parse_yjx(bytes(m)) is None
    con = db_open(":memory:")
    old, new = int(time.time()) - 200 * 86400, int(time.time())
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)",
                    [(old, "x", 1, 0), (new, "x", 2, 0)])
    con.execute("DELETE FROM battery WHERE ts < ?", (new - 90 * 86400,))
    assert con.execute("SELECT count(*) FROM battery").fetchone()[0] == 1
    assert spark([None, 0, 50, 100]) == " ▁▄█"
    print("selftest ok")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", default=DB)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sm = sub.add_parser("sample", help="grava uma amostra de cada dispositivo")
    sm.add_argument("--wait", type=float, default=60,
                    help="segundos esperando cada anúncio (default: 60)")
    sm.add_argument("--keep", type=int, default=KEEP_DAYS,
                    help=f"dias de histórico a manter (default: {KEEP_DAYS})")
    sh = sub.add_parser("show", help="timeline no terminal")
    sh.add_argument("--days", type=float, default=7)
    sh.add_argument("--width", type=int, default=60)
    sub.add_parser("selftest", help="checa os parsers e a poda")
    args = ap.parse_args()
    if args.cmd == "selftest":
        return selftest()
    return {"sample": cmd_sample, "show": cmd_show}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main() or 0)
