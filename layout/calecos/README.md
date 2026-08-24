# layout/calecos — a metade de teclado desta máquina

O repo nasceu com `layout/victor`: uma variante XKB (`victor(quotefix)`) que
sobrescreve 5 teclas para um 75% ANSI digitar como ABNT2, e um `~/.XCompose` que
vem junto. **Esta máquina não usa nada disso, de propósito.**

Aqui o arranjo é outro e mais simples:

| camada | victor | calecos |
|---|---|---|
| variante XKB | `victor(quotefix)`, instalada em `/usr/share/X11/xkb/` | **nenhuma** — `us(intl)` de fábrica |
| input sources | `[victor+quotefix, br]` | `[us+intl]` |
| Ctrl direito | vira `ISO_Level3_Shift` (deixa de ser Ctrl) | **continua Ctrl** |
| Compose | `layout/XCompose` (ç + `dead_circumflex`+espaço = `"`) | `layout/calecos/XCompose` (só o ç) |

Por que não o `victor`: ele resolve um problema que aqui não existe. O ganho
grande dele é dar um AltGr **de verdade** num teclado 75% sem AltGr físico,
sacrificando o Ctrl direito — e ordinais `ª`/`º` em AltGr+A/O. O custo (perder um
Ctrl, mexer em `/usr/share/X11/xkb/rules/evdev.xml`, e ter que rodar o script de
novo a cada `apt upgrade` do `xkb-data`) não se paga para quem já digita bem em
`us(intl)`.

## O que o XCompose daqui faz

```
include "%L"
<dead_acute> <C> : "Ç" Ccedilla
<dead_acute> <c> : "ç" ccedilla
```

`include "%L"` puxa a tabela padrão do locale inteira — tudo que o sistema já
sabia continua valendo. As duas linhas depois só acrescentam o `ç`, que é o único
caractere do português que o `us(intl)` não dá por acento morto (ele trata a
cedilha como acento próprio, em AltGr+`,`).

O resto do português sai do `us(intl)` sem ajuda: `´` `` ` `` `^` `~` `¨` são
acentos mortos nativos ali.

Recarregar depois de editar: `ibus restart` (ou deslogar).
