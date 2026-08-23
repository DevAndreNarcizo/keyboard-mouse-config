"""Histórico de bateria dos periféricos em SQLite. Só stdlib.

Este módulo não conhece nenhum modelo: pergunta ao `devices` quem está plugado e
guarda o que cada um devolver. Adicionar um periférico é criar um diretório em
`devices/` — nada aqui muda.

    kmctl probe     grava uma rodada (é o que o cron roda)
    kmctl raw       quais bytes variaram e como (para achar bateria em modelo novo)
    kmctl show      timeline
    kmctl status    último valor de cada um, e atualiza o cache do painel
"""
import os
import sqlite3
import time

import devices

DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(DIR, "battlog.db")
STATUS = os.path.join(os.environ.get("XDG_CACHE_HOME") or
                      os.path.expanduser("~/.cache"), "battlog-status")
KEEP_DAYS = 90


def db_open(path=DB):
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS battery("
                "ts INTEGER, device TEXT, pct INTEGER, charging INTEGER)")
    con.execute("CREATE INDEX IF NOT EXISTS battery_ts ON battery(ts, device)")
    con.execute("CREATE TABLE IF NOT EXISTS raw(ts INTEGER, device TEXT, hex TEXT)")
    con.execute("CREATE INDEX IF NOT EXISTS raw_ts ON raw(ts, device)")
    return con


def probe(wait=60, keep=KEEP_DAYS, db=DB, echo=print):
    """Lê todos os modelos plugados e grava. Devolve quantos responderam."""
    agora = int(time.time())
    lidos, brutos = [], []
    for mod, path in devices.present():
        try:
            r = mod.battery(path, wait)
        except PermissionError:
            echo(f"{mod.ID}: sem permissão em {path} — falta a regra udev "
                 "(udev/*.rules)")
            continue
        except OSError as e:
            echo(f"{mod.ID}: {path} respondeu erro {e.errno} ({e.strerror})")
            continue
        if r is None:
            echo(f"{mod.ID}: nada em {path} em {wait:.0f}s")
            continue
        lidos.append((agora, mod.ID, r.pct, r.charging))
        if r.raw:
            brutos.append((agora, mod.ID, r.raw.hex(" ")))
        carga = " (carregando)" if r.charging else ""
        echo(f"{mod.ID}: {r.pct}%{carga}" +
             (f"  [{r.raw.hex(' ')}]" if r.raw else ""))

    con = db_open(db)
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)", lidos)
    con.executemany("INSERT INTO raw VALUES (?,?,?)", brutos)
    cut = agora - keep * 86400
    dropped = sum(con.execute(f"DELETE FROM {t} WHERE ts < ?", (cut,)).rowcount
                  for t in ("battery", "raw"))
    con.commit()
    write_status(con)
    if dropped:
        echo(f"({dropped} amostras com mais de {keep} dias apagadas)")
    return len(lidos)


def recency(con):
    """id do modelo -> ts da última leitura. Desempata quem o painel mostra."""
    return {name: ts for name, ts in con.execute(
        "SELECT device, max(ts) FROM battery GROUP BY device")}


def status_text(con):
    """`chave valor` por linha — o que o painel lê. Um modelo por categoria.

    O valor vem da última linha do banco, não da rodada atual, de propósito: o
    receptor do mouse só fala com o mouse em uso, e mouse parado não gastou
    bateria, então repetir o último número é mais verdadeiro que apagá-lo. Quem
    morre de verdade é o cron, e isso aparece no `ts`: a extensão compara com o
    relógio e mostra "—" em vez de um número velho.
    """
    linhas = [f"ts {int(time.time())}"]
    recs = recency(con)
    for kind in devices.KINDS:
        mod, _, _ = devices.pick(kind, recency=recs)
        if mod is None:
            continue
        row = con.execute("SELECT pct FROM battery WHERE device = ? "
                          "ORDER BY ts DESC LIMIT 1", (mod.ID,)).fetchone()
        if row:
            linhas.append(f"{kind} {mod.ID} {row[0]}")
    return "\n".join(linhas) + "\n"


def write_status(con, path=STATUS):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"  # troca atômica: o painel relê a qualquer momento
    with open(tmp, "w") as f:
        f.write(status_text(con))
    os.replace(tmp, path)


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


def report_raw(con, days=7, echo=print):
    """Quais bytes variaram e como — é como se acha a bateria de um modelo novo."""
    start = int(time.time()) - days * 86400
    for name, in con.execute("SELECT DISTINCT device FROM raw WHERE ts >= ? "
                             "ORDER BY device", (start,)):
        samples = [(ts, bytes.fromhex(h)) for ts, h in con.execute(
            "SELECT ts, hex FROM raw WHERE device = ? AND ts >= ? ORDER BY ts",
            (name, start))]
        span = (samples[-1][0] - samples[0][0]) / 3600
        echo(f"\n=== {name} — {len(samples)} amostras em {span:.1f}h ===")
        echo(f"  primeira: {samples[0][1].hex(' ')}")
        echo(f"  última:   {samples[-1][1].hex(' ')}")
        muda = analyse(samples)
        if not muda:
            echo("  nenhum byte mudou ainda — deixe rodar mais tempo")
        for off, vals, veredito in muda:
            resumo = vals if len(vals) <= 12 else vals[:6] + ["..."] + vals[-5:]
            echo(f"  byte[{off:2}] {veredito}")
            echo(f"           {' '.join(str(v) for v in resumo)}")


def report_show(con, days=7, width=60, echo=print):
    """Timeline por modelo, escala fixa 0-100."""
    start = int(time.time()) - days * 86400
    step = days * 86400 / width
    if not con.execute("SELECT 1 FROM battery WHERE ts >= ? LIMIT 1",
                       (start,)).fetchone():
        echo("sem dados de bateria nessa janela — rode `kmctl probe`, ou "
             "`kmctl raw` para ver o que já foi juntado.")
        return 1
    echo(f"bateria — últimos {days:g} dia(s), 0-100% em escala fixa\n")
    largura = max(len(n) for n, in con.execute(
        "SELECT DISTINCT device FROM battery WHERE ts >= ?", (start,)))
    for name, in con.execute("SELECT DISTINCT device FROM battery "
                             "WHERE ts >= ? ORDER BY device", (start,)):
        sums = [None] * width
        for ts, pct in con.execute("SELECT ts, pct FROM battery WHERE "
                                   "device = ? AND ts >= ?", (name, start)):
            i = min(int((ts - start) / step), width - 1)
            sums[i] = pct if sums[i] is None else (sums[i] + pct) / 2
        vals = [v for v in sums if v is not None]
        last = con.execute("SELECT pct, charging FROM battery WHERE device = ? "
                           "ORDER BY ts DESC LIMIT 1", (name,)).fetchone()
        agora = f"{last[0]}%" + (" carregando" if last[1] else "")
        echo(f"{name:>{largura}} |{spark(sums)}| agora {agora}  "
             f"(min {min(vals):.0f} / max {max(vals):.0f}, "
             f"{len(vals)}/{width} intervalos com dado)")
    a = time.strftime("%d/%m %H:%M", time.localtime(start))
    echo(f"{'':>{largura}}  {a}" + " " * (width - len(a) - 5) + "agora")
    return 0
