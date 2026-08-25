# Attack Shark X6 — bateria por anúncio

Medido em 2026-08-24 na máquina `calecos`, contra o hardware.

## A família, e por que ela importa

Este mouse não tem protocolo próprio: usa um **sistema de mensagens** comum a
vários fabricantes de mouse barato. Foi isso que resolveu o caso — sem ele, o
frame `03 10 40 02 0a` seria cinco bytes sem sentido.

Estrutura de 5 bytes, do
[attack-shark-x11-driver](https://github.com/HarukaYamamoto0/attack-shark-x11-driver)
(`docs/messages/README.md`):

| byte | campo |
|---|---|
| 0 | `0x03` — opcode de "Event Message", sempre |
| 1 | **ID do modelo** — fixo por aparelho |
| 2 | código do evento |
| 3 | param1 — significado depende do evento |
| 4 | param2 — idem |

O evento `0x40` chama-se *Device Connection Message*, e apesar do nome **é o de
bateria**: param2 é o percentual.

Com isso o frame daqui se lê inteiro, sem sobrar byte:

```
03 10 40 02 0a
^^ ^^ ^^ ^^ ^^
|  |  |  |  param2 = bateria = 10%
|  |  |  param1 = estado (ver abaixo)
|  |  evento 0x40 = bateria
|  ID do modelo: 0x10 = X6   (o X11 é 0x55)
opcode de Event Message
```

Os modelos que este repo conhece, lado a lado:

| modelo | frame | ID |
|---|---|---|
| Delux M900Pro | `03 50 41 01 PP` | `0x50` |
| Attack Shark X11 | `03 55 40 01 PP` | `0x55` |
| **Attack Shark X6** | `03 10 40 02 PP` | `0x10` |

O `0x10` **não era parte da bateria** — era o identificador do modelo. Ler o
frame como "byte 1 é o percentual" daria 16%, e teria sido plausível.

## Identificação, e as quatro interfaces

| | |
|---|---|
| VID:PID | **três**: `1d57:fa60`, `fa61`, `fa55` — ver abaixo |
| `HID_ID` | `0003:00001D57:0000FA61` |
| interface | a que declara **Report ID 3 sob a página Ordinal (`0x0A`)** |

**Procurar "Attack Shark" no `lsusb` não acha nada**, igual ao caso do Delux.

### O PID muda com o modo, e isso derruba o aparelho em silêncio

O X6 é tri-mode, e **troca de ID USB conforme o modo**. Visto aqui no mesmo
mouse, sem reinstalar nada:

| PID | como enumera | quando |
|---|---|---|
| `fa61` | "Xenta USB Gaming Mouse" / "Beken USB Gaming Mouse" | 2026-08-24 |
| `fa60` | "Xenta 2.4G Wireless Device" / "Beken 2.4G Wireless Device" | 2026-08-25 |
| `fa55` | — | não visto aqui; vem das regras udev do attack-shark-x11-driver |

O módulo declarava só o `fa61`, e no dia seguinte o mouse **sumiu do `kmctl`
sem erro nenhum** — o `find()` não achava e o aparelho simplesmente não existia.
É o mesmo modo de falha que o `find_iface` tinha com a página `0xFF13` do fone:
ausência silenciosa é pior que erro.

O frame também mudou de `03 10 40 02 0a` para `03 10 40 01 0a` — só o `param1`.
Como o parse confere apenas os bytes 0..2 e lê o byte 4, isso não quebrou nada,
e reforça que o `param1` é estado (e não bateria).

O receptor expõe **quatro** interfaces com o mesmo VID:PID e **nenhuma página de
fabricante** — o que quebra a regra que o resto do repo usa para desempatar. A
assinatura que separa a de status é literal do descritor:

```
05 0a 09 00 a1 01 85 03
Usage Page (Ordinal)  Usage 0  Collection Application  Report ID 3
```

Daí o parâmetro `contains=` no `find_iface`: escolher pelo traço do descritor
quando não há página vendor para escolher.

**O número de `/dev/hidrawN` não serve para nada** — ele mudou no meio desta
própria investigação, quando um `udevadm trigger` reenumerou os aparelhos. O
mouse saiu de `hidraw3` para `hidraw5`.

## O que não se sabe

- **param1.** Aqui vale `0x02`. A tabela do driver de referência diz
  `1 = Charging complete`, `2 = Fully charged`, `3 = Charging in progress` — e
  `2` ("carregado") ao lado de `10%` **não fecha**. Ou a tabela está incompleta
  (ela não tem um valor para "descarregando", que é o estado óbvio de um mouse
  sem fio em uso), ou o X6 usa outra numeração. Está em `WONT`, e o `Reading` vai
  com `charging=None`: o painel desenha sem o `⚡` em vez de inventar estado.
- **Se 10% é o número certo.** É o que o frame diz, e todo byte do frame está
  explicado — mesma classe de evidência que justificou o `delux_m900pro` e o
  `ajazz_aj139`. Mas **não foi cruzado com uma segunda fonte**: não há leitura no
  próprio mouse para comparar, e ele não foi posto no dock para ver o valor
  subir. Quem confirma ou desmente é o histórico: `kmctl show` ao longo dos
  próximos dias mostra se a curva desce como bateria desce.

## Cadência

O receptor emitiu 13 frames em 25 s e 6 em 12 s — algo em torno de 2 s, com o
mouse em uso. Parado ele cala, e por isso o `battery()` tem `wait`: com `wait=0`
o laço não roda nem uma vez e o aparelho fica invisível **sem erro nenhum**. É a
mesma armadilha já documentada no M900Pro.
