# Bateria de periféricos sem fio no painel do GNOME — como montar

Guia para repetir numa segunda máquina o que foi montado em **2026-08-24**. Fork
de [victornoleto/keyboard-mouse-config](https://github.com/victornoleto/keyboard-mouse-config),
adaptado para o mouse **Delux M800 PRO** e depois generalizado para descobrir
sozinho qualquer aparelho com bateria.

O que fica funcionando: um ícone por aparelho na barra do GNOME, com percentual e
`⚡` quando carregando, atualizando em menos de um segundo quando algo conecta ou
desconecta. Clicando, o nome de cada aparelho.

> **Leia a seção [O que NÃO funciona](#o-que-não-funciona) antes de instalar.**
> Metade do valor deste documento está lá: várias coisas que parecem bug são
> limitações medidas, e uma delas é impossível de resolver.

---

## 1. Antes de começar

| requisito | por quê | como conferir |
|---|---|---|
| Ubuntu/GNOME em **X11** | a extensão do painel e o `Alt+F2 r` | `echo $XDG_SESSION_TYPE` → `x11` |
| GNOME Shell **46** | a extensão declara essa versão | `gnome-shell --version` |
| Python 3 | tudo do lado da leitura | `python3 -V` |
| usuário no grupo **plugdev** | acesso a `/dev/hidraw*` sem root | `id -nG \| grep plugdev` |
| `busctl` (systemd) | ler bateria de Bluetooth | `command -v busctl` |
| `gdbus` (glib2) | reagir na hora a conectar/desconectar | `command -v gdbus` |
| `sudo` | **só** para as regras udev | — |

Shell version diferente de 46: edite `panel/battlog@victor/metadata.json` e
acrescente a sua em `shell-version`. Se `gdbus` faltar, tudo funciona — só a
reação a Bluetooth passa a depender do timer de 20 s em vez de ser instantânea.

## 2. Instalar

```bash
git clone <este-repo> keyboard-mouse-config
cd keyboard-mouse-config
git checkout setup-em-casa
./kmctl selftest          # 12 checagens, nenhuma precisa de hardware
```

### ⚠️ O `install.sh` faz DUAS coisas independentes

Ele instala a parte de bateria **e** um layout de teclado ABNT2-em-75% que
**troca o seu layout do GNOME** e sobrescreve o `~/.XCompose`. As duas coisas não
têm relação nenhuma entre si.

**Se você só quer a bateria** (provavelmente o caso), pule o `install.sh` e faça
as quatro etapas dele que importam:

```bash
# 1. regras udev — acesso a hidraw sem root (a única parte com sudo)
sudo install -m644 udev/*.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw

# 2. extensão do painel
mkdir -p ~/.local/share/gnome-shell/extensions
ln -sfnT "$PWD/panel/battlog@victor" \
         ~/.local/share/gnome-shell/extensions/battlog@victor
# idempotente de propósito: `gnome-extensions enable` recusa uuid que o shell
# ainda não varreu, que é o caso numa instalação nova — daí mexer no gsettings
# direto, e checar antes de acrescentar para não duplicar se rodar duas vezes
python3 - <<'PY'
import ast, subprocess
g = ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]
lst = ast.literal_eval(subprocess.check_output(g, text=True).strip().removeprefix("@as "))
if "battlog@victor" in lst:
    print("    já habilitada")
else:
    lst.append("battlog@victor")
    subprocess.run(g[:1] + ["set"] + g[2:] + [str(lst)], check=True)
    print("    habilitada")
PY

# 3. serviço de usuário — é o que mantém tudo em dia
mkdir -p ~/.config/systemd/user
sed "s|@REPO@|$PWD|g" systemd/battlog.service > ~/.config/systemd/user/battlog.service
systemctl --user daemon-reload
systemctl --user enable --now battlog.service

# 4. reiniciar o gnome-shell: Alt+F2, digite "r", Enter
```

O bloco Python do passo 2 parece exagero para "habilitar uma extensão", e não é:
o `gnome-extensions enable` **recusa uuid que o shell ainda não varreu**, que é
exatamente o estado de uma máquina nova. E um `sed` que acrescenta na lista
duplicaria a entrada se você rodar o passo duas vezes. É a mesma lógica que o
`install.sh` usa.

O passo 4 é obrigatório e não tem atalho: o GNOME varre a pasta de extensões
**uma vez, na inicialização**. Sem reiniciar o shell, a extensão não existe para
ele — `gnome-extensions info battlog@victor` diz `doesn't exist` e é normal.

## 3. Validar, camada por camada

```bash
./kmctl scan        # este aparelho vai aparecer? e se não, por quê
./kmctl devices     # o que está aqui com bateria + os módulos
./kmctl battery     # leitura ao vivo
./kmctl status      # exatamente o que o painel lê
systemctl --user status battlog.service
journalctl --user -u battlog.service -f     # acompanhar ao vivo
```

Se o painel mostra `—`, o problema **não é o painel**: é que ninguém escreveu o
cache nos últimos 30 min. Olhe o serviço.

Se um aparelho não aparece, `./kmctl scan` diz em qual dos três caminhos ele caiu
— e o caminho 3 quer dizer que não vai funcionar sem engenharia reversa.

## 4. Como funciona

### Três caminhos para a bateria aparecer

| caminho | sozinho? | cobre |
|---|---|---|
| **Bluetooth** (`bluez_any`) | **sim** | qualquer fone, mouse, teclado ou controle BT cujo firmware reporte bateria |
| **Página de bateria do HID** (`power_supply_any`) | **sim** | quem segue o padrão; inclui Logitech Unifying/Bolt via `hid-logitech-hidpp` |
| **Família conhecida** (`vendor_probe`) | **sim** | a família Delux/TeLink (report `0x0c`), comum em mouse barato — por protocolo, não por modelo |
| **Fabricante novo** (diretório em `devices/`) | **não** | o resto — só sai por opcode que ninguém documentou |

O caminho 3 é comum em periférico de jogo barato. Medido no M800 PRO: **o
descritor HID dele não declara bateria nenhuma**, então o kernel não tem como
saber que existe bateria ali. Só o opcode `0x20` do fabricante sabe. É a razão de
este repo existir.

**Zero configuração é o padrão, não a exceção**: dos quatro caminhos, três não
pedem nada. Escrever um diretório de modelo só é necessário no quarto — ou quando
o aparelho tem caps de escrita (cor, remap, sono) que uma fonte genérica não
alcança.

### Duas coisas em `devices/`

- **módulo de modelo** (`delux_m800pro`): sabe um protocolo proprietário. Declara
  `IDS` + `find()`. Representa **um** aparelho.
- **fonte genérica** (`bluez_any`, `power_supply_any`): sabe um barramento, não um
  modelo. Declara `SOURCE = True` + `discover()`, e devolve **quantos achar**.

Antes de escrever um diretório de modelo, rode `kmctl scan`: se uma fonte já vê o
aparelho, não escreva nada.

### Tempo real

O `kmctl watch` (que é o serviço) relê a cada 20 s **ou** quando um despertador
avisa. Dois despertadores, os dois sem root:

- **udev** por socket netlink, stdlib pura — plugar e desplugar USB;
- **BlueZ** por `gdbus monitor` — conectar e desconectar.

A regra que segura o desenho: **despertador nunca é fonte de dado.** Ele entrega
um bit — "vá olhar de novo" — e quem lê é sempre o caminho normal. Sem isso
haveria um segundo parser de D-Bus para divergir do primeiro; e despertador que
morre degrada para "só o timer" em vez de dar número errado.

O painel **vigia** o arquivo de cache (`Gio.FileMonitor`), não relê por tempo.

**Latências medidas aqui:**

| | |
|---|---|
| desconectar Bluetooth → cache atualizado | **0,05 s** |
| reconectar Bluetooth → cache atualizado | 0,94 s |
| evento de udev → despertador acorda | 2,0 s |

Na desconexão o painel foi atualizado 0,7 s **antes** de o próprio `bluetoothctl`
terminar. A reconexão é mais lenta porque o `Connected: true` chega primeiro e o
`Battery1` só aparece depois, num `InterfacesAdded`.

### Duas cadências, de propósito

O cache é reescrito quando as linhas de aparelho mudam **ou** a cada 5 min
(batimento — é por ele que o painel sabe que o serviço está vivo). O histórico em
sqlite recebe uma amostra a cada 10 min: gravar a cada leitura poria ~4300 linhas
por dia por aparelho sem dizer nada novo.

## 5. O mouse Delux M800 PRO

Se você tem esse mouse, o que importa saber:

- O dongle enumera como **`248a:5b2f`** com strings do OEM — `XCTECH` /
  `Wireless-Receiver`, VID da TeLink. **Procurar "Delux" no `lsusb` não acha
  nada.**
- É **request/response**, não anúncio: `SET_FEATURE` com opcode `0x20` no report
  `0x0c` da interface 1, depois `GET_FEATURE`. Escutar não dá nada — medido: 60 s
  com o mouse em uso pesado deram **12 482 frames** no canal de movimento e
  **zero** no canal de status.
- **Byte 18 = percentual. Byte 19 = estado de carga**, e ele **não é booleano**:
  0 sem cabo, 1 carregando, 2 visto só a 100%.
- Bytes 8..11 são o ASCII **`M802`** — o mouse assina o frame.
- **O percentual não vale enquanto carrega**: ficou 90 min cravado em 64% e depois
  pulou +30 de uma vez. Carregando, não confie no número.
- **O LED de estágio de DPI só pisca quando se troca de estágio.** Isso quase me
  fez concluir que o `kmctl rgb` não funcionava — ele funciona; o efeito é que é
  invisível com o mouse parado. Teste apertando o botão de DPI.
- `kmctl rgb` escreve **os cinco estágios de uma vez** e não existe opcode que
  leia as cores atuais, então não dá para pintar um estágio preservando os outros.
  Para controle real: `kmctl rgb c1,c2,c3,c4,c5`.

Protocolo completo, com o que foi eliminado por teste, em
[`devices/delux_m800pro/PROTOCOL.md`](devices/delux_m800pro/PROTOCOL.md).

## 6. O que NÃO funciona

Tudo aqui foi medido, não suposto.

### Impossível

- **A caixinha de carga de um fone TWS não é detectável.** Com ela no cabo:
  `lsusb` inalterado, zero evento USB em 20 min, `power_supply` vazio, nada no
  UPower, nada no BlueZ. Ela puxa 5 V e não fala com barramento nenhum. Não existe
  canal por onde o número dela chegar, e qualquer percentual mostrado seria
  inventado. **Quem reporta bateria é o fone, não a caixinha** — o `Battery1`
  pendura no objeto do device Bluetooth, e a caixinha não tem endereço.
- **Qual dos dois fones de um par TWS é o percentual.** O BlueZ expõe um número
  só, e o `Battery1` do BlueZ 5.72 não tem a propriedade `Source`. Quem agrega os
  dois é o firmware, antes de mandar.

### Limitação conhecida

- **Duas unidades do mesmo modelo**: só uma aparece. O contrato é
  `find() -> handle | None` e o `find_iface` devolve o primeiro que casa, então a
  segunda fica invisível **em silêncio**. Aparelhos *diferentes* convivem bem.
  Resolver exige um ident estável por unidade, e o serial USB desses receptores
  vem vazio.
- **Categoria de aparelho pode sair errada.** Vem do `Icon` do BlueZ ou do
  `bInterfaceProtocol`; sem nenhum dos dois, vira `other` (ícone de bateria
  genérico).
- **Rótulo de modelo pode sair errado** quando dois modelos da mesma marca
  compartilham o VID:PID do receptor. O nome vem do diretório que reivindicou o
  ID, não do aparelho.

### Não verificado contra hardware

- **`kmctl sleep` e `kmctl key` (remap) do M800 PRO nunca rodaram no mouse.** Os
  pacotes estão travados por assert no selftest contra os literais do driver de
  referência, e o `_send` confere o ACK — mas isso não é o mesmo que ter
  funcionado. **Use `--dry-run` primeiro, e teste `key` num botão que você não
  usa.**
- **Modo cabo do M800 PRO (`248a:5b2e`)**: o driver de referência declara esse
  PID; aqui ele nunca apareceu. Cabo numa porta da máquina carrega o mouse e
  **não enumera nada**. Não sabemos se é o cabo (só de carga), o header do painel
  frontal, ou o firmware.
- **Mouses Attack Shark**: a marca está no repo só como **teclado**
  (`attackshark_k86`). Não há módulo de mouse dela. Os IDs de hidraw dos mouses
  R5 Ultra (`373e:0046/47`) e X11 (`1d57:fa60/fa55`) estão nas regras udev, só
  para a permissão estar pronta, e nenhum foi testado.
- **Byte de bateria do M900Pro é provisório** — foi identificado por descida
  consistente, não pelo salto de recarga que confirmou os outros.

## 7. Diagnóstico

| sintoma | o que olhar |
|---|---|
| painel não aparece | reiniciou o gnome-shell? `gnome-extensions list \| grep battlog` |
| painel mostra `—` | `systemctl --user status battlog.service` — o cache está velho |
| painel vazio, sem ícone | é o comportamento certo quando nada aqui tem bateria |
| aparelho não aparece | `./kmctl scan` diz por quê |
| `sem permissão em /dev/hidrawN` | falta a regra udev, ou você não está em `plugdev` (precisa relogar depois de entrar no grupo) |
| erro de extensão | `journalctl --user -b \| grep -i battlog` |
| serviço reiniciando | `journalctl --user -u battlog.service -n 50` |

Trocar de hardware não pede nada: desplugue um mouse e plugue outro, e se houver
módulo ou fonte que o cubra ele aparece sozinho em segundos. Foi testado ao vivo
trocando o M800 PRO por um receptor `1d57:fa65`.

## 8. Comandos

```bash
./kmctl scan                     # vai aparecer? e se não, por quê
./kmctl devices                  # o que está aqui + módulos e fontes
./kmctl battery                  # leitura ao vivo
./kmctl watch                    # o loop (é o que o serviço roda)
./kmctl probe                    # uma rodada só (alternativa por cron)
./kmctl show                     # timeline do histórico
./kmctl raw                      # quais bytes variaram (achar bateria nova)
./kmctl status                   # o que o painel lê
./kmctl selftest                 # checa o repo, sem hardware
./kmctl --dry-run rgb 00ff80     # monta o pacote e mostra, sem escrever
./kmctl --device <ident> battery  # um aparelho só (ident vem do `devices`)
```

**Use `--dry-run` antes de qualquer comando de escrita.** Ele monta os bytes e
mostra sem abrir o dispositivo.

## 9. Onde está cada coisa

| arquivo | o quê |
|---|---|
| `kmctl` | único executável; não conhece modelo nenhum |
| `devices/__init__.py` | descoberta, transportes (HID e BlueZ), contrato |
| `devices/<modelo>/` | um protocolo proprietário + `PROTOCOL.md` ao lado |
| `devices/bluez_any/`, `devices/power_supply_any/` | as fontes genéricas |
| `battery/__init__.py` | histórico em sqlite, cache do painel, `watch` |
| `wake.py` | despertadores de udev e BlueZ |
| `scan.py` | o diagnóstico do `kmctl scan` |
| `panel/battlog@victor/` | extensão do GNOME |
| `systemd/battlog.service` | o serviço de usuário |
| `udev/*.rules` | acesso a hidraw sem root |

O contrato para acrescentar um periférico está em
[`devices/README.md`](devices/README.md).
