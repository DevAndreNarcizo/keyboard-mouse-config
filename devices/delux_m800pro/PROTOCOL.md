# Delux M800 PRO — o que se sabe do protocolo

Receptor 2.4G `248a:5b2f`, modo cabo `248a:5b2e`. O dongle enumera com strings
do OEM — `iManufacturer` **XCTECH**, `iProduct` **Wireless-Receiver**, e o
`248a` é da TeLink Semiconductor, não da Delux. **Não dá para achar esse mouse
procurando "Delux" em `lsusb`**; procure o VID:PID.

Fonte dos opcodes: [xb-bx/m800-pro-driver](https://github.com/xb-bx/m800-pro-driver)
(GPL, libusb). O que esse driver faz com dois `libusb_control_transfer` é
exatamente `HIDIOCSFEATURE`/`HIDIOCGFEATURE` no hidraw da interface 1 — por isso
aqui não há libusb nem desanexar driver do kernel, e o módulo continua stdlib puro:

| driver de referência | equivalente no hidraw |
|---|---|
| `bmRequestType=0x21 bRequest=0x09 wValue=0x30c wIndex=1`, 33 B | `HIDIOCSFEATURE(33)` |
| `bmRequestType=0xa1 bRequest=0x01 wValue=0x30c wIndex=1`, 33 B | `HIDIOCGFEATURE(33)` |

`wValue 0x30c` = tipo 3 (Feature) `<< 8` \| report id `0x0c`. `wIndex 1` = a
interface 1.

## É request/response, não anúncio — e isso foi medido

O M900Pro deste repo se anuncia sozinho e o `battery()` dele **escuta**. Aqui
não: o canal fica **mudo** até alguém perguntar.

- 60 s escutando o canal vendor com o mouse em uso pesado: **0 frames**, contra
  **12482** frames de movimento no canal do mouse na mesma janela. Não é "mouse
  parado".
- Outros 5 min escutando, incluindo desligar/ligar o mouse no botão: **0 frames**.
- `GET_FEATURE` no `0x0c` **sem ter escrito antes** devolve 33 bytes de zero.
  Foi o que fez parecer, no primeiro teste, que era o mesmo "dongle mudo" do K86.
  Não é: é só que ninguém tinha perguntado nada.
- Todo outro report (`0x05`, `0x07`, e o `0x0c` com tamanho != 33) dá `EPIPE`.

## Cuidado: o canal writable é a interface de **teclado** do dongle

`find_iface(IDS, writable=True)` devolve a interface 1, e ela é a certa — é a
que tem a vendor page `0xFF00` com item Feature. Mas o descritor dela declara
**também o teclado do dongle** (report `0x01`, array de 6 bytes). Ou seja: um
`battery()` copiado do M900Pro, que faz `os.read(fd)` no path que o `find()`
devolveu, **gravaria o que o dono digita**.

Por isso este módulo nunca lê o stream de input: só `ioctl`. É o risco que o
`devices/README.md` avisa, e neste modelo ele é real, não hipotético.

## O frame de status

Pergunta (33 B, o primeiro é o report id):

```
0c 01 20 00 SS 00 00 00 …
│  │  │     └─ seq
│  │  └─ opcode 0x20 = status
│  └─ 0x01
└─ report id 0x0c
```

Resposta, medida neste hardware:

```
0c 01 20 00 01 01 10 00 4d 38 30 32 25 01 00 70 04 ff 3a 00 ff 01 00 00 87 5c 08 3f ff f4 6f 2d 39
      ^^          ^^ ^^ └──"M802"──┘                    ^^ ^^
      opcode      │  len=16                        bateria  carga
                  0x01
```

- **byte 18 = percentual.** Não é provisório como o do M900Pro: veio de uma
  implementação independente que já usava isso, e bate com o que o mouse mostra.
- **byte 19 = flag de carga** (1 = carregando).
- **bytes 8..11 = ASCII `M802`** — o mouse assina o frame. É um handle de
  identidade melhor que a string USB, que é do OEM.
- **byte 2 ecoa o opcode.** Mesmo teste que o K86 obrigou a aprender: se o byte
  não voltar igual ao que você mandou, você está lendo buffer velho, não resposta.
- byte 6 = tamanho do payload; o payload começa no byte 7. Vale para todos os
  opcodes, não só o status.
- bytes 24..32 ficaram constantes em todas as leituras — parecem assinatura do
  aparelho. O `raw` guarda o frame inteiro, então dá para reanalisar depois.

O `parse()` exige as três coisas (opcode ecoado + `M802` + 1..100) antes de
acreditar no byte 18, porque num canal de request/response uma resposta de outro
opcode tem exatamente o mesmo tamanho e passaria por bateria.

## O seq alterna, e o retry não é paranoia

O dispositivo ignora pergunta cujo `seq` não é o que ele espera, e o esperado
**alterna entre 1 e 2** — em cinco leituras seguidas o eco veio `2,1,2,1,2`. Daí
o `_handshake()` varrer em vez de assumir 1. Converge em 2 tentativas; o limite
de 8 é folga.

Comando de escrita usa o **seq seguinte** ao que foi aceito, como faz o driver
de referência.

## Pegadinha do `kmctl raw` neste modelo

O `kmctl raw` marca o **byte 4 como "CANDIDATO a bateria"**. Não é: é o `seq`.
O heurístico dele ("mexeu, ficou em 1..100, quase nunca subiu") foi desenhado
para canal de **anúncio**, onde não existe número de sequência. Num canal de
request/response o seq passa no teste por acidente.

O byte de bateria real (18) aparece como *não* tendo mudado enquanto a carga não
cair — o que é o correto, e o oposto do sinal que se procura num modelo novo.

## O LED só acende na troca de DPI — e isso quase virou um falso negativo

A primeira escrita de `rgb` pareceu não funcionar: comando aceito, ACK no byte 3,
**nada visível**. A conclusão errada estava pronta e era plausível — "o dongle
aceita e não repassa pelo rádio", exatamente o que acontece no K86 deste repo, e
a bateria continuaria funcionando porque é consulta *ao dongle*, que já tem o
número cacheado.

Era falso. **Neste mouse o LED de estágio de DPI fica apagado e só pisca quando
se troca de estágio.** Apertando o botão de DPI, piscou vermelho. A escrita tinha
funcionado desde a primeira vez.

Vale registrar o contraste, para ninguém generalizar a lição do K86: **este
dongle repassa config pelo rádio.** O K86 não repassa; este repassa. São
protocolos diferentes e a conclusão de um não vale para o outro.

Teste certo para qualquer opcode de escrita aqui: **mande e aperte o botão de
DPI**, não olhe o mouse parado.

## Byte 3 da resposta é ACK

A pergunta manda byte 3 = `0x00`; a resposta volta com **byte 3 = `0x01`**, e o
byte 2 ecoa o opcode:

```
mandei: 0c 01 06 00 03 01 18 ff 00 00 …
voltou: 0c 01 06 01 03 01 00 00 00 00 …
              ^^ ^^    ^^
         opcode │      seq ecoado
                ACK
```

Vale para os opcodes de escrita (`0x06`, `0x0b` medidos). Ou seja: dá para saber
se um comando foi **reconhecido** sem depender de olhar o efeito. Isso não é a
mesma coisa que o comando ter surtido efeito no mouse — ver a seção seguinte.

## Modo cabo: `5b2e` continua sem teste, e não é por falta de tentar

`IDS` traz `248a:5b2e` porque o driver de referência declara esse PID como modo
cabo. **Aqui ele nunca apareceu.** Com o cabo numa porta USB da máquina:

- energia flui — a flag de carga liga e o percentual sobe;
- o kernel **não enumera nada**: zero evento USB em 15 min, `lsusb` inalterado.

Não se sabe qual dos três é: cabo só de carga, header do painel frontal ligado
só na energia, ou firmware que não entra em modo cabo com o link 2.4G ativo.
Teste que separa isso: mover o **dongle** para a mesma porta. Se o mouse
continuar funcionando, a porta tem dados, e a suspeita cai no cabo ou no firmware.

Enquanto isso o `5b2e` fica em `IDS` — declarado pelo driver de referência, sem
confirmação local. Não é conhecimento negativo; é conhecimento ausente.

## Os outros opcodes

Todos com a mesma moldura (`0c 01 OP 00 SS 01 LEN` + payload no byte 7). Os que
este módulo expõe estão em `CAPS`; os demais estão aqui para não se perderem.

| opcode | o que faz | payload | exposto? |
|---|---|---|---|
| `0x20` | status/bateria | — | `battery` |
| `0x06` | cor dos 5 estágios de DPI | 5 × RGB nos bytes 7..21, na ordem dos estágios | `rgb` |
| `0x0b` | minutos até dormir (3..10) | byte 7 | `sleep` |
| `0x04` | função de um botão | byte 7 = botão, 8..10 = função | `remap` |
| `0x05` | os 5 valores de DPI | bitmask + 5 × uint16 LE, `dpi/50 - 1` | não |
| `0x07` | polling rate | byte 7: 8=125Hz 4=250 2=500 1=1000 | não |
| `0x09` | LOD (1 ou 2) | byte 7 | não |
| `0x0a` | debounce (0..30 ms) | byte 7 | não |
| `0x0c` | motion wakeup on/off | byte 7 | não |

Os quatro últimos não estão em `CAPS` porque o `kmctl` não tem subcomando para
eles — declarar cap que a CLI não alcança seria código morto. Quem precisar tem
a moldura e o opcode aqui.

**Os templates de escrita são copiados byte a byte do driver de referência, e só
o `seq` e o campo documentado são sobrescritos.** O `len` do `0x06` diz 24 bytes
de payload e só 15 são cor: os 9 restantes não estão explicados, então são
preservados em vez de zerados.

### Escrever cor é sempre escrever as cinco

O `0x06` manda os cinco estágios num pacote e **não há opcode que leia as cores
atuais**. Logo não existe "pintar só o estágio 3": os outros quatro vão junto,
com o valor que estiver no template. O `kmctl rgb X --only 3` faz isso e diz na
mensagem que faz — o nome `--only` vem do contrato do repo e prometia mais do que
o protocolo entrega. Para controle real dos cinco, a forma é
`kmctl rgb c1,c2,c3,c4,c5`.

Consequência prática: **não dá para "salvar e restaurar" a paleta do dono.** Se
você for testar cor num mouse de outra pessoa, o que estava lá se perde.

## O que foi verificado contra este hardware, e o que não

- **`battery` foi executado aqui** e devolve o percentual certo, estável em
  leituras repetidas, descendo com o tempo (59 → 58).
- **`rgb` foi executado aqui** e funciona: cor única nos cinco estágios e a
  forma de cinco cores, uma por estágio. O efeito só aparece apertando o botão
  de DPI.
- **`sleep` e `remap` não foram executados contra o mouse.** Os pacotes estão
  travados por assert no `kmctl selftest`, byte a byte, contra os literais do
  driver de referência — mesmo padrão que este repo usa para o F75 fora da mesa.
  Use `--dry-run` primeiro. O ACK do byte 3 diz se foram *reconhecidos*, o que
  já é mais do que se tinha para o F75.
- **A flag de carga (byte 19) foi confirmada.** Cabo plugado: virou 1 e o
  percentual subiu (58 → 59 → 64). **Só o byte 19 e o percentual se moveram** —
  nenhum outro byte do frame mudou, o que é o que faz a leitura ser limpa em vez
  de coincidência.
