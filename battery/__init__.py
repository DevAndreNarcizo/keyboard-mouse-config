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
import wake

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


def ler_todos(wait=0, echo=print):
    """[(Found, Reading)] de tudo que respondeu agora. **Não toca no banco.**

    Separado do `probe` porque o `watch` lê muito mais vezes do que grava: o
    cache do painel quer o número de agora, o histórico não quer uma linha a
    cada 20 s.
    """
    out = []
    for f in devices.present():
        try:
            r = f.mod.battery(f.handle, wait)
        except PermissionError:
            echo(f"{f.ident}: sem permissão em {f.handle} — falta a regra udev "
                 "(udev/*.rules)")
            continue
        except OSError as e:
            echo(f"{f.ident}: {f.handle} respondeu erro {e.errno} ({e.strerror})")
            continue
        if r is None:
            echo(f"{f.ident}: nada em {f.handle} em {wait:.0f}s")
            continue
        carga = " (carregando)" if r.charging else ""
        echo(f"{f.ident}: {r.pct}%{carga}" +
             (f"  [{r.raw.hex(' ')}]" if r.raw else ""))
        out.append((f, r))
    return out


def gravar(con, leituras, keep=KEEP_DAYS, echo=print):
    """Põe as leituras no histórico e poda o que passou de `keep` dias."""
    agora = int(time.time())
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)",
                    [(agora, f.ident, r.pct, r.charging) for f, r in leituras])
    con.executemany("INSERT INTO raw VALUES (?,?,?)",
                    [(agora, f.ident, r.raw.hex(" ")) for f, r in leituras
                     if r.raw])
    cut = agora - keep * 86400
    dropped = sum(con.execute(f"DELETE FROM {t} WHERE ts < ?", (cut,)).rowcount
                  for t in ("battery", "raw"))
    con.commit()
    if dropped:
        echo(f"({dropped} amostras com mais de {keep} dias apagadas)")
    return len(leituras)


def probe(wait=60, keep=KEEP_DAYS, db=DB, echo=print):
    """Uma rodada: lê, grava e atualiza o cache. É o que um cron roda.

    Continua existindo para quem prefere cron ao serviço — o `watch` faz o mesmo
    em loop e com despertador.
    """
    leituras = ler_todos(wait, echo)
    con = db_open(db)
    n = gravar(con, leituras, keep, echo)
    write_status(con, texto=status_text(con, [f for f, _ in leituras], leituras))
    return n


def linhas_de_aparelho(texto):
    """Só as linhas `dev` — o `ts` fora. É o que se compara para saber se algo
    mudou de verdade, já que o `ts` muda sempre."""
    return [l for l in texto.splitlines() if l.startswith("dev ")]


def watch(interval=20, record=600, heartbeat=300, wait=0, keep=KEEP_DAYS,
          db=DB, echo=print):
    """Mantém o cache do painel em dia até ser morto. É o que o serviço roda.

    **Duas cadências, de propósito.** O cache é reescrito assim que algum número
    muda ou um aparelho entra/sai; o histórico recebe uma amostra a cada
    `record` segundos. Gravar a cada 20 s encheria o banco com ~4300 linhas por
    dia por aparelho sem dizer nada novo — bateria não muda nessa velocidade, e o
    `show` desenha pior com ruído.

    O que dá tempo real de verdade é o despertador: conectar ou desconectar um
    fone aparece em menos de um segundo. **Percentual não fica mais rápido que o
    aparelho o reporta** — reler mais vezes não cria informação que ninguém
    mandou.

    O cache é gravado quando as **linhas de aparelho** mudam, ou a cada
    `heartbeat` segundos. As duas condições existem por motivos opostos e as duas
    são necessárias:

    - comparar só as linhas de aparelho, e não o texto todo, porque o `ts` muda a
      cada leitura — comparar o texto inteiro nunca acusaria "igual", e o painel
      seria acordado a cada tique à toa (era o que acontecia);
    - gravar mesmo sem mudança, de vez em quando, porque o `ts` é **batimento**:
      é por ele que a extensão sabe que quem escreve está vivo. Congelá-lo faria
      o painel exibir número velho como se fosse atual, que é justamente o que o
      limite de 30 min existe para evitar.
    """
    con = db_open(db)
    despertador = wake.Wake()
    quais = ", ".join(despertador.sources) or "nenhum (só o timer)"
    echo(f"watch: timer {interval}s, histórico {record}s, batimento "
         f"{heartbeat}s, despertadores: {quais}")
    for f in despertador.falhas:
        echo(f"  despertador indisponível: {f}")
    calado = (lambda *_a, **_k: None)
    anteriores, ultimo_registro, ultima_escrita = None, 0.0, 0.0
    try:
        while True:
            leituras = ler_todos(wait, calado)
            agora = time.monotonic()
            if agora - ultimo_registro >= record:
                gravar(con, leituras, keep, calado)
                ultimo_registro = agora
            texto = status_text(con, [f for f, _ in leituras], leituras)
            linhas = linhas_de_aparelho(texto)
            mudou = linhas != anteriores
            if mudou or agora - ultima_escrita >= heartbeat:
                write_status(con, texto=texto)
                ultima_escrita = agora
                if mudou:  # log só do que é notícia
                    echo("".join(f"  {l}\n" for l in linhas)
                         or "  (nada com bateria)")
                anteriores = linhas
            despertador.wait(interval)
    except KeyboardInterrupt:
        pass
    finally:
        despertador.close()
    return 0


def status_text(con, achados=None, leituras=None):
    """O que o painel lê. **Uma linha por aparelho presente**, não por categoria:

        ts 1787588709
        dev mouse delux_m800pro 100 - Delux M800 PRO
        dev headset bt_501b6a0cf973 90 - JBL Wave Buds 2

    Campos: `dev <kind> <ident> <pct> <carga>` e o nome legível no fim, que é o
    único que pode ter espaço. Carga é `0`, `1` ou `-` (desconhecida).

    Era um-aparelho-por-categoria, com o `devices.pick` desempatando. Passou a ser
    por aparelho porque um fone, um mouse e um teclado sem fio ao mesmo tempo são
    três coisas para mostrar, não uma escolha a fazer.

    O valor é o da leitura de agora quando ela existe (`leituras`), e a última
    linha do banco quando o aparelho está presente mas não respondeu. Isso é de
    propósito: o receptor do mouse só fala com o mouse em uso, e mouse parado não
    gastou bateria — repetir o último número é mais verdadeiro que apagá-lo. Quem
    morre de verdade é o cron ou o serviço, e isso aparece no `ts`: a extensão
    compara com o relógio e mostra "—" em vez de um número velho.
    """
    vivas = {f.ident: r for f, r in (leituras or ())}
    linhas = [f"ts {int(time.time())}"]
    for f in devices.present() if achados is None else achados:
        r = vivas.get(f.ident)
        if r is not None:
            row = (r.pct, r.charging)
        else:
            row = con.execute(
                "SELECT pct, charging FROM battery WHERE device = ? "
                "ORDER BY ts DESC LIMIT 1", (f.ident,)).fetchone()
        if not row:
            continue
        carga = "-" if row[1] is None else str(int(row[1]))
        # O nome é o único campo livre, e **não é nosso**: vem do `Alias` do
        # BlueZ (que o próprio aparelho anuncia) ou do `HID_NAME`. Um `\n` ali
        # injetaria uma linha `dev` inteira e o painel desenharia um aparelho
        # que não existe. Colapsar espaço em branco resolve na origem.
        nome = " ".join(f.name.split()) or f.ident
        linhas.append(f"dev {f.kind} {f.ident} {row[0]} {carga} {nome}")
    return "\n".join(linhas) + "\n"


def write_status(con, path=STATUS, achados=None, texto=None):
    """`texto` pronto evita gerar duas vezes — é o que faz o `kmctl status`
    imprimir exatamente o que gravou, em vez de descobrir o hardware de novo
    e poder discordar do arquivo."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"  # troca atômica: o painel relê a qualquer momento
    with open(tmp, "w") as f:
        f.write(status_text(con, achados) if texto is None else texto)
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
