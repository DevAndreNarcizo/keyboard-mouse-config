"""Checagem do repo inteiro: `kmctl selftest`.

Cobre o que dá para cobrir sem hardware — e é de propósito que o F75 e o AJ139,
que não estão na mesa, sejam justamente os mais checados aqui: para eles, isto é
o único teste que existe.
"""
import sqlite3
import time

import battery
import devices
from devices import ajazz_aj139, attackshark_k86, delux_m900pro, freewolf_f75


def contrato():
    n = devices.check()
    assert n >= 4, f"esperava ao menos os 4 modelos de casa, achei {n}"
    return f"contrato ok em {n} modelos"


def parsers():
    """Cada modelo contra um frame real, tirado do log ou do PROTOCOL.md."""
    r = attackshark_k86.parse(bytes.fromhex("00 1e 00 00 01 01 01 00"))
    assert (r.pct, r.charging) == (30, None), r
    # byte 3 em 1 NÃO vira "carregando": ele oscila sozinho (medido em 1389 frames)
    r = attackshark_k86.parse(bytes.fromhex("00 51 00 01 01 01 01 00"))
    assert (r.pct, r.charging) == (81, None), r
    # frame desalinhado (um byte a menos) logo depois de o dongle enumerar
    assert attackshark_k86.parse(bytes.fromhex("00 00 00 01 01 01 01 00")) is None

    r = delux_m900pro.parse(bytes.fromhex("03 50 41 01 42"))
    assert (r.pct, r.charging) == (66, None), r
    assert delux_m900pro.parse(bytes.fromhex("03 50 41 01 00")) is None

    # AJ139: 0xFA com marker 0xD0 no byte 8 e checksum dos bytes 4..64 no byte 3
    pkt = bytearray(64)
    pkt[0], pkt[1], pkt[8], pkt[9], pkt[10] = 0xAA, 0xFA, 0xD0, 77, 0
    pkt[3] = sum(pkt[4:64]) & 0xFF
    assert ajazz_aj139.parse(bytes(pkt)) == (77, 0, bytes(pkt[:16]))
    ruim = bytearray(pkt)
    ruim[8] = 0x00  # sem o marker é pacote de DPI, não de bateria
    assert ajazz_aj139.parse(bytes(ruim)) is None
    ruim = bytearray(pkt)
    ruim[3] ^= 0xFF  # checksum quebrado = pacote picado
    assert ajazz_aj139.parse(bytes(ruim)) is None
    return "parsers ok nos 4 modelos"


def pacotes_f75():
    """Os bytes que o F75 põe no fio, contra o que o PROTOCOL.md diz.

    É o que substitui ter o teclado na mesa: se alguém mexer no build() ou nas
    constantes, isto quebra antes de o hardware voltar e mostrar em silêncio.
    """
    _, log = freewolf_f75.remap(None, "z", "printscreen", dry=True)
    # PROTOCOL.md: "04 02 1d 46 deixa Fn+Z = Print Screen", validado no hardware
    assert log[0].startswith(">> aa 55 cc 33 04 02 1d 46"), log[0]
    _, log = freewolf_f75.remap(None, "v", "z", dry=True)
    assert log[0].startswith(">> aa 55 cc 33 04 02 19 1d"), log[0]

    # 0x07: os cinco campos entram como valor-1, menos direção e cor
    _, log = freewolf_f75.light(None, mode=7, brightness=5, speed=3,
                                direction=0, color=0, dry=True)
    assert log[0].startswith(">> aa 55 cc 33 07 06 04 02 00 00"), log[0]

    # 0x0C: item data do combo, não o índice
    _, log = freewolf_f75.sleep(None, "never", dry=True)
    assert log[0].startswith(">> aa 55 cc 33 0c 04"), log[0]

    # custom: 0x07(modo 24) + 0x0B + 0x09 + 2 bancos x 6 pacotes = 15
    msg, log = freewolf_f75.rgb(None, "00ff80", dry=True)
    assert len(log) == 15, f"{len(log)} pacotes, esperava 15"
    assert log[0].startswith(">> aa 55 cc 33 07 17"), log[0]  # 24-1 = 0x17
    assert log[3].startswith(">> aa 55 cc 33 f0 00 ff 80 00 ff 80"), log[3]
    # off manda 010101 e não 000000: preto é transparente no stream
    _, log = freewolf_f75.off(None, dry=True)
    assert log[3].startswith(">> aa 55 cc 33 f0 01 01 01"), log[3]

    for nome, err in (("mode", dict(mode=0)), ("brightness", dict(brightness=9))):
        try:
            freewolf_f75.light(None, dry=True, **err)
        except ValueError:
            pass
        else:
            raise AssertionError(f"light aceitou {nome} fora da faixa")
    return "pacotes do F75 batem com o PROTOCOL.md"


def analise():
    def s(*seqs):
        return [(i, bytes(b)) for i, b in enumerate(seqs)]

    r = battery.analyse(s([1, 80], [1, 79], [1, 78]))
    assert len(r) == 1 and r[0][0] == 1 and "CANDIDATO" in r[0][2], r
    assert "CANDIDATO" in battery.analyse(s([90], [88], [99], [97]))[0][2]
    assert "CANDIDATO" not in battery.analyse(s([10], [90], [10], [90]))[0][2]
    assert "CANDIDATO" not in battery.analyse(s([200], [150], [120]))[0][2]
    assert battery.analyse(s([5, 5], [5, 5])) == []
    assert battery.spark([None, 0, 50, 100]) == " ▁▄█"
    return "análise e sparkline ok"


def banco():
    con = battery.db_open(":memory:")
    now = int(time.time())
    con.executemany("INSERT INTO raw VALUES (?,?,?)",
                    [(now - 200 * 86400, "x", "00"), (now, "x", "01")])
    con.execute("DELETE FROM raw WHERE ts < ?", (now - 90 * 86400,))
    assert con.execute("SELECT count(*) FROM raw").fetchone()[0] == 1

    con.executemany("INSERT INTO battery VALUES (?,?,?,?)", [
        (1, "attackshark_k86", 50, None), (2, "attackshark_k86", 49, None),
        (1, "delux_m900pro", 70, None)])
    assert battery.recency(con) == {"attackshark_k86": 2, "delux_m900pro": 1}

    txt = battery.status_text(con).splitlines()
    assert txt[0].startswith("ts ") and int(txt[0][3:]) > 1_700_000_000, txt
    # o resto depende do que está plugado agora; o formato é que importa
    for linha in txt[1:]:
        kind, ident, pct = linha.split()
        assert kind in devices.KINDS and pct.isdigit(), linha
    return "banco, poda e formato do status ok"


def main():
    for f in (contrato, parsers, pacotes_f75, analise, banco):
        print(f"  {f():.<60} ok")
    print("selftest ok")
    return 0
