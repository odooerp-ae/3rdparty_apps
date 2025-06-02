/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component } from "@odoo/owl";

class SystrayIcon extends Component {
    setup() {
        super.setup(...arguments);
    }
}

SystrayIcon.template = "systray_icon";
export const systrayItem = { Component: SystrayIcon,};
registry.category("systray").add("SystrayIcon", systrayItem, { sequence: 1 });