# MAP — ajustes ativos (teclado Attack Shark K86 + mouse Delux M900Pro)

Estado vivo em 2026-08-07. O que cada camada tem de customizado e onde mora.
Histórico e justificativas: `~/Documents/notas/ubuntu/teclado-abnt2-para-75-pct.md`,
`docs/checkpoints-log.md`, `battery/README.md` e `devices/*/PROTOCOL.md`.

**Trocou o hardware em 2026-08-07.** Saíram o teclado FreeWolf F75 (`1a2c:8fff`) e o
mouse AJAZZ AJ139 (`a8a5:2255`); entraram o **Attack Shark K86** (dongle ROYUAN
`3151:4011`) e o **Delux M900Pro** (receptor 8K `1d57:fa65`). Os dois antigos continuam
suportados como `devices/freewolf_f75/` e `devices/ajazz_aj139/`.

## 1. XKB — variante `victor(quotefix)`

Herda `us(intl)` e sobrescreve 5 teclas. É o **group 1** (padrão, sem Super+Space);
`br` fica como group 2.

| Tecla | Base | Shift | AltGr | AltGr+Shift | O que é |
|---|---|---|---|---|---|
| `'` (AC11) | `dead_acute` | `dead_circumflex` | `'` | `"` | acento agudo / circunflexo; +espaço vira `'` / `"` |
| `1` (AE01) | `1` | `!` | `¹` | `¡` | fix da inversão do `us(intl)` (padrão ¹²³) |
| Ctrl direito (RCTL) | AltGr | — | — | — | vira `ISO_Level3_Shift`; deixa de ser Ctrl |
| `A` (AC01) | `a` | `A` | `ª` | `Á` | ordinal feminino ("primeir**a**") |
| `O` (AD09) | `o` | `O` | `º` | `Ó` | ordinal masculino ("primeir**o**") |

## 2. Compose (`~/.XCompose`)

| Sequência | Resultado | Nota |
|---|---|---|
| `dead_acute` + `c`/`C` | `ç`/`Ç` | |
| `dead_circumflex` + espaço | `"` | default seria `^`; vale pro keysym, então Shift+6+espaço também dá `"` |

`^` literal: dead key 2× ou AltGr+Shift+6. Trema saiu do mapa; `ü` fica em AltGr+Y.
Recarregar: `ibus restart`.

## 3. Como o mapa é aplicado (mudou em 2026-08-07)

Antes era um autostart que corria contra o GNOME no login. **Não bastava**: além de
perder a corrida às vezes, ele só rodava no login — e **plugar qualquer teclado faz o
GNOME reaplicar o layout dele por cima**, que foi o que derrubou tudo quando o K86
chegou. Agora quem aplica é o próprio GNOME:

- `install.sh` copia `layout/victor` pra `/usr/share/X11/xkb/symbols/victor`
  e registra `victor`/`quotefix` no `/usr/share/X11/xkb/rules/evdev.xml`.
- `gsettings ... sources "[('xkb','victor+quotefix'),('xkb','br')]"`.
- Sobrevive a login **e** a hot-plug. Não tem corrida.
- **Um `apt upgrade` do pacote `xkb-data` reescreve o `evdev.xml`** e apaga a entrada.
  Quando o `ª`/`º` sumir depois de um upgrade, é só rodar o script de novo (é idempotente).
- `~/.local/bin/xkb-quotefix.sh` + `~/.config/autostart/xkb-quotefix.desktop` estão
  **obsoletos**, mantidos como rede de segurança para o primeiro login pós-mudança.
  Deu certo aquele login → apagar os dois.

## 4. udev (sistema, com sudo)

- `99-attackshark.rules` — hidraw do K86 (`3151` + PIDs de cabo) e do receptor do
  mouse (`1d57:fa65`) sem root. Cópia na raiz do projeto.
- `udev/99-freewolf-f75.rules` e `udev/99-battlog-mouse.rules` — hardware antigo,
  continuam instalados e inofensivos.

## 5. Firmware do teclado (K86)

**Não há CLI própria, e é de propósito.** O canal de config (`0xFFFF` usage 2, feature
64B) **só responde por cabo USB** — testado: pelo dongle 2.4G ele aceita a escrita e
devolve zeros. Por cabo, o [sharkfin](https://github.com/dniminenn/sharkfin) (GPL, cobre
a família ROYUAN inteira) já faz modos de luz, cor per-key, remap, macro e sleep, e roda
até no browser em `app.getsharkfin.com` sem instalar nada. O K86 guarda em flash.

Ou seja: **plugar o cabo → configurar no sharkfin → desplugar**. Escrever um `k86ctl.py`
só reescreveria o sharkfin para funcionar em menos casos.

## 6. Cron — battlog

```
*/10 * * * * /caminho/para/keyboard-mouse-config/kmctl probe --wait 90
```

**Os dois resolvidos em 2026-08-08.** Teclado: byte 1 do frame de status do dongle. Mouse:
byte 4 do report `0x03` (provisório — menos evidência). O `show` desenha os dois. Detalhes e
o que já foi eliminado por teste em `devices/attackshark_k86/PROTOCOL.md` e
`devices/delux_m900pro/PROTOCOL.md`.

**Ponto cego (medido em 2026-08-23): com o teclado no carregador, o percentual do dongle não
vale.** O `0xF7` que o `probe` manda não é opcode válido, e o protocolo devolve *a resposta
anterior* — enquanto o teclado está na tomada ele para de alimentar esse buffer e o dongle
republica o valor de antes da carga. Ficou 5h30 cravado em 81% e depois voltou a marcar os
30% de antes de dormir, com a bateria cheia. Tirado o cabo, corrigiu para 100% em 2 min.
Carregando, a fonte certa é **a tela do teclado**. A flag do byte 3 **não** é "carregando" —
ela oscila 0/1 sem cabo nenhum.

No modo cabo o teclado enumera como `3151:4015` e aí sim responde ao protocolo (o `identify`
devolve board id `1168`); pelo dongle `3151:4011` nunca responde. Os dois canais convivem — com
o cabo plugado o dongle continua reportando bateria, então o log não fica com buracos.

## 7. Widget de bateria no painel (2026-08-23)

`panel/battlog@victor/`, symlinkada pelo `install.sh` para
`~/.local/share/gnome-shell/extensions/`. Mostra os dois percentuais na barra de cima.

Lê `~/.cache/battlog-status`, escrito pelo `kmctl watch` do `battlog.service` — a
extensão não toca em hidraw nem em sqlite. Desde 2026-08-24 ela **vigia** o
arquivo em vez de reler por tempo, então reflete a mudança na hora. Sem o serviço
rodando (ou `ts` com mais de 30 min) ela mostra `—` em vez de um número velho.
Detalhes em `battery/README.md`.

Aparece só depois de reiniciar o shell (X11: Alt+F2, `r`).

## 8. Organização do repo (2026-08-23)

Um diretório por modelo em `devices/`, com IDs, leitura de bateria, controle (se
houver) e o protocolo em Markdown, tudo junto. `kmctl` é o único executável: ele não
conhece modelo nenhum, pergunta ao `devices/` quem está plugado e oferece o que cada
um declarar em `CAPS`. O que um modelo comprovadamente **não** faz vai em `WONT` e
vira mensagem de erro — é onde mora o "o K86 não faz RGB por 2.4G, e por quê".

Contrato e receita para adicionar um modelo: `devices/README.md`.
`kmctl selftest` valida o contrato de todos os módulos sem precisar de hardware.

## 9. Delux M800 PRO (2026-08-24) — máquina do André

Esta seção descreve **outra máquina**, não a de 2026-08-07 das seções acima.
Aqui o teclado é um Dell KB216 com fio (não suportado, e não precisa ser: fio
não tem bateria) e o mouse é um **Delux M800 PRO** por receptor 2.4G.

- **Do projeto, só a metade do mouse está instalada.** `udev/99-delux-m800pro.rules`,
  o `battlog.service` e a extensão do painel. A camada XKB (`victor(quotefix)`,
  `~/.XCompose`, os `gsettings` de input-sources) **não** foi aplicada — o layout
  desta máquina é `br` puro, e trocá-lo não tem relação com o mouse. Quem quiser
  a parte de teclado depois roda o `install.sh`, que faz as duas.
- O dongle enumera como `248a:5b2f` com strings **XCTECH / Wireless-Receiver**
  (VID da TeLink). Procurar "Delux" no `lsusb` não acha nada.
- Bateria por request/response, não por anúncio: `SET_FEATURE` opcode `0x20` no
  report `0x0c` da interface 1, depois `GET_FEATURE`. Byte 18 = percentual.
  Medido, não deduzido — e o canal foi provado mudo com o mouse em uso.
- O mouse é o primeiro a ter caps de escrita, o que obrigou a mudar o despacho
  do `kmctl` (ver `devices/delux_m800pro/PROTOCOL.md` e o `escolher()`).
- **`battery` e `rgb` foram executados contra o hardware.** A flag de carga foi
  confirmada plugando o cabo (byte 19 vira 1, e só ele e o percentual se movem).
  O `rgb` funciona — mas o efeito **só aparece apertando o botão de DPI**, o que
  quase produziu um falso negativo.
- `sleep` e `remap` nunca correram no mouse: só assert de byte no selftest.
  `--dry-run` antes.
- **Modo cabo (`248a:5b2e`) segue sem teste.** Cabo numa porta da máquina
  carrega, mas não enumera nada — zero evento USB. Cabo, header do painel
  frontal ou firmware, não se sabe.

### Fone JBL Wave Buds 2, no mesmo painel

Entrou junto, e não custou engenharia reversa: o BlueZ publica a bateria em
`org.bluez.Battery1` e o `bluetoothctl` concorda com o `upower` (90% no teste).
Preferimos o BlueZ porque o UPower cacheia — estava 44 min atrasado na medição.

Isso acrescentou a categoria `headset` em `devices.KINDS` e o segundo transporte
(a fonte `bluez_any`). A extensão do painel deixou de ter as categorias no código: agora
lê as que o `battlog-status` traz, então um quarto aparelho não pede mexer em JS.

Efeito colateral bem-vindo: **categoria sem aparelho some do painel** em vez de
mostrar `—` para sempre. Nesta máquina o ícone de teclado desapareceu, que é o
certo — o Dell é com fio. `—` agora só aparece quando o serviço morre, que é
justamente o caso que precisa ser visível.

### Descoberta automática (2026-08-24)

O painel passou de um slot por **categoria** (no máximo um aparelho de cada) para
um slot por **aparelho**, e a lista deixou de vir do código. Fone + mouse +
teclado sem fio ao mesmo tempo são três coisas para mostrar, não uma escolha a
fazer.

Junto vieram as duas fontes genéricas (`bluez_any`, `power_supply_any`): aparelho
novo com bateria aparece sozinho, sem diretório. Diretório de modelo agora só se
justifica para o que nenhuma fonte vê — o M800 PRO e o K86, cuja bateria sai por
opcode de fabricante.

Com fio ou sem bateria não aparece, e isso **não é regra especial**: o Dell KB216
e o adaptador TP-Link simplesmente não têm o que reportar. Verificado.

**A caixinha do fone é indetectável.** No cabo ela não enumera em USB, não cria
`power_supply`, não aparece no UPower nem no BlueZ — puxa 5V e cala. Então dos
três aparelhos que o André queria ver, o painel faz dois. Não há contorno: o
número teria que ser inventado.

### Tempo real (2026-08-24)

O cron de 10 min saiu; entrou o **`battlog.service`** (unidade de usuário) rodando
`kmctl watch`. O atraso era de até 12 min (cron 10 + painel relendo a cada 2);
agora presença é instantânea e percentual é no máximo 20 s.

- `wake.py`: despertadores por **udev** (socket netlink, stdlib pura) e **BlueZ**
  (`gdbus monitor`). Medido: 2,0 s do evento até acordar.
- A extensão passou a **vigiar** o arquivo de cache (`Gio.FileMonitor`) em vez de
  reler a cada 2 min. O timer que sobrou serve a um caso só: quando quem escreve
  morre, ninguém gera evento, e é ele que faz o `—` aparecer.
- Histórico continua a cada 10 min — cache e banco têm cadências diferentes de
  propósito.

Regra que segurou o desenho: **despertador nunca é fonte de dado.** Entrega um
bit, e quem lê é sempre o caminho normal. Sem isso haveria um segundo parser de
D-Bus competindo com o `devices.present()`.

**O que não fica em tempo real, e não tem conserto:** o percentual. O fone reporta
bateria de vez em quando pelo próprio rádio, e o mouse muda 1% a cada muitos
minutos. Ler mais vezes não cria informação que ninguém mandou.

## 10. Máquina `calecos` (2026-08-24) — GNOME 50.1 em Wayland

**Terceira máquina, e a que mais foge do que as seções acima descrevem.** Nada do
hardware documentado neste repo está aqui.

| o que | esta máquina | o que o repo assumia |
|---|---|---|
| sessão | **Wayland** | X11 |
| GNOME Shell | **50.1** | 46 |
| teclado + mouse | receptor combo `3554:fa09` ("CX 2.4G Wireless Receiver") | K86 `3151:4011` |
| mouse | **Attack Shark** `1d57:fa61` (enumera "Beken USB Gaming Mouse") | Delux M800 PRO `248a:5b2f` |
| fone | HyperX Cloud III Wireless `03f0:0c9d` | JBL Wave Buds 2, por Bluetooth |

Consequências, cada uma medida aqui — menos onde estiver dito que não:

- **`Alt+F2` → `r` não existe em Wayland.** Reiniciar o shell é deslogar e logar
  de novo. Todo lugar deste repo que manda usar `Alt+F2 r` vale só para X11.
- **A extensão declarava só a `46`** e por isso o shell a recusaria. Passou a
  declarar `46`–`50`, e **funciona: `State: ACTIVE` na 50.1, zero erro de JS no
  journal.** Verificado, não deduzido. O código já era ESM (`gi://`,
  `export default class ... extends Extension`), o formato de 45+, e não usa nada
  removido no caminho — em particular não passa `vertical` ao `St.BoxLayout`, que
  é o que quebra extensão antiga na 48+.

      gnome-extensions info battlog@victor      # State: ACTIVE
      journalctl --user -b | grep -i battlog

- **`Alt+F2` → `r`: três coisas, e só a primeira era sabida.** Todas medidas na 50.1:
  1. o atalho **não existe em Wayland** — o shell é o compositor e não pode se
     reiniciar sem derrubar a sessão. O diálogo trata o `r` como um programa
     qualquer e responde `command not found`;
  2. e **não faz falta**: a afirmação de que "o GNOME varre a pasta de extensões
     uma vez, na inicialização" **não vale na 50.1**. Ele monitora a pasta, e
     pegou a extensão no instante em que o `setup-calecos.sh` criou o symlink —
     sem deslogar. Na 46 era verdade; em algum ponto do caminho deixou de ser;
  3. e o gesto **dá para devolver**, fazendo outra coisa: `panel/reload-extensions`,
     instalado como `/usr/local/bin/r`, recarrega uma extensão (disable+enable, que
     faz o shell reler o arquivo do disco). Vai em `/usr/local/bin` porque o
     `~/.local/bin` está no PATH do shell mas **não** no da sessão, que é o que o
     diálogo do `Alt+F2` enxerga.

- **Recarregar TODAS as extensões de uma vez quebra a sessão.** Aprendido do jeito
  ruim aqui: extensões que fazem monkey-patch no shell (`ding`, `dash-to-dock`,
  `hanabi`) guardam a função original para restaurar no `disable`. Derrubadas fora
  de ordem, uma restaura por cima da outra, a cadeia se perde
  (`replaceData.old_get_window_actors is undefined`) e **cinco extensões caíram em
  ERROR de uma vez** — inclusive a battlog. Extensão em ERROR **não volta com
  `enable`**: o shell não a reimporta. Só reiniciando o shell, o que em Wayland
  quer dizer deslogar. Por isso o `r` recarrega **uma só**, e recusa alvo que já
  esteja em ERROR em vez de fingir que resolve.

- **E isso expôs um bug real da extensão**, que estava lá desde sempre: o
  `disable()` fazia `this._indicator.destroy()` sem guarda. O shell chama
  `disable()` mesmo quando o `enable()` nunca rodou, e aí o `TypeError` põe a
  extensão em ERROR — de onde ela não sai sozinha. Agora é `this._indicator?.` e o
  `enable()` derruba um indicador órfão antes de criar outro.

- **O trecho que desenha aparelho foi exercitado**, já que nenhum hardware daqui
  alimenta o painel: com o serviço parado, duas linhas `dev` sintéticas no cache e
  depois um redesenho (2 slots → 1, com percentual e flag de carga diferentes).
  Zero erro de JS, `State` seguiu `ACTIVE`, e o falso **não** entrou no sqlite — o
  `watch` só grava o que ele mesmo leu. O serviço apagou o enxerto em 5 s.

- **`kmctl status` não é só leitura — ele reescreve o cache** (`kmctl:280`). Isso
  importa em dois momentos: rodá-lo com o serviço parado é o que *conserta* um
  cache velho, e rodá-lo no meio de um teste como o de cima apaga o teste.
- **Bluetooth desligado** (`systemctl is-active bluetooth` → `inactive`): o
  caminho `bluez_any` está morto aqui até ligar o serviço. Não é bug do repo.
- **Nenhum `power_supply`, nenhum device no UPower além do `DisplayDevice`.**
  Nenhum dos três aparelhos declara bateria na página HID, então o caminho
  `power_supply_any` também não pega nada.
- **Sobra o caminho 3 (sonda de família), e ele precisa de permissão em hidraw.**
  Sem as regras udev instaladas, todo `/dev/hidraw*` fica `0600 root` e o
  `kmctl scan` responde "não expõe bateria por caminho nenhum" para todos os três
  — resposta que não distingue "não tem bateria" de "não pude olhar". Por isso a
  regra do `3554:fa09` foi acrescentada em `udev/99-cx-2.4g-receiver.rules`.
- **Quem é quem, por `bInterfaceProtocol`** (1 = teclado, 2 = mouse), já que o
  nome do USB não diz: o `3554:fa09` expõe as duas — `input16` "…Receiver
  Keyboard" e `input17` "…Receiver Mouse" —, então é um receptor de *kit*, um
  dongle para os dois aparelhos. O `1d57:fa61` também declara interface de
  teclado, mas todos os seus `input*` se chamam "Beken USB Gaming Mouse": é o
  mouse, com o canal de teclado que mouse de jogo usa para macro.
### O que foi montado aqui

Quem monta esta máquina é **`setup-calecos.sh`**, não o `install.sh`. O
`install.sh` faria as duas metades do victor — inclusive sobrescrever o
`~/.XCompose` sem avisar — e a metade de teclado dele não é a desta máquina.

- **Bateria: instalada e verificada.** Extensão do painel symlinkada e habilitada,
  `battlog.service` ativo, regras udev em `/etc/udev/rules.d/`. Os sete
  `/dev/hidraw*` passaram de `0600 root` para `0660 plugdev`.
  **O que exatamente foi verificado:** o aperto de mão entre quem escreve e quem
  lê — o serviço grava `~/.cache/battlog-status` e o `kmctl status` o traz de
  volta. Só que **com carga vazia**: o arquivo tem só a linha `ts`, nenhuma linha
  `dev`. Com carga sintética o desenho também foi exercitado (ver acima); o que
  nunca aconteceu foi um aparelho **real** desta máquina chegar ao painel, e isso
  é consequência do item seguinte, não falha.
- **Teclado: `layout/calecos/`**, que é outro arranjo — `us(intl)` de fábrica, sem
  variante XKB, sem mexer no `evdev.xml`, Ctrl direito continua Ctrl, e um
  `XCompose` de três linhas que só acrescenta o `ç`. O porquê está em
  `layout/calecos/README.md`.
- **Bluetooth continua desligado por escolha.** O `setup-calecos.sh` não o liga. O
  caminho `bluez_any` fica inativo por consequência, e isso não é bug.

### Os três aparelhos: um resolvido, dois em aberto

Nenhum dos três é visto pelos caminhos automáticos — todos caem no caminho 4, o
do opcode de fabricante. Estado de cada um:

**Fone HyperX Cloud III Wireless — RESOLVIDO.** `devices/hyperx_cloud3_wireless/`.
Report `0x66` na página `0xff13`: escreve `66 89 00…`, e a resposta traz o
percentual no byte 4 e a tensão da célula nos bytes 2..3. Medido: `66 89 0f 74 4f`
→ 3956 mV e 79 %, dois campos independentes concordando. Protocolo e a fonte em
`devices/hyperx_cloud3_wireless/PROTOCOL.md`.

Achar isto obrigou a consertar o `find_iface`, que só reconhecia `0xFF00` e
`0xFFFF` como página de fabricante — a faixa vendor-defined é `0xFF00`–`0xFFFF`
inteira, e o fone usa `0xFF13`. O aparelho estava plugado e aparecia como ausente,
**sem erro nenhum**.

**Mouse Attack Shark X6 (`1d57:fa61`) — em aberto, com pista forte.** Ele
**anuncia sozinho** no report `0x03` (página `0x0a`, Input de 4 B):

    03 10 40 02 0a

A família toda tem a mesma forma, com o percentual no último byte:

| modelo | frame | fonte |
|---|---|---|
| Delux M900Pro | `03 50 41 01 PP` | `devices/delux_m900pro/` |
| Attack Shark X11 | `03 55 40 01 PP` | HarukaYamamoto0/attack-shark-x11-driver |
| **Attack Shark X6 (aqui)** | `03 10 40 02 ??` | este frame |

Pelo padrão, o `0x0a` = **10 %**. **Não confirmado**: falta a leitura real do
mouse para comparar, ou ver o valor subir no dock de carga. Sem isso não vira
módulo — 10 % é baixo o bastante para ser um número errado plausível.

**Teclado AULA F75 (receptor `3554:fa09`) — em aberto.** O canal de fabricante é a
página `0xff02`, report `0x13` (Input 19 B e Output 19 B); há também uma Feature
`0xff04` report `0x06` de 7 B, que responde `06 00 02 00 e8 00 cc fb`. Já
eliminado por teste: os opcodes `0x20 0x01` do
[Aula-F75-Max-Driver](https://github.com/VitalyArt/Aula-F75-Max-Driver) (que é
para o F75 **Max**, outro modelo) não produzem resposta no report `0x13`, e
tentá-los como report `0x20` dá `EPIPE` — esse report não existe neste descritor.

## Não ativo

- `checkpoints/01..06` — experimentos de remap de 2026-08-05 (aspas no `` ` ``, dead keys
  na home row etc.), **revertidos pro `baseline`**. **Os scripts não estão neste repo**:
  sobrou o relatório do que cada um fez, em `docs/checkpoints-log.md` e
  `docs/mapa-teclas-checkpoints.md`. Não há `checkpoints/restore.sh` para rodar — quem
  quiser um deles de volta reconstrói a partir do relatório. **Cuidado ao fazer isso:** o
  `baseline` é anterior ao ajuste de 2026-08-06 (Shift+`'` ainda era `"` direto, sem
  `dead_circumflex`) — voltar a ele desfaz esse ajuste silenciosamente.
- **FreeWolf F75** e **AJAZZ AJ139** — hardware fora da mesa desde 2026-08-07, mas
  suportados: `devices/freewolf_f75/` (bateria, luz, cor por tecla, remap, sono) e
  `devices/ajazz_aj139/` (bateria). Sem como testar ao vivo aqui — o que dá para
  verificar sem eles está no `kmctl selftest`, em asserts de bytes de pacote.
