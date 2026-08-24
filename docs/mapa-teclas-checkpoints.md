# Mapa de teclas — checkpoints 01 a 06

Estado completo da variante `~/.config/xkb/symbols/victor` no checkpoint `06-swap-ac10-ac11`, o
último antes do reset pro `baseline`. Detalhe passo a passo de cada ajuste (o que mudou, por quê, o
que foi sacrificado) em `docs/checkpoints-log.md`.

## Mapa de teclas (checkpoint 06)

| Tecla física | Base | Shift | AltGr | AltGr+Shift | Observação |
|---|---|---|---|---|---|
| `` ` ``/`~` (TLDE) | `'` | `"` | `` ` `` | `~` | aspas direto na base — checkpoint 01 |
| tecla depois do `L` (AC10) | `dead_acute` | `dead_grave` | `'` | `"` | agudo/crase — trocou de lugar com a de baixo no checkpoint 06 |
| tecla antes do Enter (AC11) | `dead_tilde` | `dead_circumflex` | `¶` | `°` | til/circunflexo — trocou de lugar com a de cima no checkpoint 06 |
| `1` (AE01) | `1` | `!` | `¹` | `¡` | mantém o padrão ¹²³ — baseline |
| Ctrl direito (RCTL) | — | — | *(é o próprio AltGr)* | — | não funciona mais como Ctrl — baseline |
| `A` (AC01) | `a` | `A` | `ª` | `Á` | ordinal feminino — baseline |
| `O` (AD09) | `o` | `O` | `º` | `Ó` | ordinal masculino — baseline |
| `/?` (AB10) | `;` | `:` | `¿` | *(dead_hook)* | ponto e vírgula / dois pontos — checkpoint 05 |
| `Q` (AD01) | `q` | `Q` | `/` | `Ä` | barra — checkpoint 05 |
| `W` (AD02) | `w` | `W` | `?` | `Å` | interrogação — checkpoint 05 |

Teclas dedicadas de acento compõem com a vogal seguinte (ex.: `dead_acute` + `a` → `á`); as colunas
AltGr acima são o símbolo solto, sem composição.

## Linha do tempo

1. **01 — `` ` ``/`~` → aspas direto.** Base `'`, Shift `"`. Consequência: essa tecla parou de compor
   `à`/`ã`/`õ` (o `dead_grave`/`dead_tilde` que estavam nela).
2. **02 — `;:` → til/circunflexo atrás do AltGr.** *(superado pelo 03 — entendido errado; a confusão
   veio de estar olhando o grupo `br`/ABNT2 antes de trocar pro grupo `en`.)*
3. **03 — correção do 02.** Til/circunflexo na **base** da tecla `;:` (com Shift, não atrás de Alt).
   Fecha o buraco do `ã`/`õ` aberto no passo 1.
4. **04 — tecla ao lado (`'`/`"`) → agudo/crase.** Base `dead_acute`, Shift `dead_grave`. Aposenta o
   fix antigo de "Shift+acento = aspas direto" nessa tecla (redundante, já que o passo 1 cobre aspas).
   Fecha o buraco do `à` (crase).
5. **05 — `/?` → `;:`.** Resolve o "sem botão" que tinha ficado do passo 3. `/` e `?` foram para
   `AltGr+Q` e `AltGr+W` (não `Ctrl`, que quebraria atalhos universais como fechar aba/sair do app).
6. **06 — troca de lugar entre as duas teclas de acento.** A que tinha ficado com til/circunflexo
   (passo 3) e a que tinha ficado com agudo/crase (passo 4) trocaram de posição entre si.

## Depois deste relatório

Resetado para o checkpoint `baseline` (`./restore.sh baseline`) — os 6 ajustes acima ficam só como
histórico neste relatório e em `docs/checkpoints-log.md`; não estão mais ativos no teclado.
