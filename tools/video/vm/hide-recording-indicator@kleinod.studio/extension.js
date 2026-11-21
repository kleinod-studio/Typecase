// Keeps the recording, screen sharing and remote access icons out of the top bar while
// explainer videos are recorded through Mutter's remote desktop and screen cast interfaces.
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export default class HideRecordingIndicator extends Extension {
    enable() {
        const area = Main.panel.statusArea;
        const quick = area.quickSettings;
        this._actors = [area.screenRecording?.container, area.screenSharing?.container, quick?._remoteAccess]
            .filter(Boolean);
        for (const actor of this._actors) {
            actor.hide();
            actor.connectObject('notify::visible', () => actor.visible && actor.hide(), this);
        }
    }

    disable() {
        for (const actor of this._actors ?? [])
            actor.disconnectObject(this);
        this._actors = null;
        Main.panel.statusArea.quickSettings?._remoteAccess?.show();
    }
}
