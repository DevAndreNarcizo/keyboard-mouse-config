# keyboard-mouse-config

Configuração de teclado e mouse que eu carrego entre máquinas: um layout
ANSI/ISO 75% que digita como um ABNT2, leitura de bateria dos periféricos sem
fio, um widget de painel com os dois percentuais, e as ferramentas de linha de
comando que sobraram de engenharia reversa.

Ubuntu/GNOME em X11. Python 3 puro — nenhuma dependência fora da stdlib.

## Instalar numa máquina nova

```bash
git clone <este-repo> && cd keyboard-mouse-config
./install.sh          # sem sudo; ele pede sozinho quando precisa
```

Depois reinicie o gnome-shell (`Alt+F2` → `r` → Enter no X11, ou deslogue). O
GNOME lê a lista de layouts e as extensões só na inicialização.

Rode `./install.sh` de novo depois de um `apt upgrade` que mexa no pacote
`xkb-data`: ele reescreve o `/usr/share/X11/xkb/rules/evdev.xml` e apaga a
entrada da variante. O sintoma é o `ª`/`º` parar de funcionar do nada.

## O layout

`layout/victor` herda o `us(intl)` e sobrescreve 5 teclas para fechar as
diferenças que sobravam em relação ao ABNT2 — sem tentar replicar a posição
física das teclas, que num 75% não existe. Só o caractere de saída importa.

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

`layout/XCompose` resolve o resto por sequência: `dead_acute` + `c` = `ç`, e
`dead_circumflex` + espaço = `"` (o padrão seria `^`).

Raciocínio completo, tecla por tecla, em [`layout/ABNT2.md`](layout/ABNT2.md).

## Bateria e controle

Um comando só, `./kmctl`, que não conhece modelo nenhum: ele pergunta ao
`devices/` quem está plugado e oferece o que cada modelo declarar saber fazer.

```bash
./kmctl devices              # modelos suportados, quem está plugado, quem o painel usa
./kmctl battery              # percentual agora
./kmctl probe                # grava uma rodada no histórico (é o que o cron roda)
./kmctl show                 # timeline
./kmctl rgb 00ff80           # cor (nos modelos que fazem)
./kmctl selftest             # checa o repo inteiro, sem precisar de hardware
```

O widget do painel (`panel/battlog@victor/`) não fala com hardware: lê o cache
que o `probe` escreve. Sem cron rodando, ele mostra `—` em vez de um número
velho.

## Adicionar o seu periférico

Copie o diretório do modelo mais parecido em `devices/`, edite, pronto — não há
lista para registrar em lugar nenhum. O contrato (o que declarar, o que
implementar, e como descobrir o byte de bateria de um modelo que ninguém mapeou
ainda) está em [`devices/README.md`](devices/README.md).

| id | modelo | tipo | o que faz |
|---|---|---|---|
| `attackshark_k86` | Attack Shark K86 | teclado | bateria |
| `delux_m900pro` | Delux M900Pro | mouse | bateria |
| `freewolf_f75` | FreeWolf F75 | teclado | bateria, luz, cor por tecla, remap, sono |
| `ajazz_aj139` | AJAZZ AJ139 | mouse | bateria |

Os dois primeiros são o hardware que está na mesa hoje; os dois últimos saíram
em 2026-08-07 e continuam suportados.

## Três conclusões que custaram teste

Valem para quem chegar aqui pelo Google:

- **Cor/RGB do K86 não funciona por 2.4G, e não é limitação de software.** O
  dongle responde *todo* opcode com um frame de status dele mesmo e nunca
  repassa nada pelo rádio — o teclado nem fica sabendo que alguém perguntou. Por
  cabo funciona, e aí o [sharkfin](https://github.com/dniminenn/sharkfin) já faz
  tudo; não vale reescrever. Teste de um pacote para saber com quem você está
  falando: por cabo a resposta **ecoa o opcode no byte 0**, pelo dongle nunca ecoa.
- **A bateria vem justamente daquele frame morto** — byte 1 é o percentual. Não
  há flag de carga confiável ali: o byte 3, que parecia ser uma, oscila 0/1 sem
  cabo nenhum.
- **Com o teclado no carregador, o número do dongle não vale.** Ele republica o
  valor anterior — ficou 5h30 cravado em 81% e depois voltou a marcar os 30% de
  antes da carga, com a bateria cheia. Corrigiu sozinho 2 min depois de o cabo
  sair. Carregando, a fonte certa é a tela do teclado. Detalhes e a medição em
  [`devices/attackshark_k86/PROTOCOL.md`](devices/attackshark_k86/PROTOCOL.md).

Os binários do fabricante (instalador Windows, `.dll`, firmware, manual
escaneado) que serviram de referência para essa engenharia reversa **não estão
no repo** de propósito: são proprietários.
