"""Checagem do repo inteiro: `kmctl selftest`.

Cobre o que dá para cobrir sem hardware — e é de propósito que o F75 e o AJ139,
que não estão na mesa, sejam justamente os mais checados aqui: para eles, isto é
o único teste que existe.
"""
import contextlib
import io
import pathlib
import tempfile
import time

import battery
import devices
import wake
from devices import (ajazz_aj139, attackshark_k86, bluez_any, delux_m800pro,
                     delux_m900pro, freewolf_f75, power_supply_any,
                     vendor_probe)


def contrato():
    n = devices.check()
    assert n >= 8, f"esperava ao menos 5 modelos + 3 fontes, achei {n}"
    fontes = [m.ID for m in devices.modules() if getattr(m, "SOURCE", False)]
    assert len(fontes) >= 3, f"esperava as fontes genericas, achei {fontes}"
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


def deducao():
    """Modelo ganha de fonte quando os dois acham o **mesmo handle**.

    Isto nao tem par que dispare hoje: o unico que havia era o diretorio do fone
    contra o bluez_any, e o diretorio foi removido. A regra fica como rede de
    seguranca para o caso concreto de um aparelho com protocolo de fabricante que
    tambem apareca numa fonte generica -- e fica testada, porque maquina sem
    teste nem usuario e exatamente como se quebra em silencio.
    """
    class Modelo:
        ID, NAME, KIND, CAPS = "modelo_x", "Modelo X", "mouse", ("battery",)
        SOURCE = False
        find = staticmethod(lambda: "/dev/mesmo")

    class Fonte:
        ID, NAME, CAPS = "fonte_x", "Fonte X", ("battery",)
        SOURCE = True
        discover = staticmethod(lambda: [
            ("f_mesmo", "Visto pela fonte", "mouse", "/dev/mesmo"),
            ("f_outro", "Só a fonte vê", "headset", "/dev/outro"),
        ])

    real = devices.modules
    devices.modules = lambda: [Modelo, Fonte]
    try:
        got = devices.present()
    finally:
        devices.modules = real
    # o handle repetido sai com o nome e as caps do MODELO, nao da fonte
    assert [f.ident for f in got] == ["modelo_x", "f_outro"], [f.ident for f in got]
    assert got[0].name == "Modelo X" and got[0].mod is Modelo
    assert got[1].mod is Fonte

    # modelo que nao acha nada nao reserva handle nenhum
    Modelo.find = staticmethod(lambda: None)
    devices.modules = lambda: [Modelo, Fonte]
    try:
        got = devices.present()
    finally:
        devices.modules = real
    assert [f.ident for f in got] == ["f_mesmo", "f_outro"], [f.ident for f in got]

    # modulo que estoura nao derruba os outros (o cron nao pode morrer por isso)
    class Quebrado:
        ID, NAME, KIND, CAPS = "quebrado", "Quebrado", "mouse", ("battery",)
        SOURCE = False
        find = staticmethod(lambda: 1 / 0)

    devices.modules = lambda: [Quebrado, Fonte]
    try:
        # o aviso vai para stderr de proposito; aqui ele e esperado, e deixa-lo
        # passar sujaria a saida do selftest com um erro que nao e erro
        with contextlib.redirect_stderr(io.StringIO()) as ruido:
            got = devices.present()
    finally:
        devices.modules = real
    assert "quebrado" in ruido.getvalue(), "o modulo quebrado devia ter avisado"
    assert [f.ident for f in got] == ["f_mesmo", "f_outro"], [f.ident for f in got]
    return "deducao modelo-sobre-fonte ok"


def percentual():
    """A regra do que e percentual crivel. Vale para todo modulo e toda fonte.

    Estava copiada em seis parsers, e o lado Bluetooth tinha divergido para
    aceitar 0. Um teste so agora que a regra e uma so.
    """
    assert devices.pct_ok(1) and devices.pct_ok(100)
    # 0 fica de fora: e o valor que canal sem resposta devolve, nao bateria zerada
    assert not devices.pct_ok(0)
    assert not devices.pct_ok(101) and not devices.pct_ok(-1)
    assert not devices.pct_ok(None) and not devices.pct_ok("50")
    # e o mesmo criterio chega nos parsers
    frame = bytearray(bytes.fromhex(
        "0c 01 20 00 01 01 10 00 4d 38 30 32 25 01 00 70 04 ff 3a 00"))
    frame[18] = 0
    assert delux_m800pro.parse(bytes(frame)) is None
    frame[18] = 100
    assert delux_m800pro.parse(bytes(frame)).pct == 100
    return "regra de percentual ok, num lugar so"


def eco_do_seq():
    """O byte 4 tem que ecoar o seq mandado, senao a resposta e de outra pergunta.

    E o unico campo que distingue "esta e a resposta" de "isto e o buffer com a
    resposta anterior": as duas ecoam o opcode e as duas tem o `M802`.
    """
    real = bytes.fromhex("0c 01 20 00 05 01 10 00 4d 38 30 32 25 01 00 70 04"
                         " ff 3a 00")
    # sem exigir seq, qualquer um passa (e o que o selftest dos parsers usa)
    assert delux_m800pro.parse(real).pct == 58
    # exigindo, so o que bate
    assert delux_m800pro.parse(real, seq=5).pct == 58
    assert delux_m800pro.parse(real, seq=4) is None, "aceitou resposta anterior"
    assert delux_m800pro.parse(real, seq=1) is None
    return "eco do seq exigido no handshake"


def fontes_genericas():
    """As duas fontes de descoberta automatica, sem hardware.

    E o que faz um aparelho novo aparecer sozinho, entao um erro aqui nao da
    sintoma obvio: simplesmente nada aparece no painel.
    """
    # --- bluez_any: funcao pura sobre o dicionario do BlueZ ---
    def bt(icone="audio-headset", conectado=True, bateria=True, alias="Fone X"):
        d = {"org.bluez.Device1": {"Connected": conectado, "Address": "AA:BB:CC",
                                   "Alias": alias, "Icon": icone}}
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
    # o nome vem do Alias do BlueZ, que acompanha renomeacao — nao de codigo
    assert bluez_any.achados(bt(alias="Outro Nome"))[0][1] == "Outro Nome"
    assert bluez_any.achados({}) == []
    for _, _, kind, _ in bluez_any.achados(bt()):
        assert kind in devices.KINDS, kind

    # --- power_supply_any: le sysfs, entao testa contra um sysfs de mentira ---
    # nome e ultimo recurso: marca nenhuma promete conter a palavra certa
    assert power_supply_any.kind_por_nome("Logitech K380 Keyboard") == "keyboard"
    assert power_supply_any.kind_por_nome("Algum Mouse Sem Fio") == "mouse"
    assert power_supply_any.kind_por_nome("MX Master 3") == "other", \
        "nome de marca nao diz a categoria — e por isso que o proto vem antes"
    for k in ("keyboard", "mouse", "other"):
        assert k in devices.KINDS
    with tempfile.TemporaryDirectory() as d:
        def escreve(**campos):
            for k, v in campos.items():
                (pathlib.Path(d) / k).write_text(v + "\n")
        escreve(capacity="55", status="Discharging", scope="Device", type="Battery")
        # sem bInterfaceProtocol na arvore, cai no palpite pelo nome
        assert power_supply_any.kind_de(d, "Teclado Sem Fio") == "keyboard"
        assert power_supply_any.kind_de(d, "MX Master 3") == "other"
        # com o proto declarado, ele ganha do nome — inclusive contra um nome
        # que apontaria para o lado errado
        # "02" e nao "2": e o que o sysfs realmente escreve. A versao anterior
        # deste teste usava "2" e por isso passava com o codigo quebrado.
        escreve(bInterfaceProtocol="02")
        assert power_supply_any.kind_de(d, "Teclado Sem Fio") == "mouse", \
            "o que o aparelho declara tem que ganhar do nome"
        escreve(bInterfaceProtocol="01")
        assert power_supply_any.kind_de(d, "MX Master 3") == "keyboard"
        # aceitar as duas grafias: nao ha promessa de padding no sysfs
        escreve(bInterfaceProtocol="2")
        assert power_supply_any.kind_de(d, "Teclado") == "mouse"
        escreve(bInterfaceProtocol="00")  # 0 = nenhum dos dois
        assert power_supply_any.kind_de(d, "Algum Mouse") == "mouse"
        escreve(bInterfaceProtocol="lixo")
        assert power_supply_any.kind_de(d, "Algum Mouse") == "mouse"
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


def batimento():
    """As linhas comparadas para decidir se o cache mudou.

    O `ts` muda a cada leitura, entao comparar o texto inteiro nunca acusaria
    "igual" -- e era o bug: o painel era acordado a cada tique de 20 s a toa, e a
    otimizacao documentada nunca disparava.
    """
    a = "ts 100\ndev mouse m 50 0 Mouse\n"
    b = "ts 999\ndev mouse m 50 0 Mouse\n"
    c = "ts 999\ndev mouse m 49 0 Mouse\n"
    assert a != b, "o ts muda mesmo (e o motivo do bug)"
    assert battery.linhas_de_aparelho(a) == battery.linhas_de_aparelho(b), \
        "so o ts mudou: nao e mudanca"
    assert battery.linhas_de_aparelho(b) != battery.linhas_de_aparelho(c), \
        "o percentual mudou: e mudanca"
    assert battery.linhas_de_aparelho("ts 1\n") == []
    return "comparacao do cache ignora o ts"


def despertadores():
    """Os filtros de dica do wake.py, sem precisar de udev nem de BlueZ.

    Eles decidem SE vale reler, nunca O QUE ler. Errar para o lado frouxo custa
    releitura desnecessaria (tempestade de ioctl); errar para o lado apertado
    custa o tempo real -- o aparelho conecta e ninguem percebe ate o timer.
    """
    # uevent chega como blob com campos separados por \0
    hidraw = b"add@/devices/x\x00ACTION=add\x00SUBSYSTEM=hidraw\x00DEVNAME=hidraw9"
    assert wake.interessa_udev(hidraw)
    for sub in (b"usb", b"power_supply", b"bluetooth"):
        assert wake.interessa_udev(b"ACTION=add\x00SUBSYSTEM=" + sub)
    # disco e rede nao interessam: numa maquina de trabalho nao sao raros, e
    # cada um viraria releitura de hardware
    assert not wake.interessa_udev(b"ACTION=change\x00SUBSYSTEM=block")
    assert not wake.interessa_udev(b"ACTION=change\x00SUBSYSTEM=net")
    assert not wake.interessa_udev(b"")

    # gdbus monitor: uma linha por sinal
    assert wake.interessa_bluez(
        b"/org/bluez/hci0/dev_X: org.freedesktop.DBus.Properties.PropertiesChanged "
        b"('org.bluez.Device1', {'Connected': <false>}, @as [])")
    assert wake.interessa_bluez(b"... {'Percentage': <byte 0x5a>} ...")
    assert wake.interessa_bluez(b"... InterfacesAdded ...")
    # volume de transporte durante audio: o caso que faria o loop girar a esmo
    assert not wake.interessa_bluez(
        b"/org/bluez/hci0/dev_X/fd3: org.freedesktop.DBus.Properties."
        b"PropertiesChanged ('org.bluez.MediaTransport1', {'Volume': <127>}, @as [])")
    # as duas linhas de banner que o monitor imprime ao subir
    assert not wake.interessa_bluez(
        b"Monitoring signals from all objects owned by org.bluez")
    assert not wake.interessa_bluez(b"The name org.bluez is owned by :1.7")
    return "filtros dos despertadores ok"


def sonda_de_familia():
    """A validacao da sonda generica: e o que impede ela de inventar percentual.

    Ela ESCREVE em aparelho desconhecido, entao as guardas sao a coisa mais
    importante do modulo. Quatro condicoes independentes, e cada uma testada
    quebrada em separado.
    """
    real = bytes.fromhex("0c 01 20 00 03 01 10 00 4d 38 30 32 25 01 00 70 04"
                         " ff 3a 00")
    assert vendor_probe.valida(real, 3) == ("M802", 58)
    # seq: e o que distingue esta resposta da anterior no mesmo buffer
    assert vendor_probe.valida(real, 4) is None
    for nome, off, val in (("opcode", 2, 0x21), ("percentual 0", 18, 0),
                           ("percentual 101", 18, 101)):
        b = bytearray(real); b[off] = val
        assert vendor_probe.valida(bytes(b), 3) is None, nome
    # tag ilegivel: e a assinatura de modelo, e sem ela sobra pouca evidencia
    for tag in (b"\x00\x00\x00\x00", b"\xff\xfe\xfd\xfc"):
        b = bytearray(real); b[8:12] = tag
        assert vendor_probe.valida(bytes(b), 3) is None, tag
    assert vendor_probe.valida(bytes(20), 1) is None, "frame de zeros"
    assert vendor_probe.valida(b"", 1) is None
    assert vendor_probe.valida(real[:19], 3) is None, "frame curto"

    # a pre-condicao estrutural: sem o report 0x0c declarado, nada e enviado
    assert vendor_probe.declara_canal(bytes.fromhex("06 00 ff 09 01 a1 01 85 0c"
                                                    " 09 01 b1 02 c0"))
    assert not vendor_probe.declara_canal(b""), "descritor vazio"
    # tem Feature mas o report id e outro
    assert not vendor_probe.declara_canal(bytes.fromhex("85 05 b1 02"))
    # tem o report 0x0c mas nenhum Feature
    assert not vendor_probe.declara_canal(bytes.fromhex("85 0c 81 02"))

    # modelo com diretorio proprio nao e sondado: escrever num aparelho que ja
    # funciona nao tem upside, e o diretorio sabe fazer melhor
    reivindicados = vendor_probe._reivindicados()
    assert delux_m800pro.IDS[0] in reivindicados, \
        "o ID do M800 PRO tem que estar reivindicado"
    return "guardas da sonda de familia ok"


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

    # Found fabricado, e nao devices.present(): antes este bloco inteiro era
    # pulado numa maquina sem hardware -- exatamente a maquina que o selftest
    # existe para cobrir -- e ainda chamava present() duas vezes, o que um
    # aparelho entrando no meio fazia falhar.
    falsos = [
        devices.Found(None, "mouse_x", "Mouse X", "mouse", "/dev/fake"),
        # nome hostil: vem do Alias do BlueZ ou do HID_NAME, nao do repo. Um \n
        # aqui injetaria uma linha `dev` e o painel desenharia aparelho fantasma.
        devices.Found(None, "bt_1", "Fone\ndev keyboard bt_falso 99 1 Fantasma",
                      "headset", "/org/bluez/x"),
        devices.Found(None, "sem_dado", "Sem leitura", "other", "/dev/fake2"),
    ]
    con.executemany("INSERT INTO battery VALUES (?,?,?,?)",
                    [(now, "mouse_x", 42, 1), (now, "bt_1", 90, None)])
    txt = battery.status_text(con, falsos).splitlines()
    assert txt[0].startswith("ts ") and int(txt[0][3:]) > 1_700_000_000, txt
    # 2 linhas: o terceiro Found nao tem leitura no banco e nao entra
    assert len(txt) == 3, txt
    for linha in txt[1:]:
        campos = linha.split(" ")
        assert campos[0] == "dev", linha
        assert campos[1] in devices.KINDS, linha
        assert campos[3].isdigit(), linha
        assert campos[4] in ("0", "1", "-"), linha
        # o nome vem por ultimo justamente porque pode ter espaco
        assert len(campos) >= 6 and campos[5], linha
    assert txt[1] == f"dev mouse mouse_x 42 1 Mouse X", txt[1]
    assert txt[2] == "dev headset bt_1 90 - Fone dev keyboard bt_falso 99 1 Fantasma", txt[2]
    return "banco, poda e formato do status ok"


def main():
    for f in (contrato, parsers, pacotes_f75, pacotes_m800pro, percentual,
              eco_do_seq, fontes_genericas, sonda_de_familia, deducao,
              batimento, despertadores, analise, banco):
        print(f"  {f():.<60} ok")
    print("selftest ok")
    return 0
