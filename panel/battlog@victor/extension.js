// Bateria do teclado e do mouse no painel.
//
// Não toca em hardware: lê ~/.cache/battlog-status, que o `kmctl probe` do cron
// reescreve a cada 10 min. Leitura de HID, parser dos bytes, escolha de qual
// modelo mostrar e histórico ficam no lado Python — aqui só desenha dois números.
//
// Formato do arquivo, uma linha por chave:
//     ts 1787495551
//     keyboard attackshark_k86 100
//     mouse delux_m900pro 66
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATUS = GLib.build_filenamev([GLib.get_user_cache_dir(), 'battlog-status']);
const ORDEM = [['keyboard', 'input-keyboard-symbolic'], ['mouse', 'input-mouse-symbolic']];
const VELHO = 30 * 60;  // s desde a última gravação: acima disso o cron morreu
const RELER = 120;      // s entre releituras do arquivo

// Devolve {ts, keyboard: {modelo, pct}, ...}, ou null se o cron parou de
// escrever: número velho no painel é pior que "—", porque não se sabe que é velho.
function ler() {
    const [ok, bytes] = GLib.file_get_contents(STATUS);
    if (!ok)
        return null;
    const campos = {};
    for (const linha of new TextDecoder().decode(bytes).split('\n')) {
        const [chave, a, b] = linha.split(' ');
        if (chave === 'ts')
            campos.ts = Number(a);
        else if (b !== undefined)
            campos[chave] = {modelo: a, pct: Number(b)};
    }
    const idade = GLib.get_real_time() / 1e6 - campos.ts;
    return campos.ts && idade < VELHO ? campos : null;
}

const Battlog = GObject.registerClass(
class Battlog extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'battlog', true);  // true = sem menu; não há o que abrir
        const box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this.add_child(box);
        this._labels = {};
        for (const [nome, icone] of ORDEM) {
            box.add_child(new St.Icon({icon_name: icone, style_class: 'system-status-icon'}));
            this._labels[nome] = new St.Label({
                y_align: Clutter.ActorAlign.CENTER,
                style: 'margin-right: 8px;',
            });
            box.add_child(this._labels[nome]);
        }
        this._atualizar();
        this._timer = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, RELER, () => {
            this._atualizar();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _atualizar() {
        let campos = null;
        try {
            campos = ler();
        } catch (e) {
            // arquivo ainda não existe (cron nunca rodou) — cai no "—"
        }
        for (const [nome] of ORDEM) {
            const info = campos?.[nome];
            this._labels[nome].text = info === undefined ? '—' : `${info.pct}%`;
        }
    }

    destroy() {
        if (this._timer)
            GLib.Source.remove(this._timer);
        this._timer = null;
        super.destroy();
    }
});

export default class BattlogExtension extends Extension {
    enable() {
        this._indicator = new Battlog();
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator.destroy();
        this._indicator = null;
    }
}
