# keyboard-config

Configuração de teclado que eu carrego entre máquinas: um layout ANSI/ISO 75%
que digita como um ABNT2, mais as ferramentas de linha de comando que sobraram de
engenharia reversa em dois teclados sem-fio.

Ubuntu/GNOME em X11.

## Instalar numa máquina nova

```bash
git clone <este-repo> && cd keyboard-config
./install.sh          # sem sudo; ele pede sozinho quando precisa
```

Depois reinicie o gnome-shell (`Alt+F2` → `r` → Enter no X11, ou deslogue). O
GNOME lê a lista de layouts só na inicialização, então a variante nova não aparece
antes disso.

Rode `./install.sh` de novo depois de um `apt upgrade` que mexa no pacote
`xkb-data`: ele reescreve o `/usr/share/X11/xkb/rules/evdev.xml` e apaga a entrada
da variante. O sintoma é o `ª`/`º` parar de funcionar do nada.

## O que é o layout

`xkb/victor` herda o `us(intl)` e sobrescreve 5 teclas para fechar as diferenças
que sobravam em relação ao ABNT2 — sem tentar replicar a posição física das teclas,
que num 75% não existe. Só o caractere de saída importa.

| Tecla | Base | Shift | AltGr | AltGr+Shift |
|---|---|---|---|---|
| `'` | `dead_acute` | `dead_circumflex` | `'` | `"` |
| `1` | `1` | `!` | `¹` | `¡` |
| Ctrl direito | *(vira AltGr)* | — | — | — |
| `A` | `a` | `A` | `ª` | `Á` |
| `O` | `o` | `O` | `º` | `Ó` |

O Ctrl direito virar `ISO_Level3_Shift` é o pulo do gato: dá um **AltGr de
verdade** (segura + qualquer tecla) num teclado que não tem AltGr físico, em vez
de atalhos fixos por tecla. Custo: o Ctrl direito deixa de ser Ctrl.

`xkb/XCompose` resolve o resto por sequência: `dead_acute` + `c` = `ç`, e
`dead_circumflex` + espaço = `"` (o padrão seria `^`).

Raciocínio completo, tecla por tecla, em [`docs/abnt2-layout.md`](docs/abnt2-layout.md).

## O que tem aqui

| | |
|---|---|
| `install.sh` | instala tudo numa máquina nova |
| `xkb/` | a variante XKB e o `.XCompose` — o coração do repo |
| `udev/` | regras de acesso hidraw sem root |
| `MAP.md` | estado vivo: o que está ativo em cada camada e onde mora |
| `battlog/` | log de bateria dos periféricos em SQLite (stdlib) |
| `f75ctl/` | CLI do FreeWolf F75 + protocolo documentado |
| `docs/` | o levantamento ABNT2 e o histórico dos experimentos de remap |

## Hardware

Atual: teclado **Attack Shark K86** (dongle ROYUAN `3151:4011`, cabo `3151:4015`) e
mouse **Delux M900Pro** (receptor `1d57:fa65`).

Duas conclusões que custaram teste e valem para quem chegar aqui pelo Google:

- **Cor/RGB do K86 não funciona por 2.4G, e não é limitação de software.** O dongle
  responde *todo* opcode com um frame de status dele mesmo e nunca repassa nada
  pelo rádio — o teclado nem fica sabendo que alguém perguntou. Por cabo funciona, e
  aí o [sharkfin](https://github.com/dniminenn/sharkfin) já faz tudo; não vale
  reescrever. Teste de um pacote para saber com quem você está falando: por cabo a
  resposta **ecoa o opcode no byte 0**, pelo dongle nunca ecoa.
- **A bateria vem justamente daquele frame morto** — byte 1 é o percentual, byte 3 é
  a flag de carregando. É o "outro canal" que o software do fabricante usa. Detalhes
  e o método em [`battlog/README.md`](battlog/README.md).

Anterior: **FreeWolf F75** (`1a2c:8fff`). O `f75ctl/` controla iluminação, cor por
tecla, remap e tempo de sono dele, com o protocolo documentado em
[`f75ctl/PROTOCOL.md`](f75ctl/PROTOCOL.md) — dialeto próprio, sync `AA 55 CC 33`.

Os binários do fabricante (instalador Windows, `.dll`, firmware, manual escaneado)
que serviram de referência para essa engenharia reversa **não estão no repo** de
propósito: são proprietários.
