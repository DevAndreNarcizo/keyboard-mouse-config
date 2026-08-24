// Bateria do teclado, do mouse e do fone no painel.
//
// Não toca em hardware: lê ~/.cache/battlog-status, que o `kmctl probe` do cron
// reescreve a cada 10 min. Leitura de HID/BlueZ, parser dos bytes, escolha de
// qual modelo mostrar e histórico ficam no lado Python — aqui só desenha números.
//
// Formato do arquivo, uma linha por chave:
//     ts 1787495551
//     mouse delux_m800pro 100
//     headset jbl_wave_buds_2 90
//
// Categoria ausente de um arquivo FRESCO é aparelho que não existe nesta máquina,
// e some do painel: um "—" eterno ao lado do ícone de teclado, numa máquina de
// teclado com fio, é ruído e não informação. Já arquivo velho ou ausente é o cron
// ter morrido, e aí TODAS aparecem com "—" — esse é o caso que precisa ser visto.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATUS = GLib.build_filenamev([GLib.get_user_cache_dir(), 'battlog-status']);
// A ordem é a do painel. As chaves têm que casar com devices.KINDS do lado Python.
const ORDEM = [
    ['keyboard', 'input-keyboard-symbolic'],
    ['mouse', 'input-mouse-symbolic'],
    ['headset', 'audio-headset-symbolic'],
];
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
        this._slots = {};
        for (const [nome, icone] of ORDEM) {
            // um box por categoria, para poder esconder ícone e número juntos
            const slot = new St.BoxLayout();
            slot.add_child(new St.Icon({
                icon_name: icone,
                style_class: 'system-status-icon',
            }));
            const label = new St.Label({
                y_align: Clutter.ActorAlign.CENTER,
                style: 'margin-right: 8px;',
            });
            slot.add_child(label);
            box.add_child(slot);
            this._slots[nome] = {slot, label};
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
        const vivo = campos !== null;
        for (const [nome] of ORDEM) {
            const info = campos?.[nome];
            const {slot, label} = this._slots[nome];
            // fresco: mostra só quem tem número. Velho/ausente: mostra tudo com
            // "—", porque aí o problema é o cron e some-lo esconderia a falha.
            slot.visible = !vivo || info !== undefined;
            label.text = info === undefined ? '—' : `${info.pct}%`;
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
