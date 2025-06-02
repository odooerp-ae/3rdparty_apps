/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";
import { Dropdown } from '@web/core/dropdown/dropdown';
import { useService } from '@web/core/utils/hooks';

class SystrayIcon extends Component {
    setup() {
        super.setup(...arguments);
        this.actionService = useService('action');
    }

    async _onClickIcon() {
        await this.actionService.loadAction({
            type: 'ir.actions.act_window',
            name: 'List of Contact',
            res_model: 'list.contact',
            view_mode: 'form',
            views: [[false, 'form']],
            view_id: 'view_list_contact_form',
            target: 'new',
        });
        this.actionService.doAction({
            type: 'ir.actions.act_window',
            name: 'List of Contact',
            res_model: 'list.contact',
            view_mode: 'form',
            views: [[false, 'form']],
            view_id: 'view_list_contact_form',
            target: 'new',
        });
    }
}

SystrayIcon.template = "systray_icon";
SystrayIcon.components = { Dropdown };
export const systrayItem = { Component: SystrayIcon,};
registry.category("systray").add("SystrayIcon", systrayItem, { sequence: 1 });