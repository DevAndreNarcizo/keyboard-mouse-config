# keyboard-mouse-config

Configuração de teclado e mouse que eu carrego entre máquinas: um layout
ANSI/ISO 75% que digita como um ABNT2, leitura de bateria dos periféricos sem
fio, um widget de painel com os percentuais, e as ferramentas de linha de
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
./kmctl devices              # o que está aqui com bateria, e os módulos
./kmctl scan                 # este aparelho vai aparecer? e se não, por quê
./kmctl battery              # percentual agora
./kmctl probe                # grava uma rodada no histórico (uma vez só)
./kmctl watch                # fica lendo e atualizando o painel (é o serviço)
./kmctl show                 # timeline
./kmctl rgb 00ff80           # cor (nos modelos que fazem)
./kmctl selftest             # checa o repo inteiro, sem precisar de hardware
```

## Tempo real

Quem alimenta o painel é o `battlog.service` (unidade **de usuário**, o
`install.sh` habilita), rodando `kmctl watch`. Duas cadências de propósito:

- **cache do painel**: reescrito assim que algum número muda. E o painel *vigia*
  o arquivo, então aparece na hora — não há polling do lado da extensão.
- **histórico**: uma amostra a cada 10 min. Gravar a cada leitura poria ~4300
  linhas por dia por aparelho no banco sem dizer nada novo.

Presença é instantânea: o `watch` escuta **udev** (socket netlink, stdlib pura) e
o **BlueZ** (`gdbus monitor`), então conectar ou desconectar um fone aparece em
menos de um segundo. Medido: 2,0 s do `udevadm trigger` até o despertador acordar.

O princípio que evita a gambiarra: **despertador nunca é fonte de dado.** Ele
entrega um bit — "vai olhar de novo" — e quem lê é sempre `present()` +
`battery()`. Assim não há um segundo parser de D-Bus para manter em sincronia, e
despertador que morre degrada para "só o timer" em vez de dar número errado.

**Percentual não fica mais rápido que o aparelho o reporta.** O fone manda
bateria de vez em quando pelo próprio rádio; o mouse muda 1% a cada muitos
minutos. Reler mais vezes não cria informação que ninguém mandou — e é por isso
que o `--interval` é 20 s e não 1 s.

O widget do painel (`panel/battlog@victor/`) não fala com hardware: lê o cache
que o `watch` escreve. **Um slot por aparelho**, com `⚡` quando carregando, e a
lista vem do arquivo — aparelho novo não pede mexer em JS.

Três estados, e a diferença entre os dois últimos é de propósito:

- aparelhos presentes → um slot para cada;
- nada com bateria aqui → **o widget some**. Ausência significando ausência;
- serviço parado (ou cache com mais de 30 min) → um `—`. Aí o problema é quem
  escreve, e esconder isso esconderia a falha.

## Funciona com o meu aparelho?

Rode `./kmctl scan` com ele ligado. A resposta é **depende da marca**, e o scan
diz em qual dos três caminhos o seu caiu:

| caminho | sozinho? | cobre |
|---|---|---|
| **Bluetooth** (`bluez_any`) | **sim** | qualquer fone, mouse, teclado ou controle BT cujo firmware reporte bateria — a maioria dos modernos |
| **Página de bateria do HID** (`power_supply_any`) | **sim** | quem segue o padrão: o kernel cria a entrada em `/sys/class/power_supply`. Inclui Logitech Unifying/Bolt, que o `hid-logitech-hidpp` já expõe |
| **Família de fabricante conhecida** (`vendor_probe`) | **sim** | hoje a família Delux/TeLink (report `0x0c`), comum em mouse sem fio barato. É por **protocolo**, não por modelo |
| **Protocolo de fabricante novo** | **não** | o resto: a bateria só sai por opcode que ninguém documentou. Precisa de um diretório em `devices/` |

**Attack Shark**: a marca está aqui, mas só como **teclado** (`attackshark_k86`).
Não há módulo de mouse dela. Os IDs de hidraw dos mouses R5 Ultra (`373e:0046/47`)
e X11 (`1d57:fa60/fa55`) já entraram nas regras udev — só a permissão, sem módulo
— porque a regra de VID `1d57` prendia o PID do receptor Delux e não os cobriria.
Nenhum foi testado aqui.

O terceiro caminho é o que mais aproxima do "só conectar": a sonda não conhece
modelo, conhece **protocolo**, então qualquer aparelho da família aparece com o
modelo lido do próprio frame. Ela **escreve** em aparelho desconhecido, então só
existe para família cuja resposta se identifica — a do K86 valida apenas
`1 <= byte[1] <= 100`, sem assinatura, e sondá-la daria número para qualquer
coisa. Está deliberadamente fora, e o motivo está em
[`devices/vendor_probe/`](devices/vendor_probe/__init__.py).

O último caso não é raro em periférico de jogo barato — é onde caem o Delux
M800 PRO e o Attack Shark K86 daqui, e é a razão de este repo existir. Medido no
M800 PRO: o descritor HID dele **não declara bateria nenhuma**, então o kernel não
tem como saber que existe bateria ali. Só o opcode `0x20` do fabricante sabe.

`kmctl scan` distingue os três e diz, para o que não aparece, se é candidato a
diretório (tem canal de fabricante) ou se não há por onde (não expõe bateria em
lugar nenhum — com fio, ou sem bateria).

## Adicionar o seu periférico

**Talvez não precise.** Desde 2026-08-24 há duas fontes genéricas que descobrem
sozinhas: `bluez_any` (qualquer aparelho Bluetooth conectado que reporte bateria)
e `power_supply_any` (qualquer periférico que o kernel já exponha em
`/sys/class/power_supply`, o que cobre quem fala a página de bateria padrão do
HID). Ligue e veja no `./kmctl devices`.

Diretório de modelo só se justifica quando **nenhuma fonte genérica vê o
aparelho** — é o caso do Delux M800 PRO e do Attack Shark K86, cuja bateria só
sai por opcode de fabricante e que não aparecem no UPower nem no `power_supply`.
É essa lacuna que dá razão ao repo existir. O outro motivo válido é ter algo a
declarar que o barramento não sabe: um `WONT` explicando por que aquele modelo
não faz RGB, ou caps de controle.

Nesse caso, copie o diretório do modelo mais parecido em `devices/`, edite,
pronto — não há lista para registrar em lugar nenhum. O contrato (os dois tipos
de módulo, o que declarar, e como descobrir o byte de bateria de um modelo que
ninguém mapeou ainda) está em [`devices/README.md`](devices/README.md).

| id | modelo | tipo | o que faz |
|---|---|---|---|
| `attackshark_k86` | Attack Shark K86 | teclado | bateria |
| `delux_m800pro` | Delux M800 PRO | mouse | bateria, cor dos estágios de DPI, remap de botão, sono |
| `delux_m900pro` | Delux M900Pro | mouse | bateria |
| `freewolf_f75` | FreeWolf F75 | teclado | bateria, luz, cor por tecla, remap, sono |
| `ajazz_aj139` | AJAZZ AJ139 | mouse | bateria |
| `bluez_any` | *(fonte)* qualquer Bluetooth com bateria | — | bateria |
| `power_supply_any` | *(fonte)* qualquer um em `/sys/class/power_supply` | — | bateria |

O K86 e o M900Pro são o hardware da mesa original; o M800 PRO entrou em
2026-08-24 noutra máquina; o F75 e o AJ139 saíram em 2026-08-07 e continuam
suportados.

As duas **fontes** entraram em 2026-08-24, junto com o primeiro aparelho não-HID
(um fone Bluetooth): quem lê a bateria dele é o BlueZ, não este repo. Isso
acrescentou a categoria `headset` e um segundo transporte.

O fone chegou a ter um diretório de modelo, e ele **foi removido no mesmo dia**:
lia o mesmo aparelho pelo mesmo caminho que a fonte genérica, e manter os dois
obrigou a inventar dedução só para ele não aparecer duas vezes. Máquina para
reconciliar duas cópias da mesma coisa é o sinal de que uma das cópias não
devia existir.

O M800 PRO foi o primeiro **mouse** com caps de controle, e isso obrigou a
mudar o despacho do `kmctl`: `kmctl rgb`/`sleep`/`key` escolhiam sempre um
teclado, porque no começo só o teclado tinha o que controlar. Agora quem opera é
quem está plugado **e declara a cap** — e se mais de um declarar, o `kmctl` pede
`--device` em vez de escolher sozinho.

## Três conclusões que custaram teste

Valem para quem chegar aqui pelo Google:

- **Nem todo receptor se anuncia — e "mudo" e "parado" são coisas diferentes.**
  O M900Pro fala sozinho e o `battery()` dele escuta; o M800 PRO nunca fala, e
  só responde a um `SET_FEATURE` seguido de `GET_FEATURE`. Descobrir isso exigiu
  provar que o canal estava mudo *com o mouse em uso*: 60 s de captura deram
  **12482** frames no canal de movimento e **zero** no canal de status. Sem essa
  testemunha, o silêncio parece mouse parado, e o `GET_FEATURE` solto devolvendo
  zeros parece o dongle morto do K86. Não era nem um nem outro.
- **Carregar não é o mesmo que ser visível, e não há contorno.** A caixinha do
  fone JBL, no cabo, não aparece em lugar nenhum: `lsusb` inalterado, zero evento
  USB, `/sys/class/power_supply` vazio, nada no UPower, nada no BlueZ. Ela puxa
  5V e não fala com barramento nenhum — igualzinho ao cabo do M800 PRO, que
  carrega o mouse e também não enumera. Aparelho que não se anuncia não é
  detectável, e qualquer percentual mostrado para ele seria inventado. Vale
  saber antes de procurar o bug que não existe.
- **"Não teve efeito" pode ser o efeito estando invisível.** A primeira escrita
  de cor no M800 PRO pareceu falhar: comando aceito, ACK no protocolo, nada na
  mesa. A explicação pronta era a do K86 logo abaixo — dongle aceita e não
  repassa. Errado: o LED de estágio de DPI daquele mouse **só pisca quando se
  troca de estágio**. Apertando o botão de DPI, estava vermelho. Antes de
  concluir que um comando não chegou, ache o jeito de fazer o efeito aparecer.
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
