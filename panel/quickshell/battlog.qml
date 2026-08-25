//@ pragma UseQApplication

// battlog para Hyprland (ou qualquer compositor com layer-shell).
//
// POR QUE ISTO EXISTE, EM VEZ DE MEXER NA BARRA QUE JÁ HÁ
//
// A extensão do GNOME (`panel/battlog@victor/`) só existe dentro do gnome-shell.
// No Hyprland a barra é outro programa — aqui, o quickshell com o config `ii` do
// dots-hyprland. Mexer no `ii` seria editar código de terceiro que é
// sobrescrito a cada atualização dele, e a mudança se perderia sem aviso.
//
// Então isto é um config quickshell **separado**, que roda ao lado:
//
//     qs -p /caminho/para/panel/quickshell/battlog.qml
//
// Mesma divisão do resto do repo: quem lê hardware é o `kmctl watch`; aqui só
// se desenha o que ele escreveu. Este arquivo NÃO abre hidraw nem sqlite — ele
// executa `kmctl bar --json --follow`, que fica de pé e emite uma linha nova a
// cada mudança. Por isso o número aparece na hora, sem reler por tempo.
//
// Três estados, os mesmos da extensão do GNOME de propósito — as duas telas
// discordarem sobre "o serviço morreu" seria pior que uma delas não existir:
//   - cache fresco com aparelhos -> um pílula por aparelho
//   - cache fresco e vazio       -> a janela SOME (nada aqui tem bateria)
//   - cache velho ou ausente     -> "—", em cor de alerta

import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root

    property string texto: ""
    property string dica: ""
    property string classe: "empty"

    // `kmctl bar --json --follow` fica vivo e escreve uma linha por mudança.
    // running: true + o Process reiniciado no onExited dão a rede de segurança:
    // se o kmctl morrer, isto volta sozinho em vez de congelar um número velho.
    Process {
        id: fonte
        command: [Quickshell.env("BATTLOG_KMCTL") || "kmctl",
                  "bar", "--json", "--follow", "--icons"]
        running: true

        stdout: SplitParser {
            splitMarker: "\n"
            onRead: linha => {
                if (!linha.trim()) { root.classe = "empty"; root.texto = ""; return }
                try {
                    const o = JSON.parse(linha)
                    root.texto = o.text || ""
                    root.dica = o.tooltip || ""
                    root.classe = o["class"] || "ok"
                } catch (e) {
                    // Linha torta não derruba a barra: é melhor mostrar o valor
                    // anterior do que sumir por causa de um byte.
                    console.warn("battlog: linha ilegível:", linha)
                }
            }
        }

        onExited: reiniciar.start()
    }

    Timer {
        id: reiniciar
        interval: 3000
        onTriggered: fonte.running = true
    }

    Variants {
        model: Quickshell.screens

        PanelWindow {
            required property var modelData
            screen: modelData

            // Só existe quando há o que dizer. Ausência significando ausência é
            // a mesma regra da extensão do GNOME.
            visible: root.classe !== "empty" && root.texto !== ""

            // A margem de topo default (79) NÃO é estética: a barra do `ii` ocupa
            // `0 0 1920 73`, e com 6 o pílula ficava DESENHADO EM CIMA dela.
            // Descoberto com `hyprctl layers`, não adivinhado. Quem usa outra
            // barra (ou nenhuma) ajusta pelas variáveis abaixo.
            anchors { top: true; right: true }
            margins {
                top: parseInt(Quickshell.env("BATTLOG_MARGIN_TOP") || "79")
                right: parseInt(Quickshell.env("BATTLOG_MARGIN_RIGHT") || "12")
            }
            implicitWidth: conteudo.implicitWidth + 24
            implicitHeight: conteudo.implicitHeight + 10
            color: "transparent"
            // Sem isto a janela reserva espaço e empurra a barra do ii para baixo.
            exclusionMode: ExclusionMode.Ignore

            Rectangle {
                anchors.fill: parent
                radius: height / 2
                color: "#cc1e1e2e"
                border.width: 1
                border.color: root.classe === "stale" ? "#f38ba8"
                            : root.classe === "low"   ? "#fab387"
                            : "#45475a"

                RowLayout {
                    id: conteudo
                    anchors.centerIn: parent
                    spacing: 6

                    Text {
                        text: root.texto
                        color: root.classe === "stale" ? "#f38ba8"
                             : root.classe === "low"   ? "#fab387"
                             : root.classe === "charging" ? "#a6e3a1"
                             : "#cdd6f4"
                        font.pixelSize: 13
                    }
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    onEntered: if (root.dica) console.log(root.dica)
                }
            }
        }
    }
}
