# Attack Shark K86 — o que se sabe do protocolo

Dongle ROYUAN `3151:4011` (2.4G) / `3151:4015` (cabo). Família yc3123 no
[sharkfin](https://github.com/dniminenn/sharkfin), `device 2730`, com tela de
240x135 — é dela que sai o número em que se pode confiar durante a carga.

**Sem CLI própria, de propósito.** O canal de config (`0xFFFF` usage 2, feature
64B) só responde por cabo, e por cabo o sharkfin já faz luz, cor por tecla,
remap, macro e sleep — inclusive no browser, em `app.getsharkfin.com`. Escrever
um `k86ctl` só reescreveria o sharkfin para funcionar em menos casos. É por isso
que o módulo declara tudo isso em `WONT` em vez de em `CAPS`.

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

## Risco conhecido do `probe` do teclado

Escrever no canal vendor do F75 reiniciava o timer de sono dele — e economizar
bateria é justamente o objetivo. Não está provado que o `0xF7` não faça o mesmo
no K86; o indício a favor é que a resposta volta idêntica e instantânea mesmo
com esperas de 1 s, sugerindo que quem responde é o dongle sozinho, sem tocar o
rádio. **Se a bateria do teclado passar a cair rápido demais, o primeiro
suspeito é este cron** — tirar e voltar a escutar passivo.
