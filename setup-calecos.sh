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
[ "${XDG_SESSION_TYPE:-}" = wayland ] \
  && echo "    sessão Wayland — reiniciar o shell aqui é deslogar (Alt+F2 r é só X11)" \
  || echo "    sessão ${XDG_SESSION_TYPE:-desconhecida} — este script foi escrito para Wayland, siga em frente com atenção"
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

if command -v gsettings >/dev/null && [ -n "${XDG_CURRENT_DESKTOP:-}" ]; then
  echo "==> input sources do GNOME"
  # Fixado explicitamente para o setup ser reproduzível numa máquina nova. Nesta
  # aqui é no-op: já era us+intl.
  ATUAL=$(gsettings get org.gnome.desktop.input-sources sources)
  ALVO="[('xkb', 'us+intl')]"
  if [ "$ATUAL" = "$ALVO" ]; then
    echo "    já é us(intl), nada a fazer"
  else
    echo "    era $ATUAL"
    gsettings set org.gnome.desktop.input-sources sources "$ALVO"
    echo "    agora é $ALVO"
  fi

  echo "==> extensão do painel"
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
    print("    já habilitada")
else:
    lst.append("battlog@victor")
    subprocess.run(g[:1] + ["set"] + g[2:] + [str(lst)], check=True)
    print("    habilitada (aparece depois que o shell reiniciar)")
EXTPY
else
  echo "==> GNOME não detectado, pulando gsettings"
fi

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

A extensão do painel só existe para o shell depois que ele reiniciar, e nesta
máquina **isso quer dizer deslogar e logar** — `Alt+F2` → `r` é de X11 e não
existe em Wayland. Depois do próximo login, quem confirma que ela subiu:

  gnome-extensions info battlog@victor
  journalctl --user -b | grep -i battlog

Se o painel mostrar "—", o problema não é o painel: é que ninguém escreveu o
cache nos últimos 30 min. Olhe o serviço:

  systemctl --user status battlog.service
  journalctl --user -u battlog.service -f

Nenhum aparelho na lista acima? `./kmctl scan` diz em qual dos quatro caminhos
cada um caiu. Caindo no 4, só sai por engenharia reversa — e a ferramenta para
isso é `./kmctl raw`, que mostra quais bytes se mexem.
EOF
