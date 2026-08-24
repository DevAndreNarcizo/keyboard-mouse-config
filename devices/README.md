# devices — um diretório por modelo

Todo o conhecimento de um periférico mora em `devices/<fabricante>_<modelo>/`:
os IDs USB, como achar a interface certa, como ler a bateria, o que ele sabe
controlar, o que ele **não** sabe, e o protocolo em Markdown ao lado.

Para adicionar o seu: copie o diretório do modelo mais parecido e edite. Não há
lista para registrar em lugar nenhum — a descoberta varre esta pasta.

## O contrato

```python
NAME = "Attack Shark K86"        # nome para humano
KIND = "keyboard"                # keyboard | mouse | headset
IDS  = ("00003151:00004011",)    # identificador; ver "dois transportes" abaixo
CAPS = ("battery",)              # o que este modelo faz DE VERDADE
WONT = {"light": "por que não, em uma frase"}   # opcional

def find() -> handle | None      # o que o battery() precisa para falar com ele
def battery(path, wait=0) -> Reading(pct, charging, raw) | None
```

O que o `find()` devolve é **opaco**: quem consome só o repassa ao `battery()`.
No lado HID é um `/dev/hidrawN`; no lado Bluetooth, um object path do BlueZ.
Não presuma que é um arquivo.

`battery` é obrigatório; o resto é opcional e só existe se estiver em `CAPS`.
As funções de controle recebem `path` e um `dry=False`, e devolvem
`(mensagem, [pacotes])` — o `dry` faz a operação montar os pacotes sem abrir o
dispositivo, que é o que permite testar sem ter o hardware:

```python
def light(path, mode, brightness, speed, direction, color, dry=False)
def rgb(path, color, only=None, brightness=5, speed=4, dry=False)
def off(path, dry=False)
def remap(path, key, to, layer="fn", dry=False)
def sleep(path, when, dry=False)
```

Três regras que valem a pena entender antes de escrever o seu:

- **`CAPS` é a interface.** Não existe classe base nem método que levanta
  `NotImplementedError`: o módulo declara o que faz e o `kmctl` só oferece isso.
  Um mouse que só reporta bateria é um arquivo de 30 linhas.
- **`WONT` guarda o conhecimento negativo.** Foi caro descobrir que o dongle do
  K86 não repassa comando nenhum pelo rádio; essa frase vira a mensagem de erro
  de `kmctl light`, em vez de virar uma falha feia e uma tarde perdida por quem
  vier depois. Uma cap não pode estar em `CAPS` e em `WONT` ao mesmo tempo — o
  selftest reclama.
- **`find()` quase sempre é uma linha.** `find_iface(IDS, writable=…,
  at_start=…)` cobre os quatro modelos daqui. O `writable=True` só serve a
  interface com item Feature (`0xB1`) ou Output (`0x91`) — **use quando o modelo
  precisar de escrita**: num teclado, uma das outras interfaces costuma carregar
  o NKRO, e escolher errado significa ler tudo o que o dono digita.

`Reading.charging` é `None` quando o modelo não tem flag de carga **ou quando a
flag existe mas mente** — foi o caso do K86, cujo byte 3 oscila 0/1 sem cabo
nenhum. Preferimos não dizer a dizer errado.

`Reading.raw` é o frame cru. Guarde-o mesmo depois de identificar o byte: é ele
que alimenta a tabela `raw` do battlog, e foi relendo frames antigos que dois
parsers foram corrigidos sem ter perdido histórico.

## Achar o byte de bateria de um modelo novo

O caminho já rodou duas vezes aqui e não precisa de engenharia reversa do
firmware:

1. Escreva o módulo com um `battery()` que devolva `Reading(1, None, frame)` —
   percentual fixo, só para o frame cru entrar no banco.
2. Deixe o cron rodar algumas horas.
3. `kmctl raw` marca como **`CANDIDATO a bateria`** todo byte que se mexeu,
   ficou em 1..100 e quase nunca subiu — descarga é monotônica, tirando os
   saltos de recarga. Foi assim que o byte 1 do K86 e o byte 4 do M900Pro
   apareceram sozinhos no meio do frame.
4. Troque o offset no `parse()` e pronto: o `show` desenha a timeline.

**O experimento que confirma um byte é tirar o cabo depois de uma carga, não
plugar.** Plugar produz um artefato — o número salta e pode voltar sozinho ao
valor de antes. Tirar faz o aparelho reportar de novo, e aí o valor bate com o
que o próprio aparelho mostra.

## Modelos aqui hoje

| id | modelo | tipo | caps |
|---|---|---|---|
| `attackshark_k86` | Attack Shark K86 | teclado | bateria |
| `delux_m800pro` | Delux M800 PRO | mouse | bateria, cor, remap, sono |
| `delux_m900pro` | Delux M900Pro | mouse | bateria |
| `freewolf_f75` | FreeWolf F75 | teclado | bateria, luz, cor, remap, sono |
| `ajazz_aj139` | AJAZZ AJ139 | mouse | bateria |
| `jbl_wave_buds_2` | JBL Wave Buds 2 | fone | bateria |

O F75 e o AJ139 saíram da mesa em 2026-08-07 e não têm como ser testados ao
vivo aqui — o que dá para verificar sem eles está no `selftest`, em asserts de
bytes de pacote e de parser. Do M800 PRO, `battery` e `rgb` foram executados
contra o hardware; `sleep` e `remap` estão no mesmo regime de assert.

## Dois transportes

- **HID** (`find_iface`): quatro dos modelos. `IDS` são `HID_ID` como aparecem
  no uevent do hidraw. O trabalho de decodificar o frame é nosso, e é onde mora
  a engenharia reversa.
- **Bluetooth** (`find_bluez`): o BlueZ já publica a bateria normalizada em
  `org.bluez.Battery1`, então `IDS` são pedaços de `Modalias`
  (`v0ECBp2100` de `bluetooth:v0ECBp2100d001F` — vendor e produto, sem o `d` de
  release, que muda com firmware). Não há frame, e `Reading.raw` fica `b""`.

A divisão é a mesma nos dois: **o pacote sabe o transporte, o diretório sabe
qual aparelho é.** Um segundo fone é um diretório de 20 linhas com um `Modalias`
diferente, porque não há conhecimento de modelo para guardar.

Falar D-Bus em stdlib puro não é razoável, então o lado Bluetooth chama o
`busctl` — que vem com o systemd, não é pacote Python. Sem ele, ou com o
bluetoothd parado, `find_bluez` devolve `None` e o resto do repo não se abala.

## Dois jeitos de ler bateria, e como saber qual é o seu

Os modelos daqui se dividem em dois, e confundir os dois custa uma tarde:

- **Quem se anuncia** (M900Pro, AJ139): o `battery()` abre o path e **escuta**.
  Mouse parado não produz frame — isso é "parado", não "quebrado".
- **Quem só responde** (K86, M800 PRO): o `battery()` **escreve e depois lê**,
  por `HIDIOCSFEATURE` + `HIDIOCGFEATURE`. Escutar não dá nada, nunca.

Para saber em qual grupo o seu está, capture o canal vendor **junto com o canal
de movimento/teclado**. Se o de movimento enche e o vendor fica em zero, é do
segundo grupo — foi assim que o M800 PRO se revelou (12482 frames contra 0).
Sem essa testemunha você não distingue canal mudo de aparelho parado.

**E um aviso que o M800 PRO tornou concreto:** ali o `writable=True` cai na
interface que também declara o **teclado** do dongle. É a interface certa para
`ioctl`, mas um `battery()` copiado de um modelo do primeiro grupo — que faz
`os.read()` no path — gravaria o que o dono digita. Se o seu modelo é do segundo
grupo, não leia o stream.
