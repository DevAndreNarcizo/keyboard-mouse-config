#!/usr/bin/env bash
# Setup da máquina `calecos` — GNOME 50.1 em Wayland.
#
# É o irmão do `install.sh`, e existe porque o `install.sh` faz DUAS coisas: a
# bateria dos periféricos E a camada de teclado do victor, que sobrescreve o
# ~/.XCompose e troca o layout do GNOME. Aqui a camada de teclado é outra (ver
# `layout/calecos/README.md`), então rodar o `install.sh` nesta máquina desfaria
# o arranjo em vez de montá-lo.
#
# Rodar SEM sudo — ele pede sozinho nas linhas que precisam.
# Idempotente: pode rodar de novo à vontade.
#
# Uma assimetria de propósito: para o ~/.XCompose **a cópia do repo é a que
# manda**. Editou o arquivo em casa e rodou o script de novo? Ele salva o que
# estava em ~/.XCompose.bak-<data> e põe a versão do repo no lugar. Quem quiser
# mudar o Compose muda em `layout/calecos/XCompose` e commita — senão a mudança
# se perde na próxima vez que este script rodar.
#
# O que ele NÃO faz, cada um por um motivo:
#   - não instala variante XKB nem mexe no evdev.xml (aqui é us(intl) de fábrica)
#   - não liga o Bluetooth: está desligado por escolha, e o caminho `bluez_any`
#     fica inativo por consequência. Quem quiser: sudo systemctl enable --now bluetooth
#   - não mexe em cron: quem alimenta o painel é o battlog.service
set -euo pipefail
cd "$(dirname "$(realpath "$0")")"

# Sem tty, `sudo` não tem como pedir a senha nem gravar o timestamp — é o caso
# quando o script roda de dentro de um agente ou de um pipeline. Aí SUDO_ASKPASS
# aponta para um helper e o `-A` o usa. No uso normal, num terminal, a variável
# não existe e isto vira o `sudo` de sempre.
# `if` e não `[ ... ] && ...`: sob `set -e` a forma curta derruba o script quando
# o teste dá falso, que é justamente o caso comum (rodando num terminal).
SUDO=(sudo)
if [ -n "${SUDO_ASKPASS:-}" ]; then
  SUDO=(sudo -A)
fi

echo "==> conferindo o terreno"
echo "    sessão: ${XDG_CURRENT_DESKTOP:-?} / ${XDG_SESSION_TYPE:-?}"
id -nG | tr ' ' '\n' | grep -qx plugdev \
  && echo "    no grupo plugdev: ok" \
  || echo "    !! FORA do grupo plugdev — as regras udev não bastam. sudo usermod -aG plugdev $USER, e relogar"

echo "==> Compose (~/.XCompose)"
# O victor sobrescreve sem perguntar; aqui não. O arquivo desta máquina é o que
# está versionado, então o caso normal é `cmp` dar igual e nada acontecer.
if [ -e "$HOME/.XCompose" ] && ! cmp -s layout/calecos/XCompose "$HOME/.XCompose"; then
  cp "$HOME/.XCompose" "$HOME/.XCompose.bak-$(date +%Y%m%d%H%M%S)"
  echo "    o que existia foi salvo em ~/.XCompose.bak-*"
fi
install -m644 layout/calecos/XCompose "$HOME/.XCompose"
echo "    ç por acento agudo; o resto do português o us(intl) já dá"

echo "==> regras udev (hidraw sem root)"
# É o ÚNICO pedaço com sudo. Sem ele /dev/hidraw* fica 0600 root e o `kmctl scan`
# responde "não expõe bateria" para tudo — resposta que não distingue "não tem"
# de "não pude olhar".
"${SUDO[@]}" install -m644 udev/*.rules /etc/udev/rules.d/
"${SUDO[@]}" udevadm control --reload-rules
"${SUDO[@]}" udevadm trigger --subsystem-match=hidraw
echo "    $(ls /etc/udev/rules.d/*.rules 2>/dev/null | wc -l) arquivos de regra em /etc/udev/rules.d/"

# ---------------------------------------------------------------------------
# DUAS SESSÕES, e por isso o gate é pelo que está INSTALADO, não pelo que está
# rodando. O login desta máquina oferece `ubuntu.desktop` (GNOME) e três
# `hyprland*.desktop`; rodar este script de dentro de uma sessão e configurar só
# ela deixaria a outra quebrada até alguém rodar de novo lá dentro. Cada frente
# instala a sua parte, e quem escolhe é a sessão em que se loga.
# ---------------------------------------------------------------------------

if command -v gnome-shell >/dev/null; then
  echo "==> GNOME (instalado)"

  # Só faz sentido no GNOME; no Hyprland o layout vem do `input {}` do hyprland.
  ATUAL=$(gsettings get org.gnome.desktop.input-sources sources 2>/dev/null || echo "")
  ALVO="[('xkb', 'us+intl')]"
  if [ "$ATUAL" = "$ALVO" ]; then
    echo "    input sources: já é us(intl)"
  elif [ -n "$ATUAL" ]; then
    gsettings set org.gnome.desktop.input-sources sources "$ALVO"
    echo "    input sources: $ATUAL -> $ALVO"
  fi

  EXT="$HOME/.local/share/gnome-shell/extensions/battlog@victor"
  mkdir -p "$(dirname "$EXT")"
  ln -sfnT "$PWD/panel/battlog@victor" "$EXT"
  # `gnome-extensions enable` recusa uuid que o shell ainda não varreu (é o caso
  # numa instalação nova), então mexe direto no gsettings — mesma chave.
  python3 - <<'EXTPY'
import ast, subprocess
g = ["gsettings", "get", "org.gnome.shell", "enabled-extensions"]
lst = ast.literal_eval(subprocess.check_output(g, text=True).strip().removeprefix("@as "))
if "battlog@victor" in lst:
    print("    extensão do painel: já habilitada")
else:
    lst.append("battlog@victor")
    subprocess.run(g[:1] + ["set"] + g[2:] + [str(lst)], check=True)
    print("    extensão do painel: habilitada")
EXTPY
else
  echo "==> GNOME não instalado, pulando a extensão do painel"
fi

if command -v Hyprland >/dev/null && command -v qs >/dev/null; then
  echo "==> Hyprland (instalado)"

  # A barra do Hyprland é outro programa: aqui, quickshell. O widget é um config
  # SEPARADO, ao lado do `ii` do dots-hyprland — editar o `ii` seria mexer em
  # código de terceiro que a próxima atualização dele sobrescreve sem avisar.
  EXECS="$HOME/.config/hypr/custom/execs.conf"
  LINHA="exec-once = qs -p $PWD/panel/quickshell/battlog.qml"
  if [ ! -f "$EXECS" ]; then
    echo "    !! $EXECS não existe — o widget não vai subir sozinho."
    echo "       Acrescente à mão:  $LINHA"
  elif grep -qF "battlog.qml" "$EXECS"; then
    echo "    autostart: já está em custom/execs.conf"
  else
    cp "$EXECS" "$EXECS.bak-$(date +%Y%m%d%H%M%S)"
    {
      echo ""
      echo "# --- battlog: bateria dos periféricos ---"
      echo "$LINHA"
    } >> "$EXECS"
    echo "    autostart: acrescentado (backup em execs.conf.bak-*)"
  fi

  # NÃO reescreve o input{} do usuário: só confere que os dois lados concordam.
  # Se o GNOME está em us+intl e o Hyprland em outra coisa, trocar de sessão
  # trocaria o teclado por baixo do dono — e isso ele tem que decidir, não eu.
  HGEN="$HOME/.config/hypr/custom/general.conf"
  if [ -f "$HGEN" ] && grep -q "kb_layout *= *us" "$HGEN" && grep -q "kb_variant *= *intl" "$HGEN"; then
    echo "    teclado: kb_layout=us kb_variant=intl — bate com o GNOME"
  else
    echo "    teclado: NÃO confirmado como us/intl em custom/general.conf."
    echo "       As duas sessões podem estar com layouts diferentes. Para igualar:"
    echo "       input { kb_layout = us  kb_variant = intl }"
  fi
else
  echo "==> Hyprland não instalado, pulando o widget do quickshell"
fi

echo "==> comando \`r\` (recarregar a interface)"
# Vai em /usr/local/bin e não em ~/.local/bin de propósito: o ~/.local/bin está
# no PATH do shell mas NÃO no da sessão, e é o da sessão que o diálogo do
# Alt+F2 enxerga. Conferido com `systemctl --user show-environment`.
#
# Instalado SEMPRE: ele decide em tempo de execução em qual compositor está.
"${SUDO[@]}" install -m755 panel/reload-shell /usr/local/bin/r
echo "    GNOME: recarrega a extensão | Hyprland: hyprctl reload"

echo "==> serviço de usuário (bateria em tempo real)"
UNIT="$HOME/.config/systemd/user/battlog.service"
mkdir -p "$(dirname "$UNIT")"
sed "s|@REPO@|$PWD|g" systemd/battlog.service > "$UNIT"
systemctl --user daemon-reload
systemctl --user enable --now battlog.service
# `restart` e não só `enable --now`: rodar o script de novo depois de mexer no
# Python deixaria o serviço com o código velho em memória, que é um sintoma
# chato de diagnosticar (o `kmctl battery` acha e o painel não mostra).
systemctl --user restart battlog.service
echo "    battlog.service: $(systemctl --user is-active battlog.service)"

echo "==> o que apareceu"
./kmctl scan || true

cat <<'EOF'

pronto.

A extensão do painel sobe sozinha: na 50.1 o shell monitora a pasta e a pega no
instante em que o symlink aparece. Confira:

  gnome-extensions info battlog@victor     # State: ACTIVE
  journalctl --user -b | grep -i battlog   # deve sair vazio

DUAS SESSÕES: o que aparece depende de onde você loga.

  GNOME     -> extensão do painel (panel/battlog@victor)
  Hyprland  -> widget do quickshell, canto superior direito
               (panel/quickshell/battlog.qml, subindo por custom/execs.conf)

O dado é o mesmo nos dois: o battlog.service escreve ~/.cache/battlog-status e
cada frente só desenha. Trocar de sessão não pede nada.

`Alt+F2` → `r` → Enter funciona nas duas, fazendo o que cabe em cada uma: em
X11 o atalho reiniciava o shell, e em Wayland isso é impossível (o shell é o
compositor). O /usr/local/bin/r decide em tempo de execução:

  no GNOME     recarrega UMA extensão (padrão battlog@victor)
  no Hyprland  hyprctl reload

Nenhum dos dois alcança o código do próprio compositor. Para isso, deslogar.

Se o painel mostrar "—", o problema não é o painel: é que ninguém escreveu o
cache nos últimos 30 min. Olhe o serviço:

  systemctl --user status battlog.service
  journalctl --user -u battlog.service -f

Nenhum aparelho na lista acima? `./kmctl scan` diz em qual dos quatro caminhos
cada um caiu. Caindo no 4, só sai por engenharia reversa — e a ferramenta para
isso é `./kmctl raw`, que mostra quais bytes se mexem.
EOF
