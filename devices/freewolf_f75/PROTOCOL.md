# FreeWolf F75 — protocolo HID

Engenharia reversa do software oficial Windows (`FREE WOLF F75 setup 1.0.4.4.exe` →
`DeviceDriver.exe` + `XYUI.dll`, família de UI "XYUI"), validada no hardware via
`/dev/hidraw` no Linux. Data: 2026-07-31.

## Identificação USB

Do `reference/config.xml` (`device_type="301"`, `device_info="kb-k600t"`):

| Modo | VID:PID | Interface de config |
|------|---------|---------------------|
| Cabo USB | `1a2c:a073` | `MI_02` |
| Receptor 2.4G | `1a2c:8fff` | `MI_03` |

No Linux o canal de configuração é o `hidraw` cujo report descriptor começa com
Usage Page vendor (`06 02 FF`), com reports IN e OUT de **64 bytes sem Report ID**.
Nesta máquina, no dongle 2.4G, é a **interface 0** (`/dev/hidraw6`).
`f75ctl.py` detecta sozinho procurando `06 xx FF` no descriptor.

Atenção: o `1a2c:afff` comentado no config.xml é um PID antigo de modo cabo.
O dongle `a8a5:2255` (YJX-CHIP/AJAZZ), presente na mesma máquina, **não é o F75**.

## Transporte

Pacote de **64 bytes**, sem checksum, mesmo formato nos dois sentidos:

```
Offset  Tam  Campo
------  ---  -----
0       4    sync: AA 55 CC 33  (idêntico host->kb e kb->host)
4       1    comando
5       59   payload (resto zerado)
```

Writes em `/dev/hidraw` precisam do prefixo **Report ID `0x00`** (65 bytes no
`write()`); o kernel o remove. Sem isso o `0xAA` do sync viraria Report ID.

O teclado **não confirma** comandos de escrita — só responde ao `0x0E`. Ele também
manda `0x0E` espontaneamente de tempos em tempos (status/bateria).

## Comandos confirmados no hardware

| CMD | Direção | Função |
|-----|---------|--------|
| `0x0E` | OUT/IN | status: resposta traz bateria % em `[5]`, flag em `[6]` |
| `0x07` | OUT | modo de iluminação (payload abaixo) |
| `0x0B` | OUT | complemento do `0x07` quando o modo é 24 (custom) |
| `0x09` | OUT | precede o stream de cores por tecla |
| `0xF0`–`0xF5` | OUT | banco de frame 1 — 6 pacotes × 18 teclas × RGB |
| `0xF6`–`0xFB` | OUT | banco de frame 2 — idem |
| `0x04` | OUT | remap de tecla: `[5]`=camada+1, `[6]`=tecla, `[7]`=alvo |
| `0x0F` | OUT | **limpa** o keymap (o app manda *antes* de reenviar tudo) |
| `0x0C` | OUT | tempo de sono: `[5]` = 1 (2 min), 2 (15 min), 3 (30 min), 4 (nunca) |
| `0x0D` | OUT | tempo de resposta das teclas: `[5]` = 1, 2 ou 3 (marchas) |

### `0x07` — modo de iluminação

```
[5] modo - 1        (modo 1..24; ver tabela de modos)
[6] brilho - 1      (brilho 1..5)
[7] velocidade - 1  (velocidade 1..5)
[8] direção         (0/1)
[9] índice de cor   (paleta do firmware; 0 = arco-íris/colorido)
```

Os campos vêm da tabela SQLite `t_light_data` do app
(`mode, brightness, speed, direction, colorful, colorindex, color_value`); o
mapeamento acima foi extraído da função em `0x411130` do `DeviceDriver.exe`.
Note que `color_value` (RGB) **não** vai nesse pacote — cor arbitrária só pelo
modo custom.

Modos (nomes de `reference/language/1033.lan`, ids 501–522): 1 ondas
esquerda/direita, 2 pontos estrelados, 3 ondas cima/baixo, 4 ejeção
bidirecional, 5 ciclo espectral, 6 caleidoscópio, **7 luz estática**, 8
respiração geral, 9 operação cruzada, 10 luz voando, 11 respiração por tecla,
12 pergaminho, 13 serpente, 14 tornado, 15 três acima três abaixo, 16 chuva,
17 moinho, 18 onda senoidal, 19 cavalo a galope, 20 entrecruzado, 22 ritmo de
música, 23 ritmo da tela, **24 custom (por tecla)**.

### Cor RGB arbitrária (modo custom)

Sequência que funciona (validada visualmente):

1. `0x07` com modo 24 → payload `[23, brilho-1, vel-1, 0, 0]`
2. `0x0B` (sem payload)
3. `0x09` (sem payload)
4. `0xF0`..`0xF5`, cada um com **54 bytes** de payload a partir de `[5]`
   = 18 teclas × `(R, G, B)`
5. `0xF6`..`0xFB`, o mesmo conteúdo

São **108 slots** de tecla por banco (324 bytes), indexados pelo `key_index` do
`reference/layouts/kb-k600t.xml` (80 teclas reais, índices 3..101, com buracos).
Ordem dos bytes é **R, G, B** (confirmado: `ff0000` acende vermelho, `00ff80`
acende verde-menta).

**`000000` é transparente**: preto no stream não apaga a tecla, o firmware lê
como "não mexe nesta tecla" e ela mantém a cor anterior. Isso engana feio — um
frame todo preto parece "comando ignorado", e um frame com uma tecla colorida e
o resto preto parece "nada aconteceu" (foi assim que o teste do slot único
falhou duas vezes aqui). Para apagar de fato use **`010101`**, que é invisível a
olho nu; é o que o `f75ctl.py off` manda.

O slot no frame **é** o `key_index` do `reference/layouts/kb-k600t.xml`
(confirmado no hardware: `rgb 0000ff --only esc`, key_index 15, acende só o Esc,
com o resto do frame em `010101`). Os dois bancos são cópias do mesmo conteúdo —
uma tecla só, mandada nos dois, acende uma tecla só.

Os **dois bancos são obrigatórios**: enviando só `0xF0`–`0xF5` a maioria das
teclas fica apagada (no teste inicial só o bloco de índices 54–71, o cluster do
WASD, acendeu). O app faz `Sleep(3ms)` antes de cada pacote — `f75ctl.py` mantém
essa folga (`PACKET_GAP`).

## `0x04` — remap de tecla (confirmado no hardware)

```
[5] camada + 1     (0 = "Top layer", 1 = "Fn layer" -> byte 1 ou 2)
[6] tecla física   (HID usage code, o mesmo `code` do layouts/kb-k600t.xml)
[7] alvo           (HID usage code da nova função)
```

Um pacote por tecla, com ~16 ms entre pacotes (o app faz `Sleep(16)`).
Validado: `04 02 1d 46` deixa **Fn+Z = Print Screen** (visto no fio como
`[2]=0x46` na interface de teclado), e `04 02 19 1d` faz Fn+V digitar `z`.

**Pegadinha que custou horas:** o `0x0F` **NÃO é um commit** — ele *limpa* o
keymap. No app o fluxo é `0x0F` → (todas as teclas da camada 0) → (todas as
teclas da camada 1), sempre reenviando tudo. Mandar `0x0F` depois de um `0x04`
desfaz o remap silenciosamente. Não é preciso commit: o `0x04` já persiste.

O remap é aditivo, então para reverter uma tecla basta remapeá-la para si mesma
(`04 02 19 19`). `raw 0f` zera o keymap inteiro (inclusive outros remaps).

Fluxo de "aplicar tudo" do app, para referência (`0x4101a0`): `0x08` +
`Sleep(100)` → `0x0F` → loop camada 0 → loop camada 1. Por tecla: se
`macro_type` ∈ {0} pula, se ∈ {3,7} usa o stream de macro (abaixo), senão
`0x04`.

Teclas com `fnlayer_disable="1"` no XML não aceitam remap.

### Atalhos Fn de fábrica (do manual impresso, `../freewolf-f75-manual.pdf`)

Nada disso passa pelo protocolo — é tudo firmware:

| Combo | Função |
|-------|--------|
| **Fn+A** | **cor** da strip lateral |
| **Fn+Caps** | **modo** da strip lateral (4: arco-íris, gradiente suave, cor fixa, apagada) |
| Fn+X | liga/desliga o backlight ("keyboard light switch / power saving mode") |
| Fn+PgDn | troca o efeito do backlight principal |
| Fn+↑ / Fn+↓ | brilho do backlight — **e da strip lateral também** (medido) |
| Fn+← / Fn+→ | velocidade do efeito |
| Fn+1 | entra no modo de luz custom |
| Fn+\` | grava/armazena cores custom por tecla (aperta a tecla até a cor desejada) |
| Fn+Backspace | mostra a bateria nas teclas numéricas (1 tecla ≈ 10%) |
| Fn+Espaço (3 s) | **restaura configuração de fábrica** (apaga remaps) |
| Fn+L_Win | trava a tecla Win |
| Fn+Q/W/E | Bluetooth 1/2/3 (segurar = pareamento) |
| Fn+R | 2.4G (segurar = pareamento) |

Usar esses combos de luz tira o teclado do modo custom (o firmware reassume o
backlight), então depois deles é preciso reenviar as cores.

## `0x0C` / `0x0D` — sono e resposta das teclas

Os dois carregam um único byte, lido de comboboxes da aba de configurações do app
(campos `0x56c` e `0x574` do objeto de diálogo; funções `0x411d20` e `0x411e60`).
Os valores são o *item data* dos combos, não o índice:

| `0x0C` (sono) | | `0x0D` (resposta) | |
|---|---|---|---|
| 1 | 2 minutos | 1 | 1ª marcha (mais rápida) |
| 2 | 15 minutos | 2 | 2ª marcha |
| 3 | 30 minutos | 3 | 3ª marcha |
| 4 | não dormir | | |

As latências que o app anuncia por marcha (ids 187–189 do `.lan`): 1ª ≈ 2–3 ms no
cabo / 5–6 ms no 2.4G / 12–13 ms no Bluetooth; 2ª ≈ 4–5 / 7–8 / 14–15; 3ª ≈ 6–7 /
9–10 / 16–17.

Não há commit: o byte vale na hora.

**O que "dormir" faz neste teclado.** O manual (p. 2) documenta **dois** níveis:
"light sleep (no operation automatic light off time): 2 minutes" e "deep sleep:
30 minutes". Ou seja, o backlight apagar aos 2 min é comportamento de fábrica,
independente deste comando — o que invalidou o primeiro teste feito aqui (mandar
`0x0C`=1 = "2 min" e ver a luz apagar aos 2 min não provava nada).

Medido: com `0x0C`=1 e o teclado parado 3 min, o rádio **não** cai — o status
`0x0E` continua chegando a cada ~5,5 s e as teclas seguem digitando. O que
acontece é o backlight desligar.

Ao acordar, uma **tecla basta**: o backlight volta e o firmware restaura o frame
custom que estava guardado (verificado com o frame "só o Esc aceso" — voltou só
o Esc, sem tocar em Fn+X). Numa medição anterior eu só consegui religar com
Fn+X e concluí que a tecla não bastava; aquela conclusão está errada, ou pelo
menos não vale em geral — provavelmente eu estava com o Fn+X desligado na
ocasião.

Depois de uma noite inteira (deep sleep), a cor custom **se perde**: o teclado
acordou com o backlight apagado e, ao religar, só parte das teclas acesa. O
remap do keymap (`0x04`), esse sim, sobreviveu — está em flash.

**Em aberto:** qual dos dois sonos o `0x0C` controla. O teste que discrimina é
mandar `0x0C`=4 (never) e deixar o teclado **3 min sem tecla**: se o backlight
continuar aceso, o comando controla o light sleep (e `never` resolve o apagar);
se apagar aos 2 min mesmo assim, o `0x0C` mexe só no deep sleep e o light sleep
é fixo no firmware. Não pode haver escrita nossa nem tecla durante a janela.

## Macros com sequência — mapeado, não implementado

Para uma tecla virar uma *sequência* de teclas com delays (`macro_type` 3 ou 7),
o app usa outro caminho (`0x4106b0`): stream nos comandos **`0x00`, `0x01`,
`0x02`**, 3 pacotes × 54 bytes, `Sleep(20ms)` entre pacotes e `Sleep(170ms)` no
fim. Buffer: `[0]`=camada+1, `[1]`=tecla, `[2]`=tipo, `[3]`=nº de registros, e
depois **2 bytes por evento** — byte 1 = tecla (VK convertido para HID usage por
`0x441f30`), byte 2 = delay codificado por `0x4232f0(kind, ms)`, que comprime
até 31000 ms em um byte com escala (`kind` 0 = press, 1 = release). Dados vêm de
`t_macro_data` + `t_macrorecord`.

## Não mapeado / limitações

- **Strip bar (fita lateral)**: não é controlável pelo protocolo, mas **é
  controlável pelo teclado**: `Fn+Caps` escolhe o modo e `Fn+A` a cor (manual,
  p. 5) — foi assim que a strip ficou azul. Como a cor dela é um estado próprio
  do firmware, ela não acompanha automaticamente a cor que o software manda; é
  um ajuste manual de uma vez. Testado sem
  sucesso: índice de cor do `0x07` (em modo normal e custom), frames por tecla
  nos dois bancos (inclusive com a ordem invertida), slots além dos 108, e
  comandos de chunk que o app não usa (`0xFC`–`0xFF`, `0xEE`, `0xEF`). Ela
  O campo de brilho do `0x07` também não a afeta (testado com brilho 1: teclas
  mudam, strip não). Quem muda a intensidade dela é o **Fn+↓/Fn+↑**, e esse
  estado é próprio dela: sobrevive aos nossos pacotes de cor. Ela
  também não emite nada no canal vendor quando muda de modo por Fn+Caps Lock, e
  o software oficial não tem nenhum controle para ela (nenhuma string
  `STRIP`/`BAR`/`SIDE` no exe). Conclusão: firmware-only, via Fn+Caps Lock.
  Atenção: o comando `0x08` parece resetar o estado de luz e deixou a strip em
  arco-íris — evite mandá-lo. **`0xFF` no campo de brilho (`0x07[6]`) também é
  para evitar**: não é "brilho 0", é valor inválido e trava o pipeline de luz —
  o teclado passa a ignorar mudança de modo e de frame. Sai mandando um `0x07`
  com brilho válido (1–5), não precisa reset nem religar o teclado.
- **Ler a configuração atual**: não existe. Os comandos `0x0F`, `0x0A` e `0x10`
  não devolvem nada. O app guarda o estado no SQLite dele, não no teclado.
- **Índices da paleta de cor** (`0x07[9]`): mapeados só em parte —
  **0 = vermelho, 6 = um verde/ciano, 7 = colorido** (arco-íris estático), vistos
  no hardware. Os nomes vêm de relato visual, então trate a matiz como
  aproximada; o que é sólido é que cada índice é uma cor fixa distinta. Os nomes na UI são branco, vermelho, laranja, amarelo, verde, ciano,
  azul, roxo, "nenhum" e "colorido" (ids 111–119 e 90 do `.lan`), mas a ordem do
  combo não é a do `.lan` e **o "nenhum" não está na lista** (testei 0, 6 e 7
  atrás dele). Para cor exata use o modo custom.
- **Apagar o LED não existe no protocolo.** Fechado por eliminação: `000000` no
  frame é transparente; brilho 0 (byte `0xFF` em `0x07[6]`) é ignorado, o
  firmware mantém o brilho anterior; não há índice de paleta "sem cor"; e o app
  oficial não tem controle de liga/desliga de luz. O mínimo alcançável é
  `010101` com brilho 1 (o que o `f75ctl.py off` manda) — PWM baixíssimo, mas
  não zero. Off de verdade só pelo **Fn+X**, que apaga a strip lateral também.

## Macros / remap do Fn — estrutura mapeada, não implementada

Achado no exe, ainda **não testado no hardware** (escrever keymap errado pode
deixar teclas inúteis):

- Stream de keymap: comandos **`0x00`, `0x01`, `0x02`**, 3 pacotes × 54 bytes
  (162 bytes), com `Sleep(20ms)` entre pacotes e `Sleep(170ms)` no fim
  (loop em `0x4107d0`).
- Layout do buffer (montado em `0x410c10`): 4 bytes de header (contador de
  registros em `[0]`) e depois **2 bytes por tecla remapeada** — só as teclas
  alteradas entram, não as 80. Byte 1 = tecla (convertida por `0x441f30`,
  tabelas HID↔interno em `0x442000`–`0x442250`), byte 2 = ação (convertida por
  `0x4232f0(kind, valor)`, com `kind=0` para `macro_type==2` e `kind=1` para
  `macro_type==3`).
- Fonte dos dados: tabela `t_key_macro_data(profile, fn_layer, key_code,
  layout_value, macro_type, macro_value, macro_value2, macro_value3)`.
- Provável seleção de perfil/camada antes do stream: **`0x04`** com
  `[5]=perfil+1`, `[6]=camada` (funções `0x410590` e `0x410a11`).
- Macros propriamente ditas (sequência de teclas com delays) vêm de
  `t_macro_data` + `t_macrorecord`; o stream delas ainda não foi localizado.

Para fechar isso o caminho mais seguro é captura USB do app oficial numa VM
Windows (passthrough só do dongle `1a2c:8fff`, `usbmon` + Wireshark, filtro
`usb.endpoint_address == 0x03 || usb.endpoint_address == 0x83`, uma mudança por
captura).

## Recuperação (não testado)

O menu do app tem "Reset Keyboard" e "Restore Factory Settings" (ids 152/153),
que correspondem a **`0x10` com `[5]=0x00`** e **`0x10` com `[5]=0x01`**
(funções `0x418c80` e `0x418d50`). Apagam a configuração do teclado — use só
se algo travar.

## Nota sobre Wine

Descartado: o instalador coloca um driver HID virtual de kernel no Windows
(`vhidev.inf` / `vhidflt.inf`, strings `\\.\vhidflt`, `root\vhidev` no exe) e o
app fala com o dispositivo por `HidD_SetFeature` + SetupAPI através desse filtro.
Nada disso carrega no Wine.
