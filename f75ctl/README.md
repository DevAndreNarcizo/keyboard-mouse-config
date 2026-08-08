# f75ctl

Controle do teclado **FreeWolf F75** no Linux. Python 3 puro (stdlib), um arquivo.
Protocolo em [PROTOCOL.md](PROTOCOL.md).

## Instalação

```bash
sudo install -m644 99-freewolf-f75.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --subsystem-match=hidraw
```

Sem a regra udev o `/dev/hidraw*` é só root.

## Uso

```bash
./f75ctl.py status                 # bateria e estado
./f75ctl.py modes                  # lista os 22 modos de iluminação
./f75ctl.py light --mode 7         # luz estática (--brightness 1..5, --speed 1..5,
                                   #   --direction 0|1, --color <índice da paleta>)
./f75ctl.py rgb 00ff80             # cor RGB arbitrária no teclado todo
./f75ctl.py rgb 0000ff --only esc  # acende só o Esc, resto apagado
./f75ctl.py off                    # apaga as teclas (a strip continua)
./f75ctl.py key z printscreen      # Fn+Z passa a ser Print Screen
./f75ctl.py key f5 home --layer base   # remap na camada normal
./f75ctl.py sleep never            # 2min | 15min | 30min | never
./f75ctl.py raw 0d 02              # tempo de resposta das teclas (1, 2 ou 3)
./f75ctl.py listen --seconds 20    # observa o canal vendor
./f75ctl.py raw 0e                 # envia um comando cru (experimentos)
```

`rgb` usa o modo custom por tecla — é o único caminho para cor exata; o `light
--color` usa a paleta fixa do firmware.

**`rgb 000000` não apaga nada**: preto é transparente no stream de frames, o
firmware lê como "não mexe nesta tecla". Por isso existe o `off`, que manda
`010101` (invisível). Foi essa pegadinha que fez dois testes parecerem "comando
ignorado" (ver PROTOCOL.md).

## Economizar bateria com indicador de ligado

O que funciona, e sobrevive ao sono (medido):

```bash
./f75ctl.py off      # teclas escuras; a strip lateral fica acesa
```

O `off` **não desliga o LED** — manda `010101` com brilho 1, que é o mínimo que o
protocolo alcança (PWM ~0,4% do valor × brilho 1). Não existe apagar de verdade
por software: ver a seção "Apagar o LED não existe no protocolo" do PROTOCOL.md.
Off real é só o Fn+X, e ele leva a strip junto — é o preço do indicador.

A strip é firmware, apaga junto quando o teclado dorme e volta com uma tecla —
ou seja, **strip acesa = ligado, tudo escuro = dormindo**, sem custo de bateria
nas 80 teclas. Se quiser um indicador nas teclas em vez da strip, `rgb 0000ff
--only esc` faz o mesmo com uma tecla só.

Não use o Fn+X para isso: ele apaga a strip também, então "tudo escuro" deixaria
de significar "dormindo". Com o `off` o Fn+X sai da rotina.

Para a strip gastar o mínimo: **Fn+↓** baixa a intensidade dela (o brilho do
nosso `0x07` não a alcança) e **vermelho** é a cor de menor consumo — LED
vermelho tem tensão direta ~1/3 menor que verde/azul, e branco acenderia os três
dies. Esses ajustes são só no teclado (Fn+↓ e Fn+A/Fn+Caps) e sobrevivem aos
nossos pacotes.

`key` aceita nomes (`printscreen`, `home`, `f5`, `delete`…), letras/dígitos, ou
`0xNN` direto. O remap é gravado no teclado na hora e é aditivo: para desfazer
uma tecla, remapeie ela para si mesma (`./f75ctl.py key v v`).
**`raw 0f` apaga o keymap inteiro** — é o reset, não um commit.

## Estado

Funciona: status/bateria, os 22 modos de iluminação com brilho/velocidade/direção,
cor RGB arbitrária, remap de tecla nas camadas normal e Fn, tempo de sono e tempo
de resposta das teclas.

Não implementado: macros com *sequência* de teclas e delays (caminho mapeado no
PROTOCOL.md — stream `0x00`–`0x02`).

Não é possível: controlar a strip lateral (firmware-only, só por Fn+Caps Lock —
ver PROTOCOL.md para o que foi testado). Também não há como *ler* a configuração
atual do teclado; o protocolo é só de escrita, fora o status de bateria.

Funções de fábrica da camada Fn (Fn+X apaga o backlight, Fn+Caps Lock troca o
modo da strip) continuam valendo e não aparecem no protocolo.

Cuidado com o sono: quando o tempo estoura, o backlight apaga e **só volta com
Fn+X** — nem tecla nem reenviar a cor religam (o teclado segue acordado e
digitando; é só a luz). Se isso incomodar, use `sleep never`.

A cor arbitrária (`rgb`) vive na RAM e **se perde no sono profundo** (uma noite
desligado): o teclado acorda apagado e volta parcial. Basta rodar o `rgb` de
novo. O remap de tecla, ao contrário, fica gravado no flash e sobrevive.

A strip lateral se ajusta pelo próprio teclado: **Fn+Caps** troca o modo e
**Fn+A** a cor (é assim que se deixa ela azul). Depois de usar qualquer combo Fn
de luz, reenvie a cor com `rgb` — o firmware reassume o backlight e derruba o
modo custom. A lista completa de atalhos está no PROTOCOL.md.

## Diretórios

- `key-slots.json` — código HID → `key_index` no frame de cores, 105 teclas.
  Extraído do `layouts/kb-k600t.xml` do app Windows do fabricante; **só a tabela
  derivada mora aqui**, o XML original é proprietário e não vai no repo. É por
  isso que os `PROTOCOL.md` citam caminhos em `reference/` que você não vai achar:
  eram os arquivos do app extraído, usados na engenharia reversa.
- A regra udev do F75 está em `../udev/99-freewolf-f75.rules`.

Para extrair o instalador de novo é preciso o `innoextract` do git master
(o release 1.9 não lê Inno Setup 6.3):

```bash
docker run --rm -v "$PWD:/out" -v "<dir do exe>:/in:ro" alpine sh -c \
  "apk add -q build-base cmake boost-dev boost-static xz-dev git && \
   git clone -q --depth 1 https://github.com/dscharrer/innoextract /src && \
   cd /src && cmake -DCMAKE_BUILD_TYPE=Release . >/dev/null && make -j\$(nproc) && \
   ./innoextract -e -d /out '/in/FREE  WOLF  F75 setup 1.0.4.4.exe'"
```

`tap.py [segundos]` mostra os reports HID de entrada do teclado — foi assim que o
remap do Fn+Z foi verificado objetivamente (`[2]=0x46` = Print Screen no fio),
sem depender de olhar a tela.
