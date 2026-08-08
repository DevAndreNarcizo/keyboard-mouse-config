# battlog

Histórico de bateria dos periféricos em SQLite. Python 3 puro (stdlib), um arquivo.

Hardware atual (2026-08-07): teclado **Attack Shark K86** (dongle ROYUAN
`3151:4011`) e mouse **Delux M900Pro** (receptor 8K `1d57:fa65`).

```bash
./battlog.py probe        # grava uma rodada de bytes crus (é o que o cron roda)
./battlog.py raw          # quais bytes variaram e como
./battlog.py show         # timeline de bateria (só depois de haver parser)
./battlog.py selftest     # checa análise, poda e sparkline
```

Instalação da regra udev:

```bash
sudo install -m644 ../udev/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

Cron (a cada 10 min, em `crontab -l`):

```
*/10 * * * * .../battlog.py probe --wait 90 >.../last-run.log 2>&1
```

## Bateria do teclado: resolvida (2026-08-08)

**Byte 1 do frame de status do dongle.** O opcode mandado não importa: o dongle
do K86 responde **o mesmo frame a qualquer comando** — `00 PP 00 00 01 01 01 ck`
— e nunca repassa nada pelo rádio. Foi confirmado duas vezes de forma
independente: pela varredura própria dos opcodes `0x80-0xFF` e pelo *data bundle*
do sharkfin, onde os 17 opcodes conhecidos devolvem byte a byte a mesma coisa e o
`identify` fica sem resposta. As duas ferramentas mediram `33` no mesmo momento,
depois de cair de `34`.

Esse beco sem saída é, ao mesmo tempo, as duas respostas: **é por isso que não
existe config por 2.4G** (o dongle não é túnel) **e é o "outro canal" que o
software do fabricante usa pra ler bateria** (o frame é do dongle, não do
teclado). Não adianta patchar o sharkfin: o código dele manda os bytes certos, o
firmware do dongle é que não repassa.

Plugar o cabo resolveu o resto do frame de uma vez: o byte 1 vinha caindo
`34 33 33 32 32` e **pulou pra 42** no instante em que o USB entrou, enquanto o
byte 3 virava `0 → 1` e o byte 5 fazia o inverso. Então `[1]` = percentual,
**`[3]` = flag de carregando** (o `[5]` é redundante), `[7]` = checksum.

**O dongle continua reportando com o teclado no cabo.** (Eu tinha previsto o
contrário — que o log ficaria com buracos durante sessões de cabo. Errado: os
dois canais ficam vivos ao mesmo tempo, e é justamente assim que dá pra ver a
carga subindo.)

## Bateria do mouse: byte 4, provisório

O receptor **só fala com o mouse em uso** — 70 s parado não dão nada; em uso sai
`03 50 41 01 55` no report `0x03`. O `raw` apontou o `byte[4]` descendo
`85 84 84 84`, enquanto o `0x50` (80) e o `0x41` (65) ficaram parados.

Está marcado como **provisório** de propósito: é um decremento só, consistente
mas com bem menos evidência que o do teclado (que teve o salto de recarga como
prova). O `raw` continua gravando o frame inteiro, então se esse byte se revelar
outra coisa — contador, qualidade de link — dá pra trocar o offset sem ter
perdido histórico nenhum.

O que já foi eliminado por teste, para não refazer:

- `/sys/class/power_supply` e `upower` não veem nenhum dos dois.
- Nenhum descritor HID declara usage de bateria.
- Teclado: o report vendor `0x05` (`/dev/hidraw7`) ficou mudo por ~20 min;
  `GET_REPORT` nele devolve zeros.
- Mouse: `GET_REPORT` no vendor `0x04` dá `EPIPE`.
- **Cor/RGB por 2.4G: impossível, e não é limitação de software.** O dongle
  responde todo opcode com o próprio frame de status e não repassa nada pelo
  rádio, então o teclado nunca recebe o comando (o `identify` do sharkfin fica
  sem resposta). Patchar o sharkfin não cria um transporte que não existe no
  firmware. Por cabo ele já faz tudo — usar o sharkfin, não reescrever.

**Como distinguir os dois canais em um teste:** por cabo o teclado enumera como
`3151:4015` ("ROYUAN Gaming Keyboard"), e a resposta **ecoa o opcode no byte 0** —
`0x8F` devolve `8f 90 04 00 …` (board id `1168`). Pelo dongle (`3151:4011`) a
resposta **nunca ecoa**: é sempre o mesmo frame começando em `00`. Se o byte 0
não for igual ao opcode que você mandou, você está falando com o dongle, não com
o teclado. A regra udev do projeto casa pelo VID `3151` sem prender PID, então os
dois modos já saem com permissão.

## Como o `probe` acha um byte de bateria

Ele grava os bytes **crus**, sem interpretar, e `raw` marca como `CANDIDATO a
bateria` todo byte que se mexeu, ficou em 1..100 e quase nunca subiu (descarga é
monotônica, tirando os saltos de recarga). Foi assim que o byte 1 do teclado
apareceu sozinho no meio do frame. Confirmado o byte, é preencher `PARSERS`
(`{"teclado": 1}`) e o `show` desenha a timeline como no F75.

É esse o caminho que falta pro mouse: deixar acumular e olhar o `raw`.

## Risco conhecido do `probe` do teclado

Escrever no canal vendor do F75 reiniciava o timer de sono dele — e economizar
bateria é justamente o objetivo. Não está provado que o `0xF7` não faça o mesmo
no K86; o indício a favor é que a resposta volta idêntica e instantânea mesmo
com esperas de 1 s, sugerindo que quem responde é o dongle sozinho, sem tocar o
rádio. **Se a bateria do teclado passar a cair rápido demais, o primeiro
suspeito é este cron** — tirar e voltar a escutar passivo.

## Dados

`battlog.db`: `raw(ts, device, hex)` com os bytes crus e `battery(ts, device,
pct, charging)` para quando houver parser. Poda de **90 dias** roda dentro do
próprio `probe` (`--keep` muda o prazo); não há segunda rotina para agendar.

`battlog-f75.py` é a versão anterior, do FreeWolf F75 + AJAZZ AJ139, com os
parsers de bateria dos dois. Continua funcionando se aquele hardware voltar.
