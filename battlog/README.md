# battlog

Histórico de bateria dos periféricos em SQLite. Python 3 puro (stdlib), um arquivo.

Hardware atual (2026-08-07): teclado **Attack Shark K86** (dongle ROYUAN
`3151:4011`) e mouse **Delux M900Pro** (receptor 8K `1d57:fa65`).

```bash
./battlog.py probe        # grava uma rodada de bytes crus (é o que o cron roda)
./battlog.py raw          # quais bytes variaram e como
./battlog.py show         # timeline de bateria (só depois de haver parser)
./battlog.py status       # último valor de cada um, e atualiza o cache do painel
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

## Widget no painel do GNOME

`../gnome/battlog@victor/` — extensão de dois arquivos que mostra os dois
percentuais na barra de cima, ao lado do Astra Monitor.

Ela **não fala com hardware**: o `probe` reescreve `~/.cache/battlog-status`
(`ts`, `teclado`, `mouse`, um por linha, troca atômica) no fim de cada rodada, e
a extensão relê esse arquivo a cada 2 min. Toda a parte difícil — hidraw,
parser, histórico — continua no `battlog.py`, e o painel é só um `St.Label`.

Três decisões que valem o comentário:

- **O valor vem da última linha do banco, não da rodada atual.** O receptor do
  mouse só fala com o mouse em uso, então metade das rodadas não tem mouse — e
  mouse parado não gastou bateria. Repetir o último número é mais verdadeiro que
  apagá-lo.
- **`ts` mais velho que 30 min vira `—`.** É o cron que morreu, e um número
  velho no painel engana justamente por parecer atual.
- **Sem flag de carregando.** A do teclado (byte 3) pisca 0/1 sem cabo nenhum;
  no painel ela mentiria a cada duas leituras.

O Astra Monitor não serve de casa pra isso: a versão 42 não tem sensor por
comando (o `sensors-source` dele só lê `hwmon`), então seria preciso um driver
de kernel falso só para expor dois inteiros.

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

O que sustenta o byte 1 é a **descarga**: ele cai devagar e de forma monótona por
dias (88 → 30 numa semana) e, quando o cabo sai depois de uma carga, ele pula para
o valor que a tela do próprio teclado mostra (medido em 23/08: 30 → 100 em menos de
2 min). Só o resto do frame:

| byte | o que é |
|---|---|
| `[1]` | percentual — **com a ressalva de carga, abaixo** |
| `[3]` | flutua 0/1 sem cabo nenhum. **Não é flag de carregando**, não usar |
| `[5]` | constante `1` nos frames modernos. Bate com o inverso de `[3]` em só 464 de 1389 amostras — coincidência, não relação |
| `[7]` | `0` nos frames modernos. **Não é checksum** (a regra `0xFF - soma` vale para o que se *manda*, não para o que volta) |

Nos três primeiros dias do log (08–10/08) aparece um segundo formato, com `[7] =
0x7a` e às vezes `[0] = 1`. São 112 frames, todos daquela época, e nada depois de
10/08. Não foi investigado.

## O ponto cego: teclado no carregador

**Enquanto o teclado está no cabo, o percentual do dongle não vale nada.** Medido
na noite de 22→23/08, com o cabo num carregador de tomada (o PC nunca viu o
`3151:4015`, então o teclado ficou no 2.4G a noite inteira):

```
04:00  30%          antes do cabo
04:10  78%          cabo entrou
04:20  81%  chg=1
  ...  81% cravado, 33 leituras idênticas em 5h30
10:00  30%  chg=0   ainda no carregador, carga já completa
10:29  100%         2 min depois de tirar o cabo
```

Carga real não fica parada em 81 por 5h30 nem volta ao valor exato de antes. O que
explica isso está no protocolo do sharkfin: **"an unsupported command returns the
previous reply, not an error"** — o `0xF7` que o `probe` manda não é opcode válido,
então o que se lê é o *buffer de resposta* do dongle, não uma medição. Enquanto o
teclado está na tomada ele para de alimentar esse buffer, e o dongle republica o
que tinha. Sai o cabo, o teclado volta a reportar, o número se corrige sozinho.

**Não dá para detectar esse estado pelo frame.** O `[3]` é ruído; e um tombo grande
para baixo é ambíguo — pode ser o buffer voltando ao valor velho (22/08, 81 → 30
mentindo) ou o teclado acordando e reportando a verdade depois de uma noite dormindo
(18/08, 60 → 46, legítimo). A série sozinha não separa os dois casos, então o painel
**não** tenta adivinhar: mostra o que o dongle diz.

Na prática: **carregando, olhe a tela do teclado** — ela é medição do firmware dele.
O painel volta a valer sozinho poucos minutos depois de o cabo sair.

Histórico de todos os saltos para cima em 90 dias: `09/08 42→100`, `13/08 20→83` e
`14/08 71→100` grudaram (cargas reais); `14/08 71→99` e `23/08 30→81` voltaram
(sessões de carga em andamento). O canal funciona — ele só não é confiável *durante*
a carga.

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
pct, charging)` para quando houver parser. Frames com percentual **0** não entram
no `battery`: é o frame desalinhado que sai logo depois de o dongle enumerar, e
virava um 0% falso no gráfico (6 linhas assim foram apagadas em 23/08; o `raw`
guarda todas, dá pra rederivar). Poda de **90 dias** roda dentro do
próprio `probe` (`--keep` muda o prazo); não há segunda rotina para agendar.

`battlog-f75.py` é a versão anterior, do FreeWolf F75 + AJAZZ AJ139, com os
parsers de bateria dos dois. Continua funcionando se aquele hardware voltar.
