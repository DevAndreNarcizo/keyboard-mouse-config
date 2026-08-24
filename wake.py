"""Despertadores: avisar que o hardware **pode** ter mudado.

Regra que mantém isto simples e é o que separa desenho de gambiarra: **um
despertador nunca é fonte de dado.** Ele só diz "vai olhar de novo"; quem lê é
sempre o caminho normal (`devices.present()` + `mod.battery()`). Consequências:

- não existe um segundo parser de D-Bus ou de uevent para manter em sincronia
  com o primeiro — o que os despertadores entregam é um bit, não um percentual;
- despertador que morre ou falta degrada para "só o timer", nunca para número
  errado. Por isso todo construtor aqui engole erro e o `sources` diz o que
  sobrou de pé.

Dois deles, os dois sem root (medido):

- **udev**, por socket netlink, stdlib pura. Pega plugar e desplugar USB.
- **BlueZ**, por `gdbus monitor`. Pega conectar e desconectar na hora. É a única
  parte do repo que depende do `gdbus` (glib2); sem ele, presença de Bluetooth
  passa a depender do intervalo do timer, e nada mais quebra.
"""
import os
import selectors
import socket
import subprocess
import time

NETLINK_KOBJECT_UEVENT = 15
GRUPO_UDEV = 2  # eventos já processados pelas regras, não os crus do kernel

# O `gdbus monitor` é falante durante áudio (volume de transporte, por exemplo).
# Só estas palavras interessam, e filtrar aqui é filtro de *dica*, não parser:
# nenhum valor é extraído da linha, ela só decide se vale reler.
BLUEZ_INTERESSA = (b"Connected", b"Battery1", b"Percentage",
                   b"InterfacesAdded", b"InterfacesRemoved")

# Mesma ideia no udev: só os subsistemas de onde bateria pode aparecer ou sair.
# Sem isto, uevent de disco ou de rede — que numa máquina de trabalho não são
# raros — dispararia releitura de hardware sem motivo nenhum.
UDEV_INTERESSA = (b"SUBSYSTEM=hidraw", b"SUBSYSTEM=usb",
                  b"SUBSYSTEM=power_supply", b"SUBSYSTEM=bluetooth")


def interessa_udev(blob):
    """Este uevent pode ter mexido em algo com bateria?

    Função pura, e é o único lugar onde o blob é olhado. Nenhum valor sai dele:
    a resposta é um bit. Interpretar uevent aqui seria o começo de um segundo
    descobridor de hardware, competindo com o `devices.present()`.
    """
    return any(p in blob for p in UDEV_INTERESSA)


def interessa_bluez(linha):
    """Esta linha do `gdbus monitor` merece uma releitura?

    O monitor é falante durante áudio (volume de transporte, por exemplo), e sem
    este filtro cada sinal viraria releitura de hardware — tempestade de ioctl no
    lugar de tempo real.
    """
    return any(p in linha for p in BLUEZ_INTERESSA)


class _Udev:
    nome = "udev"

    def __init__(self):
        self.sock = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM,
                                  NETLINK_KOBJECT_UEVENT)
        self.sock.setblocking(False)
        self.sock.bind((0, GRUPO_UDEV))

    def fileno(self):
        return self.sock.fileno()

    def drain(self):
        """Consome o que chegou. True se algum evento foi de subsistema que
        interessa.

        O blob é olhado só para essa decisão — nenhum valor sai dele. Interpretar
        uevent aqui seria o começo de um segundo descobridor de hardware.
        """
        veio = False
        while True:
            try:
                blob = self.sock.recv(8192)
            except (BlockingIOError, InterruptedError):
                return veio
            except OSError:
                return veio
            if interessa_udev(blob):
                veio = True

    def close(self):
        self.sock.close()


class _Bluez:
    nome = "bluez"

    def __init__(self):
        self.proc = subprocess.Popen(
            ("gdbus", "monitor", "--system", "--dest", "org.bluez"),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        os.set_blocking(self.proc.stdout.fileno(), False)
        self.resto = b""

    def fileno(self):
        return self.proc.stdout.fileno()

    def drain(self):
        veio = False
        while True:
            try:
                pedaco = os.read(self.fileno(), 65536)
            except (BlockingIOError, InterruptedError):
                break
            except OSError:
                break
            if not pedaco:  # o monitor morreu
                break
            self.resto += pedaco
            *linhas, self.resto = self.resto.split(b"\n")
            for linha in linhas:
                if interessa_bluez(linha):
                    veio = True
        return veio

    def vivo(self):
        return self.proc.poll() is None

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()


class Wake:
    """Espera até `timeout` segundos, ou até algum despertador avisar.

    `wait(timeout)` devolve True se foi acordado por evento, False se foi o
    timeout — quem chama relê nos dois casos, a diferença serve para log.
    """

    def __init__(self, fontes=(_Udev, _Bluez)):
        self.fontes, self.falhas = [], []
        for cls in fontes:
            try:
                self.fontes.append(cls())
            except Exception as e:  # noqa: BLE001 - falta de binário, permissão, o que for
                self.falhas.append(f"{cls.nome} ({e})")
        self.sel = selectors.DefaultSelector()
        for f in self.fontes:
            self.sel.register(f.fileno(), selectors.EVENT_READ, f)

    @property
    def sources(self):
        return [f.nome for f in self.fontes]

    def wait(self, timeout):
        """True se um evento **que interessa** chegou; False se o tempo acabou.

        Evento sem interesse não encerra a espera: ele é drenado e o que resta do
        timeout continua valendo. Sem isso, as duas linhas de banner que o
        `gdbus monitor` imprime ao subir já faziam o primeiro `wait` voltar na
        hora, e qualquer sinal falante do BlueZ durante áudio viraria releitura
        de hardware — tempestade de ioctl em vez de tempo real.
        """
        fim = time.monotonic() + timeout
        while True:
            restante = fim - time.monotonic()
            if restante <= 0:
                return False
            prontos = self.sel.select(restante)
            self._enterrar_mortos()
            if not prontos:
                return False
            # drena TODAS as fontes prontas: `any()` curto-circuitaria e
            # deixaria dado sem consumir, o que traria o select de volta na hora
            if any([chave.data.drain() for chave, _ in prontos]):
                return True

    def _enterrar_mortos(self):
        """Fonte que morreu para de ser esperada; senão o select volta sempre
        pronto no fd fechado e o loop vira busy-wait."""
        for f in list(self.fontes):
            if hasattr(f, "vivo") and not f.vivo():
                self.sel.unregister(f.fileno())
                self.fontes.remove(f)
                self.falhas.append(f"{f.nome} (morreu)")

    def close(self):
        for f in self.fontes:
            self.sel.unregister(f.fileno())
            f.close()
        self.sel.close()
        self.fontes = []
