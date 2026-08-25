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

## No cabo de carga, a bateria é ilegível — e isso é definitivo

Medido em 2026-08-25, com o mouse a noite inteira no cabo:

- **o dongle fica mudo.** 0 frames em 15 s, duas medições separadas. O driver de
  referência do X11 já dizia: no modo cabo o mouse para de falar pelo rádio;
- **as interfaces do cabo não têm canal de bateria.** Com o cabo plugado aparece
  um segundo device USB (`1d57:fa61`, "Xenta USB Gaming Mouse") com **duas**
  interfaces, de 75 B e 73 B: só teclado/mouse básico e um Output de LED.
  **Nenhum report Feature, nenhuma página de fabricante.** Não há o que perguntar.

Ou seja: enquanto carrega por cabo, o número não existe em canal nenhum. Está em
`WONT` como `battery-no-cabo`. O módulo expõe `DICA` para o `kmctl battery` dizer
isso a quem estranhar o silêncio — mas **não** implementa `estado()` para este
caso, porque `estado()` é veredito e tiraria o mouse da lista; mouse calado há
dois minutos deve manter o último valor, e é a janela do `LEITURA_VELHA` que
decide.

### Cuidado: o mesmo PID já apareceu com configurações USB diferentes

Em 2026-08-24 o `fa61` tinha **quatro** interfaces, e uma delas (236 B) carregava
o canal de status. Em 2026-08-25 o `fa61` apareceu com **duas**, sem canal
nenhum. Mesmo VID:PID, configuração diferente. Por isso o módulo escolhe a
interface pela **assinatura do descritor**, nunca pelo PID — e por isso não se
pode inferir "está no cabo" da presença de um PID.

## O frame de anúncio NÃO é a bateria — e o que é

**Correção de 2026-08-25.** Este documento afirmava que o `param2` do frame de
anúncio era o percentual. **Está errado**, e o teste que derrubou foi o óbvio: o
mouse passou a noite inteira no carregador, foi desplugado, o dongle voltou a
falar — e o valor continuou `0x0a`. O histórico do `kmctl show` mostra
`min 10 / max 10`: o byte **nunca se moveu**, em nenhuma leitura, em dois dias.

Um mouse carregado a noite inteira não está com 10%. Ou `0x0a` não é bateria, ou
é uma escala 0–10 (e aí 10 = cheio, o que encaixaria com tudo). Não foi decidido
por medição, e por isso o percentual saiu do módulo.

### O canal certo: o protocolo do HUB de navegador

A Attack Shark publica um configurador **em navegador**, sem instalação, que
funciona em Linux e cobre o X6: <https://controlhub.top/AttackShark/>. Ele fala
WebHID, então o protocolo está no JavaScript dele — que é uma fonte melhor que
qualquer binário de Windows. Extraído de `assets/index-BLQzAg-a.js`:

**Enquadramento.** Report **`0x08`**, pacote de **16 bytes**:

```
[0]  comando
[4]  sequência   (0 para mouse; 128 para teclado — a função `fr()` do HUB)
[15] checksum
```

O checksum é escolhido para que **a soma de (report ID + os 16 bytes) dê `0x55`**.
No JS: `at(t) = 85 - (soma(t[0..14]) & 255)`, e depois `t[15] = at(t) - 8`, onde
`8` é justamente o report ID. O verificador do outro lado (`hw()`) confere que a
soma dá 85.

**Comandos** (enum `Ne` do HUB), os relevantes:

| nº | nome |
|---|---|
| 3 | `DeviceOnLine` |
| **4** | **`BatteryLevel`** |
| 6 | `GetPairState` |
| 14 | `GetCurrentConfig` |

**Resposta da bateria.** Chega como **input report**, não por `GET_FEATURE` — o
HUB a lê no `oninputreport`. O `Le` do JS é o `DataView` do WebHID, que **exclui**
o report ID; no `/dev/hidraw*` tudo desloca um byte:

| `Le[i]` do HUB | byte no hidraw | significado |
|---|---|---|
| `Le[0]` | `pkt[1]` | eco do comando (`4`) |
| `Le[5]` | `pkt[6]` | **percentual** |
| `Le[6]` | `pkt[7]` | **carregando** (`==1`) |
| `Le[7..8]` | `pkt[8..9]` | **tensão em mV**, big-endian |
| `Le[9]` | `pkt[10]` | se `==1`, o percentual está em `Le[10]` (`pkt[11]`) |

O estado inicial do HUB é `battery:{level:20, charging:false, voltage:3728}` —
confirmando que `level` é percentual 0–100 e `voltage` é mV, exatamente como o
fone HyperX faz.

**Isso dá também a flag de carga**, que o frame de anúncio não dava de forma
confiável — e é o que permite mostrar o `⚡` em vez de fazer o aparelho sumir.

### Estado do teste

`SET_FEATURE` no report `0x08` com o pacote acima **foi aceito uma vez**
(`set ok`). O `GET_FEATURE` seguinte deu `ETIMEDOUT`, coerente com a resposta
chegar por input report. As tentativas seguintes deram `EPIPE` — e a explicação
é a mesma limitação já medida: **o cabo tinha sido replugado**, e com o mouse no
cabo o dongle não repassa nada pelo rádio. **Falta rodar o teste com o mouse fora
do cabo.**

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
