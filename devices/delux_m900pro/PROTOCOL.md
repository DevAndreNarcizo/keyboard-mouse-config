# Delux M900Pro — o que se sabe do protocolo

Receptor 8K `1d57:fa65`. Só escuta: `GET_REPORT` no vendor `0x04` dá `EPIPE`,
então o único caminho é esperar o receptor se anunciar — e ele só fala com o
mouse em uso.

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
