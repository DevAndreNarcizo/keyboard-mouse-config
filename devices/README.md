# devices — um diretório por modelo

Todo o conhecimento de um periférico mora em `devices/<fabricante>_<modelo>/`:
os IDs USB, como achar a interface certa, como ler a bateria, o que ele sabe
controlar, o que ele **não** sabe, e o protocolo em Markdown ao lado.

Para adicionar o seu: copie o diretório do modelo mais parecido e edite. Não há
lista para registrar em lugar nenhum — a descoberta varre esta pasta.

## O contrato

```python
NAME = "Attack Shark K86"        # nome para humano
KIND = "keyboard"                # keyboard | mouse
IDS  = ("00003151:00004011",)    # HID_ID como aparece no uevent do hidraw
CAPS = ("battery",)              # o que este modelo faz DE VERDADE
WONT = {"light": "por que não, em uma frase"}   # opcional

def find() -> "/dev/hidrawN" | None
def battery(path, wait=0) -> Reading(pct, charging, raw) | None
```

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
| `delux_m900pro` | Delux M900Pro | mouse | bateria |
| `freewolf_f75` | FreeWolf F75 | teclado | bateria, luz, cor, remap, sono |
| `ajazz_aj139` | AJAZZ AJ139 | mouse | bateria |

Os dois últimos saíram da mesa em 2026-08-07 e não têm como ser testados ao
vivo aqui — o que dá para verificar sem eles está no `selftest`, em asserts de
bytes de pacote e de parser.
