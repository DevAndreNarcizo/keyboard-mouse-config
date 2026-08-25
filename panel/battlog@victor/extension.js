// Bateria de tudo que está aqui e tem bateria, no painel.
//
// Não toca em hardware: lê ~/.cache/battlog-status, que o `kmctl watch` reescreve
// assim que algo muda. Descoberta, protocolo, escolha de fonte e histórico ficam
// no lado Python — aqui só se desenha o que o arquivo mandar.
//
// O arquivo é VIGIADO (Gio.FileMonitor), não relido por tempo: mudança aparece na
// hora. O timer que sobrou é rede de segurança para um caso só — quando quem
// escreve morre, ninguém gera evento, e é o timer que faz o "—" aparecer.
//
//     ts 1787589472
//     dev mouse delux_m800pro 100 0 Delux M800 PRO
//     dev headset bt_501b6a0cf973 90 - JBL Wave Buds 2
//
// Campos: `dev <kind> <ident> <pct> <carga> <nome...>`. O nome vem por último
// porque é o único que pode ter espaço. Carga é 0, 1 ou "-" (desconhecida).
//
// Um slot por APARELHO, não por categoria: fone + mouse + teclado sem fio ao
// mesmo tempo são três coisas para mostrar. A lista vem do arquivo, então
// aparelho novo não pede mexer neste código.
//
// Na barra cabe ícone + número; o NOME vai no menu, porque com dois mouses ao
// mesmo tempo dois ícones iguais com dois números não dizem qual é qual.
//
// Três estados, de propósito:
//   - arquivo fresco com aparelhos  -> um slot para cada
//   - arquivo fresco e vazio        -> widget SOME. Nada aqui tem bateria, e
//                                     ausência significando ausência é o pedido.
//   - arquivo velho ou ausente      -> um "—". Aí o problema é o cron ter
//                                     morrido, e esconder isso esconderia a falha.
import Clutter from 'gi://Clutter';
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATUS = GLib.build_filenamev([GLib.get_user_cache_dir(), 'battlog-status']);
const VELHO = 30 * 60;  // s desde a última gravação: acima disso quem lê morreu
// O arquivo é vigiado, então releitura por tempo é só rede de segurança — ela
// existe para a transição para "—" acontecer, que é justamente o caso em que
// ninguém escreve e portanto nenhum evento chega.
const RELER = 60;

// As chaves são os KINDS do lado Python. Kind que não estiver aqui cai no
// genérico — o Python manda "other" quando uma fonte acha algo que não sabe
// classificar, e um ícone de bateria é melhor que um ícone errado.
const ICONE = {
    keyboard: 'input-keyboard-symbolic',
    mouse: 'input-mouse-symbolic',
    headset: 'audio-headset-symbolic',
    phone: 'phone-symbolic',
    gamepad: 'input-gaming-symbolic',
    other: 'battery-symbolic',
};

// Devolve {ts, devs: [{kind, ident, pct, carga, nome}]}, ou null se o cron parou
// de escrever: número velho no painel é pior que "—", porque não se sabe que é velho.
function ler() {
    const [ok, bytes] = GLib.file_get_contents(STATUS);
    if (!ok)
        return null;
    let ts = 0;
    const devs = [];
    for (const linha of new TextDecoder().decode(bytes).split('\n')) {
        const campos = linha.split(' ');
        if (campos[0] === 'ts') {
            ts = Number(campos[1]);
        } else if (campos[0] === 'dev' && campos.length >= 6) {
            devs.push({
                kind: campos[1],
                ident: campos[2],
                pct: Number(campos[3]),
                carga: campos[4] === '1',
                nome: campos.slice(5).join(' '),
            });
        }
    }
    if (!ts || GLib.get_real_time() / 1e6 - ts >= VELHO)
        return null;
    return {ts, devs};
}

const Battlog = GObject.registerClass(
class Battlog extends PanelMenu.Button {
    _init() {
        // Com menu: na barra cabe só ícone + número, e com dois mouses ao mesmo
        // tempo isso não diz QUAL é qual. O menu mostra o nome de cada um.
        super._init(0.0, 'battlog');
        this._box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this.add_child(this._box);
        this._atualizar();
        // Vigia o arquivo: o `kmctl watch` reescreve no instante em que algo
        // muda, e o painel reflete na hora em vez de esperar o próximo tick.
        // O backend inotify do GLib observa o diretório pelo nome, então a troca
        // atômica (`os.replace`) que o lado Python faz é detectada.
        try {
            this._monitor = Gio.File.new_for_path(STATUS)
                .monitor_file(Gio.FileMonitorFlags.NONE, null);
            this._monitorId = this._monitor.connect('changed',
                () => this._atualizar());
        } catch (e) {
            // sem monitor o widget continua funcionando pelo timer abaixo
            this._monitor = null;
        }
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, RELER, () => {
            this._atualizar();
            return GLib.SOURCE_CONTINUE;
        });
    }

    // A lista de aparelhos muda quando se liga ou desliga um, então os slots são
    // refeitos a cada leitura. É a cada 2 min e são poucos atores; diffar não
    // pagaria a complexidade.
    _slot(icone, texto, nome) {
        const slot = new St.BoxLayout();
        slot.add_child(new St.Icon({
            icon_name: icone,
            style_class: 'system-status-icon',
        }));
        slot.add_child(new St.Label({
            text: texto,
            y_align: Clutter.ActorAlign.CENTER,
            style: 'margin-right: 8px;',
        }));
        if (nome)
            slot.set_accessible_name(`${nome}: ${texto}`);
        this._box.add_child(slot);
    }

    _item(texto, icone) {
        const item = new PopupMenu.PopupImageMenuItem(texto, icone,
            {reactive: false});
        this.menu.addMenuItem(item);
    }

    _atualizar() {
        let dados = null;
        try {
            dados = ler();
        } catch (e) {
            // arquivo ainda não existe (serviço nunca rodou) — cai no "—"
        }
        this._box.destroy_all_children();
        this.menu.removeAll();
        if (dados === null) {
            this._slot('battery-missing-symbolic', '—', 'battlog sem dados');
            this._item('Nenhuma leitura recente', 'battery-missing-symbolic');
            this._item('systemctl --user status battlog.service',
                'dialog-information-symbolic');
            this.visible = true;
            return;
        }
        for (const d of dados.devs) {
            const icone = ICONE[d.kind] ?? ICONE.other;
            const valor = `${d.pct}%${d.carga ? '⚡' : ''}`;
            this._slot(icone, valor, d.nome);
            // é aqui que se sabe qual é qual quando há dois do mesmo tipo
            this._item(`${d.nome} — ${valor}`, icone);
        }
        // fresco e vazio: nada aqui tem bateria, então nada a mostrar
        this.visible = dados.devs.length > 0;
    }

    destroy() {
        if (this._timer)
            GLib.Source.remove(this._timer);
        this._timer = null;
        if (this._monitor) {
            this._monitor.disconnect(this._monitorId);
            this._monitor.cancel();
            this._monitor = null;
        }
        super.destroy();
    }
});

export default class BattlogExtension extends Extension {
    enable() {
        // Guarda contra enable() em cima de um indicador que já existe: o shell
        // faz isso quando um disable() anterior falhou no meio. Sem isto sobra um
        // indicador órfão na barra, que ninguém mais consegue destruir.
        if (this._indicator)
            this.disable();
        this._indicator = new Battlog();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        // O `?.` não é decoração. O shell chama disable() mesmo quando enable()
        // nunca rodou (extensão que entrou em ERROR, recarga em lote, sessão
        // terminando) e, sem a guarda, esse segundo disable() lança
        // "this._indicator is null" — o que põe a extensão em ERROR e ela não
        // volta sozinha nem reabilitando: só reiniciando o shell.
        //
        // Foi exatamente o que aconteceu ao recarregar todas as extensões de
        // uma vez em 2026-08-24.
        this._indicator?.destroy();
        this._indicator = null;
    }
}
