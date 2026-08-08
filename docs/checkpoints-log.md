# Checkpoints do ajuste EN → ABNT2

Cada checkpoint é uma cópia dos 4 arquivos que esse ajuste toca. `resetar tudo` = voltar pro
checkpoint `baseline`, com `./restore.sh baseline`.

## baseline (2026-08-05)

Estado documentado em `../abnt2-layout.md`, seção "O que foi mudado de fato (resumo tecla por
tecla)". Corresponde a:

| Tecla | Antes (`us+intl` puro) | Neste checkpoint |
|---|---|---|
| Shift + tecla de acento | trema | `"` direto |
| `dead_acute` + `c`/`C` | `ć`/`Ć` | `ç`/`Ç` |
| `AltGr+1` | `¡` | `¹` |
| Ctrl direito | Ctrl | AltGr (não funciona mais como Ctrl) |
| `AltGr+A` | `á` | `ª` |
| `AltGr+O` | `ó` | `º` |

Arquivos:
- `baseline/XCompose` → `~/.XCompose`
- `baseline/xkb-symbols-victor` → `~/.config/xkb/symbols/victor`
- `baseline/xkb-quotefix.sh` → `~/.local/bin/xkb-quotefix.sh`
- `baseline/xkb-quotefix.desktop` → `~/.config/autostart/xkb-quotefix.desktop`

`gsettings org.gnome.desktop.input-sources` não muda entre checkpoints (sempre
`[('xkb', 'br'), ('xkb', 'us+intl')]`) — não faz parte da restauração.

## 01-tlde-quotes (2026-08-05)

Ajuste pedido: a tecla `` ` ``/`~` (TLDE, canto superior esquerdo) vira aspas direto — sem AltGr, sem
Compose, sem dead key.

```
key <TLDE> { [ apostrophe, quotedbl, grave, asciitilde ] };
```

- Nível 1 (sem modificador): `'`
- Nível 2 (Shift): `"`
- Nível 3/4 (AltGr / AltGr+Shift): mantidos como no `us(intl)` original — `` ` `` e `~` soltos
  (símbolo puro, sem compor com a vogal seguinte).

**Atenção — consequência não pedida explicitamente:** essa tecla era quem carregava `dead_grave` e
`dead_tilde` (níveis 1/2 do `us(intl)`), que são o mecanismo de compor `à` (crase) e `ã`/`õ` (dead
key + vogal). Com a mudança, **essa tecla não compõe mais nada** — `` ` `` e `~` viram símbolos soltos
via AltGr, não dead keys. Não relocei `dead_grave`/`dead_tilde` pra nenhuma outra tecla porque não foi
pedido; `à`/`ã`/`õ` ficam sem tecla de acesso até o próximo ajuste definir onde eles vão.

Único arquivo que mudou nesse checkpoint: `xkb-symbols-victor` (os outros 3 são idênticos ao
`baseline`).

## 02-ac10-tilde-circunflexo (2026-08-05) — ⚠️ superado pelo 03, ver correção abaixo

Ajuste pedido: a tecla `;:` (AC10) vira til + circunflexo, atrás do AltGr ("com alt").

```
key <AC10> { [ semicolon, colon, dead_tilde, dead_circumflex ] };
```

- Nível 1/2 (sem modificador / Shift): `;` / `:` — sem mudança.
- Nível 3 (AltGr): `dead_tilde` — `AltGr+;` depois vogal → `ã`/`õ`.
- Nível 4 (AltGr+Shift): `dead_circumflex` — `AltGr+Shift+;` depois vogal → `â`/`ê`/`ô`.

**Isso fecha o buraco do checkpoint 01:** `ã`/`õ` (dead_tilde) tinham ficado sem tecla nenhuma depois
que a TLDE virou aspas — agora têm de novo, em `AltGr+;`. `â`/`ê`/`ô` já tinham caminho por
`Shift+6` (inalterado); agora ganham um segundo caminho em `AltGr+Shift+;`, redundante mas inofensivo.

**Ainda em aberto:** `à` (crase, `dead_grave`) continua sem tecla — não foi pedido ainda onde ele vai.

**Sacrificado nessa tecla** (baixo custo, símbolos raros): `¶` (paragraph, nível 3 original) sem
alternativa nesta variante; `°` (degree, nível 4 original) ainda alcançável por um caminho mais longo
(`AltGr+Shift+0` seguido de espaço, dead key `dead_abovering` que continua intacta na tecla `0`).

## 03-ac10-tilde-circunflexo-fix (2026-08-05)

**Correção do checkpoint 02.** O pedido original ("com alt") tinha sido entendido como til/circunflexo
atrás do AltGr, mantendo `;`/`:` na base. Victor apontou o erro: a confusão veio de estar olhando o
grupo `br` (ABNT2 real, onde essa tecla é `Ç`) antes de trocar pro grupo `en`. Pedido corrigido: til +
circunflexo na **base da tecla, com Shift** — não atrás de Alt.

```
key <AC10> { [ dead_tilde, dead_circumflex, paragraph, degree ] };
```

- Nível 1 (sem modificador): `dead_tilde` — tecla + vogal → `ã`/`õ`.
- Nível 2 (Shift): `dead_circumflex` — tecla + vogal → `â`/`ê`/`ô` (redundante com `Shift+6`, que
  continua igual).
- Nível 3/4 (AltGr / AltGr+Shift): deixados como o `us(intl)` original (`paragraph`/`degree`) — não
  foram tocados porque o pedido foi só "com shift".

**`;`/`:` ficam sem tecla por enquanto** — Victor vai indicar depois pra onde eles vão. Não inventei
um lugar pra eles.

## 04-ac11-agudo-crase (2026-08-05)

Ajuste pedido: a tecla ao lado da `;:` (AC11, hoje `'`/`"`) vira acento agudo + crase.

```
key <AC11> { [ dead_acute, dead_grave, apostrophe, quotedbl ] };
```

- Nível 1 (sem modificador): `dead_acute` — sem mudança, já era assim (tecla + vogal → `á é í ó ú`).
- Nível 2 (Shift): `dead_grave` — **trocado**, era `quotedbl` (o fix do Problema 3, "Shift+acento =
  aspas direto"). Agora tecla + vogal → `à` (crase).
- Nível 3/4 (AltGr / AltGr+Shift): sem mudança (`apostrophe`/`quotedbl`, ainda dão `'`/`"` soltos).

**Isso aposenta o fix do Problema 3 nesta tecla** — faz sentido porque a `` ` ``/`~` (checkpoint 01)
já dá aspas direto na base, então não precisa mais duplicar aqui.

**Fecha o último buraco em aberto:** `à` (crase) estava sem tecla desde o checkpoint 01 — agora mora
em `Shift` desta tecla.

## 05-slash-semicolon (2026-08-05)

Ajuste pedido: a tecla `/?` (AB10) vira `;`/`:` (resolve o "sem botão" do checkpoint 03). `/` e `?`
saem daqui e vão para `AltGr+Q`/`AltGr+W`.

```
key <AB10> { [ semicolon, colon, questiondown, dead_hook ] };
key <AD01> { [ q, Q, slash, Adiaeresis ] };
key <AD02> { [ w, W, question, Aring ] };
```

- `AB10` nível 1/2: `;`/`:` (era `/`/`?`). Nível 3/4 sem mudança (`¿`/`dead_hook`).
- `AD01` (Q) nível 3 (AltGr): `/` (era `ä` — quase nunca usado em português).
- `AD02` (W) nível 3 (AltGr): `?` (era `å` — idem).

Victor propôs `Alt` ou `Ctrl` pra `/`/`?`; recomendei `AltGr` e não `Ctrl` — `Ctrl+Q`/`Ctrl+W` são
atalhos universais (sair do app / fechar aba-janela) usados o tempo todo, e além disso Ctrl não é um
"nível" de teclado como o AltGr: os programas interceptam Ctrl+tecla como atalho antes de virar texto,
então nem funcionaria bem como forma de digitar caractere.

## 06-swap-ac10-ac11 (2026-08-05)

Ajuste pedido: inverter `~^` (AC10) com `´\`` (AC11) — trocar os dois conteúdos inteiros de lugar.

```
key <AC10> { [ dead_acute, dead_grave, apostrophe, quotedbl ] };   // agora agudo+crase
key <AC11> { [ dead_tilde, dead_circumflex, paragraph, degree ] }; // agora til+circunflexo
```

Troca completa (todos os 4 níveis), não só base+Shift — `AC10` (a tecla logo depois do `L`) agora é
`´\`` (agudo/crase), e `AC11` (a próxima, antes do Enter) é `~^` (til/circunflexo). Nenhum caractere
foi perdido, só mudou de tecla.

## Restaurar

```bash
./restore.sh <checkpoint>   # ex.: ./restore.sh baseline  |  ./restore.sh 06-swap-ac10-ac11
```

Copia os 4 arquivos de volta, dá `ibus restart` e reaplica a variante XKB no display atual.
