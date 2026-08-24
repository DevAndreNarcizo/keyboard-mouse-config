// Bateria de tudo que está aqui e tem bateria, no painel.
//
// Não toca em hardware: lê ~/.cache/battlog-status, que o `kmctl probe` do cron
// reescreve a cada 10 min. Descoberta, protocolo, escolha de fonte e histórico
// ficam no lado Python — aqui só se desenha o que o arquivo mandar.
//
//     ts 1787589472
//     dev mouse delux_m800pro 100 0 Delux M800 PRO
//     dev headset jbl_wave_buds_2 90 - JBL Wave Buds 2
//
// Campos: `dev <kind> <ident> <pct> <carga> <nome...>`. O nome vem por último
// porque é o único que pode ter espaço. Carga é 0, 1 ou "-" (desconhecida).
//
// Um slot por APARELHO, não por categoria: fone + mouse + teclado sem fio ao
// mesmo tempo são três coisas para mostrar. A lista vem do arquivo, então
// aparelho novo não pede mexer neste código.
//
// Três estados, de propósito:
//   - arquivo fresco com aparelhos  -> um slot para cada
//   - arquivo fresco e vazio        -> widget SOME. Nada aqui tem bateria, e
//                                     ausência significando ausência é o pedido.
//   - arquivo velho ou ausente      -> um "—". Aí o problema é o cron ter
//                                     morrido, e esconder isso esconderia a falha.
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const STATUS = GLib.build_filenamev([GLib.get_user_cache_dir(), 'battlog-status']);
const VELHO = 30 * 60;  // s desde a última gravação: acima disso o cron morreu
const RELER = 120;      // s entre releituras do arquivo

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
        super._init(0.0, 'battlog', true);  // true = sem menu; não há o que abrir
        this._box = new St.BoxLayout({style_class: 'panel-status-menu-box'});
        this.add_child(this._box);
        this._atualizar();
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

    _atualizar() {
        let dados = null;
        try {
            dados = ler();
        } catch (e) {
            // arquivo ainda não existe (cron nunca rodou) — cai no "—"
        }
        this._box.destroy_all_children();
        if (dados === null) {
            this._slot('battery-missing-symbolic', '—', 'cron do battlog parado');
            this.visible = true;
            return;
        }
        for (const d of dados.devs) {
            const icone = ICONE[d.kind] ?? ICONE.other;
            this._slot(icone, `${d.pct}%${d.carga ? '⚡' : ''}`, d.nome);
        }
        // fresco e vazio: nada aqui tem bateria, então nada a mostrar
        this.visible = dados.devs.length > 0;
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
