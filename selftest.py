"""Checagem do repo inteiro: `kmctl selftest`.

Cobre o que dá para cobrir sem hardware — e é de propósito que o F75 e o AJ139,
que não estão na mesa, sejam justamente os mais checados aqui: para eles, isto é
o único teste que existe.
"""
import pathlib
import sqlite3
import tempfile
import time

import battery
import devices
from devices import (ajazz_aj139, attackshark_k86, bluez_any, delux_m800pro,
                     delux_m900pro, freewolf_f75, jbl_wave_buds_2,
                     power_supply_any)


def contrato():
    n = devices.check()
    assert n >= 8, f"esperava ao menos 6 modelos + 2 fontes, achei {n}"
    fontes = [m.ID for m in devices.modules() if getattr(m, "SOURCE", False)]
    assert len(fontes) >= 2, f"esperava as fontes genericas, achei {fontes}"
    return f"contrato ok em {n} modulos ({len(fontes)} fontes)"


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
    # M800 PRO: frame medido no hardware (58%, sem carga). Canal e
    # request/response, entao o parser exige o opcode ecoado no byte 2 E a
    # assinatura "M802" nos bytes 8..11 - sem isso, resposta de outro opcode
    # tem o mesmo tamanho e viraria percentual falso.
    real = bytes.fromhex("0c 01 20 00 01 01 10 00 4d 38 30 32 25 01 00 70 04 ff"
                         " 3a 00 ff 01 00 00 87 5c 08 3f ff f4 6f 2d 39")
    r = delux_m800pro.parse(real)
    assert (r.pct, r.charging) == (58, 0), r
    assert r.raw == real, "raw tem que guardar o frame inteiro"
    # byte 19 nao e booleano: 0 sem cabo, 1 carregando, 2 visto so a 100%.
    # Valor fora dos tres e estado desconhecido -> None, nao um palpite.
    for b19, esperado in ((0, 0), (1, 1), (2, 1), (3, None), (0xff, None)):
        f = bytearray(real)
        f[19] = b19
        assert delux_m800pro.parse(bytes(f)).charging is esperado \
            or delux_m800pro.parse(bytes(f)).charging == esperado, \
            f"byte19={b19} deu {delux_m800pro.parse(bytes(f)).charging}"
    for nome, mexe in (
            ("opcode nao ecoado", {2: 0x21}),
            ("sem a assinatura M802", {8: 0x00}),
            ("percentual em 0", {18: 0}),
            ("percentual acima de 100", {18: 200})):
        ruim = bytearray(real)
        for off, val in mexe.items():
            ruim[off] = val
        assert delux_m800pro.parse(bytes(ruim)) is None, nome
    assert delux_m800pro.parse(real[:19]) is None, "frame curto"
    return "parsers ok nos 5 modelos"


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


def pacotes_m800pro():
    """Os bytes que o M800 PRO poria no fio, contra os literais do driver de
    referencia (xb-bx/m800-pro-driver).

    `battery` foi executado contra o hardware; estes tres nao. Isto e o que
    segura: se alguem mexer nos TEMPLATES ou nos offsets, quebra aqui em vez de
    desconfigurar o mouse de alguem em silencio.
    """
    # 0x06: cor nos 5 estagios, bytes 7..21. Os bytes 22..32 do template nao
    # estao explicados (o len diz 24 e so 15 sao cor) e sao preservados.
    _, log = delux_m800pro.rgb(None, "00ff80", dry=True)
    assert log[0] == (">> 0c 01 06 00 01 01 18 00 ff 80 00 ff 80 00 ff 80 00 ff"
                      " 80 00 ff 80 00 ff ff ff ff ff ff ff ff 00 00"), log[0]
    # --only sao estagios de DPI, nao teclas: so o estagio 3 (bytes 13..15) muda,
    # e os outros quatro caem no padrao do template - o 0x06 escreve os 5 juntos
    # e nao ha opcode que leia os atuais, entao preservar e impossivel.
    msg, log = delux_m800pro.rgb(None, "ff0000", only="3", dry=True)
    assert log[0] == (">> 0c 01 06 00 01 01 18 00 ff 00 00 ff 00 ff 00 00 ff 00"
                      " ff ff ff 00 00 ff ff ff ff ff ff ff ff 00 00"), log[0]
    assert "padrao de fabrica" in msg or "padrão de fábrica" in msg, msg

    # forma de 5 cores: controle total, um RRGGBB por estagio nos bytes 7..21
    _, log = delux_m800pro.rgb(None, "ff0000,00ff00,0000ff,ffffff,000000",
                               dry=True)
    assert log[0] == (">> 0c 01 06 00 01 01 18 ff 00 00 00 ff 00 00 00 ff ff ff"
                      " ff 00 00 00 00 ff ff ff ff ff ff ff ff 00 00"), log[0]

    # 0x0b: minutos direto no byte 7
    _, log = delux_m800pro.sleep(None, 5, dry=True)
    assert log[0].startswith(">> 0c 01 0b 00 01 01 02 05 00"), log[0]

    # 0x04: byte 7 = botao, 8..10 = os 3 bytes da funcao (keys.h)
    _, log = delux_m800pro.remap(None, "wheel", "playpause", dry=True)
    assert log[0].startswith(">> 0c 01 04 00 01 01 04 02 80 cd 00 00"), log[0]
    _, log = delux_m800pro.remap(None, "mouse4", "dpilock/1200", dry=True)
    assert log[0].startswith(">> 0c 01 04 00 01 01 04 04 50 0b 00 00"), log[0]

    # o que tem que ser recusado antes de chegar no fio
    for nome, chamada in (
            ("cor invalida", lambda: delux_m800pro.rgb(None, "xyz", dry=True)),
            ("estagio fora de 1..5",
             lambda: delux_m800pro.rgb(None, "00ff00", only="9", dry=True)),
            ("2 cores (nem 1 nem 5)",
             lambda: delux_m800pro.rgb(None, "00ff00,ff0000", dry=True)),
            ("5 cores junto com --only",
             lambda: delux_m800pro.rgb(None, "ff0000,00ff00,0000ff,fff,000000",
                                       only="2", dry=True)),
            ("sleep never", lambda: delux_m800pro.sleep(None, "never", dry=True)),
            ("sleep fora de 3..10", lambda: delux_m800pro.sleep(None, 2, dry=True)),
            ("botao inexistente",
             lambda: delux_m800pro.remap(None, "mouse9", "mute", dry=True)),
            ("funcao inexistente",
             lambda: delux_m800pro.remap(None, "lmb", "nada", dry=True))):
        try:
            chamada()
        except ValueError:
            pass
        else:
            raise AssertionError(f"M800 PRO aceitou {nome}")
    return "pacotes do M800 PRO batem com o driver de referencia"


def bluetooth():
    """O matcher do lado Bluetooth, sem precisar de Bluetooth ligado.

    `bluez_match` e separada de `find_bluez` justamente para isto: e funcao
    pura sobre o dicionario que o BlueZ devolve.
    """
    def obj(connected=True, modalias="bluetooth:v0ECBp2100d001F", bateria=True):
        d = {"org.bluez.Device1": {"Connected": connected, "Modalias": modalias}}
        if bateria:
            d["org.bluez.Battery1"] = {"Percentage": 90}
        return {"/org/bluez/hci0/dev_X": d}

    ids = jbl_wave_buds_2.IDS
    assert devices.bluez_match(obj(), ids) == "/org/bluez/hci0/dev_X"
    # pareado mas desconectado nao conta: continua no BlueZ e sem bateria
    assert devices.bluez_match(obj(connected=False), ids) is None
    # conectado sem Battery1 tambem nao: mostraria "plugado" sem numero
    assert devices.bluez_match(obj(bateria=False), ids) is None
    # outro aparelho conectado nao vira este modelo
    assert devices.bluez_match(obj(modalias="bluetooth:v1234p5678d0001"),
                               ids) is None
    # o `d` do modalias e release de firmware: mudar ele NAO deve quebrar o match
    assert devices.bluez_match(obj(modalias="bluetooth:v0ECBp2100d9999"),
                               ids) == "/org/bluez/hci0/dev_X"
    assert devices.bluez_match({}, ids) is None
    # sem falar com o BlueZ, tudo devolve vazio em vez de estourar
    assert devices.bluez_objects.__doc__ and devices._busctl("nao-existe") is None
    return "matcher do Bluetooth ok"


def fontes_genericas():
    """As duas fontes de descoberta automatica, sem hardware.

    E o que faz um aparelho novo aparecer sozinho, entao um erro aqui nao da
    sintoma obvio: simplesmente nada aparece no painel.
    """
    # --- bluez_any: funcao pura sobre o dicionario do BlueZ ---
    def bt(icone="audio-headset", conectado=True, bateria=True):
        d = {"org.bluez.Device1": {"Connected": conectado, "Address": "AA:BB:CC",
                                   "Alias": "Fone X", "Icon": icone}}
        if bateria:
            d["org.bluez.Battery1"] = {"Percentage": 77}
        return {"/org/bluez/hci0/dev_AA": d}

    got = bluez_any.achados(bt())
    assert got == [("bt_aabbcc", "Fone X", "headset", "/org/bluez/hci0/dev_AA")], got
    assert bluez_any.achados(bt(conectado=False)) == []
    assert bluez_any.achados(bt(bateria=False)) == []
    assert bluez_any.achados(bt(icone="input-mouse"))[0][2] == "mouse"
    assert bluez_any.achados(bt(icone="input-keyboard"))[0][2] == "keyboard"
    # icone que nao conhecemos vira "other", nao um palpite
    assert bluez_any.achados(bt(icone="coisa-nova"))[0][2] == "other"
    for _, _, kind, _ in bluez_any.achados(bt()):
        assert kind in devices.KINDS, kind

    # --- power_supply_any: le sysfs, entao testa contra um sysfs de mentira ---
    assert power_supply_any.kind_de("Logitech K380 Keyboard") == "keyboard"
    assert power_supply_any.kind_de("algum treco") == "other"
    with tempfile.TemporaryDirectory() as d:
        def escreve(**campos):
            for k, v in campos.items():
                (pathlib.Path(d) / k).write_text(v + "\n")
        escreve(capacity="55", status="Discharging", scope="Device", type="Battery")
        r = power_supply_any.battery(d)
        assert (r.pct, r.charging, r.raw) == (55, 0, b""), r
        escreve(status="Charging")
        assert power_supply_any.battery(d).charging == 1
        # sem status o kernel nao disse nada: None, nao "descarregando"
        escreve(status="")
        assert power_supply_any.battery(d).charging is None
        escreve(capacity="0")
        assert power_supply_any.battery(d) is None, "0% e leitura invalida aqui"
        escreve(capacity="nao-numero")
        assert power_supply_any.battery(d) is None
    return "fontes genericas ok"


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

    # da ao status_text o que ele precisa para emitir uma linha por aparelho
    # presente; sem isso, numa maquina sem nada plugado so sairia o `ts`.
    for f in devices.present():
        con.execute("INSERT INTO battery VALUES (?,?,?,?)", (now, f.ident, 42, 1))
    txt = battery.status_text(con).splitlines()
    assert txt[0].startswith("ts ") and int(txt[0][3:]) > 1_700_000_000, txt
    assert len(txt) == 1 + len(devices.present()), txt
    for linha in txt[1:]:
        campos = linha.split(" ")
        assert campos[0] == "dev", linha
        assert campos[1] in devices.KINDS, linha
        assert campos[3].isdigit(), linha
        assert campos[4] in ("0", "1", "-"), linha
        # o nome vem por ultimo justamente porque pode ter espaco
        assert len(campos) >= 6 and campos[5], linha
    return "banco, poda e formato do status ok"


def main():
    for f in (contrato, parsers, pacotes_f75, pacotes_m800pro, bluetooth,
              fontes_genericas, analise, banco):
        print(f"  {f():.<60} ok")
    print("selftest ok")
    return 0
