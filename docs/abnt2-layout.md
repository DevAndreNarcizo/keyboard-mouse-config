# Ajuste EN → ABNT2 (teclado 75%)

## Contexto

Troca do teclado físico de ABNT2 full size para um 75% ANSI/ISO (FreeWolf F75). O 75% não tem tecla
dedicada de `ç` nem o layout físico do ABNT2, então o input source do dia a dia é o **`us+intl`** do
GNOME (US International com dead keys), ao lado do `br` (ABNT2 virtual, sem teclado físico
correspondente). Ambiente: GNOME/Ubuntu em **X11**, `ibus-daemon` ativo.

Duas mecânicas diferentes do X11 entram em jogo:
- **Compose** (`~/.XCompose`): resolve *sequências* de duas teclas (dead key + tecla seguinte). Não
  muda o que uma tecla emite sozinha.
- **XKB symbols**: define o que cada tecla emite em cada nível (sem modificador, Shift, AltGr,
  AltGr+Shift). É o único jeito de mudar o comportamento de uma tecla *sozinha*, ou de dar função de
  modificador a uma tecla que não tinha (caso do Ctrl direito virando AltGr).

## Tabela completa — ABNT2 × teclado atual

Levantamento tecla a tecla comparando `/usr/share/X11/xkb/symbols/br` (ABNT2 real) com o setup atual
(`us(intl)` + patches).

| Caractere(s) | Como é no ABNT2 | Como sai no setup atual | Status |
|---|---|---|---|
| á é í ó ú | tecla dedicada de acento (`dead_acute`) + vogal | `dead_acute` (tecla `'`) + vogal | ✅ igual |
| à (crase) | `dead_grave` + a | `dead_grave` (tecla `` ` ``) + a | ✅ igual, tecla física diferente |
| â ê ô | `dead_circumflex` + vogal | `Shift+6` (`dead_circumflex`) + vogal | ✅ igual, tecla física diferente |
| ã õ | `dead_tilde` + vogal | `Shift+` da tecla `` ` `` (`dead_tilde`) + vogal | ✅ igual, tecla física diferente |
| ç / Ç | tecla dedicada | `dead_acute` + `c`/`C` (override de Compose) | ✅ ajustado — Problema 1 |
| `"` aspas duplas | Shift+tecla de aspas, direto | `Shift`+acento, direto | ✅ ajustado — Problema 3 |
| `'` apóstrofo | tecla dedicada | `dead_acute`+espaço, ou `AltGr`+acento | ✅ ok |
| `^` circunflexo solto | `AltGr`+tecla | `Shift+6`+espaço, ou `AltGr+Shift+6` | ✅ ok |
| `¿` `¡` | `AltGr`(+Shift) | `AltGr`(+Shift) na fileira de números | ✅ ok (precisa do AltGr novo) |
| `®` `©` | `AltGr+R` / `AltGr+C` | `AltGr+R` / `AltGr+C` | ✅ igual |
| `§` `°` | `AltGr+=` / `AltGr+;` | `AltGr+S` / `AltGr+;` | ✅ ok, `§` em tecla física diferente |
| `µ` | `AltGr+M` | `AltGr+M` | ✅ igual |
| `¬` | tecla dedicada (canto superior esquerdo) | `AltGr+\` | ✅ ok, tecla física diferente |
| `¹ ² ³ ¼ ½ ¾` | fileira de números, `AltGr` | fileira de números, `AltGr` | ✅ ok (`¹` exigiu fix — Problema 5) |
| `ª` (ordinal feminino) | `AltGr+]` | `AltGr+A` | ✅ ajustado — Problema 4 (posição por mnemônico, a pedido do Victor) |
| `º` (ordinal masculino) | `AltGr+\` | `AltGr+O` | ✅ ajustado — Problema 4 (idem) |
| `/` `?` | tecla extra, só existe no ABNT2 físico | tecla padrão americana (mesma posição do `us`) | ⚠️ não é gap — a tecla extra não existe fisicamente no 75%, mas a função não se perde |
| `\` `\|` | tecla extra ISO, só existe no ABNT2 físico | tecla padrão americana | ⚠️ não é gap — idem |
| `⅜` (três oitavos) | `AltGr+5` | **não mapeado em nenhuma tecla** | ❌ gap conhecido, não corrigido — uso praticamente nulo em português, não vale a pena |

## O que foi mudado de fato (resumo tecla por tecla)

Das linhas acima, só estas exigiram alteração — o resto já funcionava de fábrica no `us(intl)` ou por
Compose padrão do sistema:

| Tecla | Antes (`us+intl` puro) | Agora |
|---|---|---|
| Shift + tecla de acento | trema (`dead_diaeresis`) | `"` direto |
| `dead_acute` + `c`/`C` | `ć`/`Ć` (polonês) | `ç`/`Ç` |
| `AltGr+1` | `¡` | `¹` (mantém o padrão `¹²³` com `AltGr+2`/`AltGr+3`) |
| Ctrl direito | Ctrl (igual ao esquerdo) | AltGr — **não funciona mais como Ctrl** |
| `AltGr+A` | `á` | `ª` |
| `AltGr+O` | `ó` | `º` |

## Histórico — como cada ajuste foi decidido

### Problema 1 — cedilha: `dead_acute + c` virava `ć` em vez de `ç`

**Causa:** no `us(intl)`, a tecla de acento (`'`) é `dead_acute` no nível 1. A combinação
`dead_acute + c` está definida na tabela Compose padrão do sistema
(`/usr/share/X11/locale/en_US.UTF-8/Compose`) como `ć`/`Ć` (polonês/croata), não como `ç`.

**Solução:** `~/.XCompose` herdando tudo do Compose padrão e sobrescrevendo só essas duas sequências
(`include "%L"` + as duas linhas de override). Recarrega com `ibus restart`. Nenhuma das outras ~5000
combinações do Compose padrão é afetada.

### Problema 2 — aspas duplas e circunflexo (nenhuma alteração necessária)

Já vêm prontos no `us(intl)` como dead keys nativas:

| Caractere | Combinação |
|---|---|
| `"` aspas duplas | tecla de acento + **Shift**, depois **espaço** (ou direto: `AltGr+Shift`+tecla de acento) |
| `'` apóstrofo | tecla de acento, depois **espaço** (ou direto: `AltGr`+tecla de acento) |
| `^` circunflexo solto | `Shift+6`, depois **espaço** (ou direto: `AltGr+Shift+6`) |
| `ê â ô î û` | `Shift+6`, depois a vogal |

Lógica: dead key + espaço solta o caractere ASCII puro; dead key + vogal acentua; AltGr(+Shift) na
mesma tecla dá o resultado direto sem precisar do espaço.

### Problema 3 — `Shift + acento` sozinho virar aspas direto (sem espaço)

O fluxo do Problema 2 (`Shift+acento` + espaço) era lento demais pra aspas duplas, de longe o
caractere mais usado no dia a dia. Isso não dá pra fazer via Compose (que só resolve sequência de
duas teclas) — precisou mexer no símbolo XKB da tecla `AC11` (a tecla de acento/aspas).

Nasceu aí a variante custom `~/.config/xkb/symbols/victor` (`quotefix`), carregada substituindo o
grupo 2 do layout (`br,victor(quotefix),us` no lugar de `br,us(intl),us`). Por ser uma alteração
direta no X server via `xkbcomp`, não sobrevive a logout sozinha — precisa reaplicar a cada login, daí
o `~/.local/bin/xkb-quotefix.sh` + `~/.config/autostart/xkb-quotefix.desktop`.

**Gotcha técnico:** `setxkbmap -layout "...,victor(quotefix),..."` direto **falha** nesta máquina
(`Error loading new keyboard description`). O que funciona: gerar o keymap com `setxkbmap ... -print`
e dar pipe pro `xkbcomp -I~/.config/xkb - "$DISPLAY"`, contornando o load interno do `setxkbmap`.

**Regressão conhecida — corrida de largada no login:** o script roda com sucesso, mas o GNOME
reaplica o `br,us(intl),us` de fábrica **depois**, porque autostart e a aplicação do input source do
GNOME disparam em paralelo via systemd, sem ordem garantida. Tentativa de fix sem sudo (registrar a
variante direto no gsettings) falhou — o GNOME só enxerga `/usr/share/X11/xkb`, não
`~/.config/xkb`, e ignora a variante silenciosamente. Mitigação atual: o script vira um retry loop
(reaplica a cada 2s por ~20s após o login). Reduz bastante a chance da corrida, mas não elimina 100%.
Fix definitivo exigiria sudo (mover o arquivo pra `/usr/share/X11/xkb/symbols/` e trocar o input
source no gsettings) — Victor optou por não usar sudo até agora.

### Problema 4 — indicadores ordinais `º`/`ª` sem caminho razoável

Levantamento sistemático comparando `br` (ABNT2) com `us(intl)` + patches, tecla a tecla — deu origem
à tabela completa no topo deste documento. Único gap real encontrado (fora o `⅜`, irrelevante): `º`/`ª`
não existiam em nenhuma tecla do `us(intl)` puro.

**O F75 não tem AltGr físico.** O XML do layout oficial (`f75ctl/reference/layouts/kb-k600t.xml`)
mostra que a posição onde ficaria o Alt direito manda o código `Fn` (proprietário do firmware, nunca
chega ao Linux como modificador). Não existe tecla física sobrando pra virar AltGr sem sacrificar algo
já em uso (Ctrl esquerdo, Enter, `\`) ou inexistente nesta placa (Menu, Win direito).

Três tentativas até a solução final:
1. **Compose em `dead_abovering`** — dependia de AltGr, que não existe. Descartada.
2. **Firmware Fn+1/Fn+2 → HID F13/F14 → XKB liga direto** (via `f75ctl`, que já sabe remapear teclas
   na camada Fn) — funcionava, mas achado estranho: o objetivo do projeto é o teclado se comportar
   como Windows/ABNT2, e dois atalhos fixos não têm nada a ver com como AltGr funciona de verdade
   (segura + qualquer tecla). Descartada. (Pegadinha encontrada no caminho: **`Fn+1` é hardwired de
   fábrica** — entra no "modo de luz custom", nunca passa pelo protocolo de remap; documentado no
   `PROTOCOL.md` do `f75ctl`, tabela de atalhos Fn de fábrica.)
3. **Final — Ctrl direito vira AltGr de verdade.** `Control_L`/`Control_R` são keycodes distintos no
   X11 (`<LCTL>`/`<RCTL>`); no F75 o Ctrl direito fica ao lado do Fn. `key <RCTL> { [
   ISO_Level3_Shift ], type[group1]="ONE_LEVEL" };` transforma o Ctrl direito num AltGr real. Troca:
   ele para de funcionar como Ctrl (o esquerdo cobre tudo). Bônus: todo o resto que dependia de AltGr
   (`¿¡®©§°µ`) passa a funcionar de graça nas posições padrão do `us(intl)`.

`º`/`ª` passaram por dois lugares: primeiro `<AD12>`/`<BKSL>` (posições físicas reais do ABNT2, `]` e
`\`), depois movidos a pedido do Victor pra **`AltGr+A`/`AltGr+O`** (mnemônico
"primeir**a**"/"primeir**o**") — sacrifica o acesso a `á`/`ó` via AltGr nessas duas teclas, sem
problema porque o caminho principal de acentos (dead key) não muda.

### Problema 5 — `AltGr+1` dava `¡` em vez de `¹` (quebrava o padrão ¹²³)

Testando o AltGr novo, `AltGr+2`/`AltGr+3` davam `²`/`³` direto, então o esperado pra `1` era `¹`. O
`us(intl)` tem os níveis 3/4 da tecla `1` **invertidos** em relação ao ABNT2 real:

- `us(intl)` AE01: `[1, exclam, exclamdown, onesuperior]` → AltGr = `¡`, AltGr+Shift = `¹`
- `br(abnt2)` real AE01 (herdado de `symbols/latin`, variante `basic`): `[1, exclam, onesuperior,
  exclamdown]` → AltGr = `¹`, AltGr+Shift = `¡`

Único caso encontrado até agora onde o `us(intl)` difere do ABNT2 não só na posição, mas na *ordem*
dos níveis pro mesmo par de caracteres — não foi feita varredura exaustiva desse tipo específico
(nível 3×4 trocados) em todas as outras teclas do layout.

## Arquivos alterados

### `~/.XCompose`
```
include "%L"

<dead_acute> <c> : "ç" ccedilla
<dead_acute> <C> : "Ç" Ccedilla
```
Recarrega com `ibus restart`.

### `~/.config/xkb/symbols/victor`
```
partial alphanumeric_keys
xkb_symbols "quotefix" {
    include "us(intl)"
    key <AC11> { [ dead_acute, quotedbl, apostrophe, quotedbl ] };
    key <AE01> { [ 1, exclam, onesuperior, exclamdown ] };
    key <RCTL> { [ ISO_Level3_Shift ], type[group1]="ONE_LEVEL" };
    key <AC01> { [ a, A, ordfeminine, Aacute ] };
    key <AD09> { [ o, O, masculine, Oacute ] };
};
```
Aplicado por cima do input source `br,victor(quotefix),us` (grupo 2). Recarrega com:
```bash
setxkbmap -I"$HOME/.config/xkb" -rules evdev -model pc105+inet -layout "br,victor(quotefix),us" -print \
  | xkbcomp -I"$HOME/.config/xkb" - "$DISPLAY"
```

### `~/.local/bin/xkb-quotefix.sh` + `~/.config/autostart/xkb-quotefix.desktop`
Reaplicam o comando acima por ~20s a cada login (ver **Pendências** abaixo).

### `gsettings org.gnome.desktop.input-sources`
```
[('xkb', 'br'), ('xkb', 'us+intl')]
```
Não muda — a variante `victor(quotefix)` não aparece aqui porque o GNOME só enxerga
`/usr/share/X11/xkb`, não `~/.config/xkb` (ver Pendências).

Nenhuma alteração exigiu sudo nem tocou em arquivo de sistema — tudo é por usuário e reversível
(apagar os arquivos volta ao comportamento padrão do `us(intl)`).

## Pendências / instável

- **Corrida de largada no login:** a variante XKB depende do autostart rodar *depois* do GNOME
  aplicar o input source de fábrica, sem ordem garantida — às vezes perde. Mitigação atual: retry
  loop de ~20s. Fix definitivo exigiria sudo. Se algo parecer "voltou ao normal" depois de um boot, é
  essa corrida, não uma regressão do que foi configurado aqui.
- `⅜` (três oitavos) não tem caminho nenhum no setup atual — gap conhecido e ignorado (uso
  praticamente nulo em português).
- Não foi feita varredura exaustiva de inversões nível-3×4 (o tipo de bug do Problema 5) em todas as
  teclas do layout — só a `1` foi encontrada e corrigida.

## Windows — como replicar (se algum dia precisar)

O Windows não tem equivalente nativo ao Compose do X11. Caminho mais simples: **WinCompose**
(open source, wincompose.info — confirme antes de baixar), que reintroduz a mesma ideia de
dead keys/compose.

1. Instalar o WinCompose e escolher a tecla de **Compose** (Right Alt, Caps Lock ou Menu).
2. Em `%AppData%\WinCompose\.XCompose` (o WinCompose já mescla com as sequências padrão dele):
   ```
   <dead_acute> <c> : "ç"
   <dead_acute> <C> : "Ç"
   ```
3. Reiniciar o WinCompose (bandeja → Restart).

Fluxo resultante: **Compose**, depois `'` (acento), depois `c` → `ç` — equivalente ao Problema 1. As
combinações do Problema 2 (aspas, circunflexo, vogais acentuadas) são as mesmas sequências, só
trocando a tecla morta do Linux pela tecla Compose do Windows.

O Problema 3 **nem existe no Windows com WinCompose** — a tecla `'` sozinha sempre emite normal, só a
tecla Compose dispara composição. Isso só mudaria se optasse pelo layout nativo "United States-
International" do Windows (dead keys embutidas, sem WinCompose) e quisesse inverter um nível
específico de uma tecla — aí o equivalente à edição de símbolo XKB é o **Microsoft Keyboard Layout
Creator (MSKLC)**, ferramenta oficial pra compilar um layout customizado (`.dll`, instalado como
driver, exige reiniciar sessão). Bem mais trabalho que o WinCompose — só vale a pena se o objetivo for
reproduzir "tecla sozinha muda de caractere" e não só dead keys customizáveis.
