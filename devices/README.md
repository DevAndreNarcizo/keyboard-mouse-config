# devices — dois tipos de módulo

A descoberta varre esta pasta e não conhece ninguém pelo nome. O que ela acha é
de um de dois tipos:

**Módulo de modelo** (`delux_m800pro`, `attackshark_k86`, …). Todo o conhecimento
de um periférico num diretório: os IDs, como achar a interface certa, como ler a
bateria, o que ele sabe controlar, o que ele **não** sabe, e o protocolo em
Markdown ao lado. Declara `IDS` + `find()`, e representa **um** aparelho.

**Módulo de fonte** (`bluez_any`, `power_supply_any`). Não sabe modelo nenhum:
sabe um barramento, e devolve **quantos aparelhos achar**. Declara `SOURCE = True`
+ `discover()`. É o que faz um teclado sem fio novo aparecer sozinho.

**Antes de escrever um diretório de modelo, ligue o aparelho e rode
`kmctl devices`.** Se uma fonte genérica já o vê, não escreva nada — o diretório
só se justifica quando nenhuma vê (bateria por opcode de fabricante, como o
M800 PRO e o K86, que não aparecem no UPower nem no `power_supply`) ou quando há
algo a declarar que o barramento não sabe: um `WONT`, ou caps de controle.

Quando as duas coisas veem o mesmo aparelho, o módulo de modelo ganha e o achado
genérico é suprimido — a dedução é por `handle`, o que funciona no Bluetooth
porque os dois lados devolvem o mesmo object path.

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

Um módulo de **fonte** troca `KIND`/`IDS`/`find()` por:

```python
SOURCE = True
def discover() -> [(ident, nome, kind, handle), …]   # quantos achar
def battery(handle, wait=0) -> Reading | None
```

O `ident` é a chave estável que vai para o banco e para o cache do painel, e
precisa ser único entre fontes — daí os prefixos (`bt_`, `ps_`).

`battery` é obrigatório nos dois; o resto é opcional e só existe se estiver em
`CAPS`.
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

O F75 e o AJ139 saíram da mesa em 2026-08-07 e não têm como ser testados ao
vivo aqui — o que dá para verificar sem eles está no `selftest`, em asserts de
bytes de pacote e de parser. Do M800 PRO, `battery` e `rgb` foram executados
contra o hardware; `sleep` e `remap` estão no mesmo regime de assert.

## Dois transportes

- **HID** (`find_iface`): quatro dos modelos. `IDS` são `HID_ID` como aparecem
  no uevent do hidraw. O trabalho de decodificar o frame é nosso, e é onde mora
  a engenharia reversa.
- **Bluetooth** (`bluez_any`): o BlueZ já publica a bateria normalizada em
  `org.bluez.Battery1`, então **não há diretório de modelo nenhum** deste lado —
  a fonte lista o que está conectado e pronto. Não há frame, e `Reading.raw` fica
  `b""`.

Houve um `devices/jbl_wave_buds_2/` por algumas horas em 2026-08-24, casando por
`Modalias`. **Foi removido**, e a lição vale mais que ele: uma fonte genérica não
precisa *reconhecer* o aparelho, só listá-lo. O diretório lia o mesmo fone pelo
mesmo caminho que o `bluez_any`, e manter os dois obrigou a inventar dedução em
`present()` só para o fone não aparecer duas vezes. O nome ficou até melhor sem
ele: vem do `Alias` do BlueZ, que acompanha renomeação, em vez de fixado em código.

Se algum dia um aparelho Bluetooth merecer diretório — por ter caps de controle —,
é o `Modalias` sem o `d` de release que serve como identificador, porque o `d`
muda com firmware.

Falar D-Bus em stdlib puro não é razoável, então o lado Bluetooth chama o
`busctl` — que vem com o systemd, não é pacote Python. Sem ele, ou com o
bluetoothd parado, a fonte devolve lista vazia e o resto do repo não se abala.

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
