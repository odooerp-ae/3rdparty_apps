import logging

import requests
from requests.auth import HTTPBasicAuth

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MaqsamBaseApi(models.AbstractModel):
    _name = "maqsam.base.api"
    _description = "Maqsam Base API Mixin"

    @api.model
    def _get_maqsam_api_credentials(self):
        config_param = self.env["ir.config_parameter"].sudo()
        access_key = config_param.get_param("maqsam.api.access_key")
        access_secret = config_param.get_param("maqsam.api.access_secret")

        if not access_key or not access_secret:
            raise UserError(
                _(
                    "Maqsam API credentials are not configured. "
                    "Please go to Settings > General Settings > Maqsam Integration "
                    "to set them up."
                )
            )
        return access_key, access_secret

    @api.model
    def _get_maqsam_api_url(self, version="v2"):
        config_param = self.env["ir.config_parameter"].sudo()
        if version == "v1":
            return config_param.get_param(
                "maqsam.api.base_url.v1", "https://api.maqsam.com/v1"
            )
        else:
            return config_param.get_param(
                "maqsam.api.base_url.v2", "https://api.maqsam.com/v2"
            )

    @api.model
    def _get_maqsam_portal_url(self):
        config_param = self.env["ir.config_parameter"].sudo()
        return config_param.get_param(
            "maqsam.portal.base_url", "https://portal.maqsam.com"
        )


class MaqsamCall(models.Model):
    _name = "call.erp"
    _inherit = ["mail.thread", "maqsam.base.api"]
    _description = "Maqsam Call"
    _rec_name = "contact_name"

    contact_name = fields.Many2one("res.partner", string="Contact")
    agent_email = fields.Char(
        related="contact_name.email", string="Agent Email", readonly=False
    )
    phone = fields.Char(
        related="contact_name.phone", string="Phone Number", readonly=False
    )
    caller = fields.Char(
        related="contact_name.mobile", string="Caller Number", readonly=False
    )

    def _post_log(self, message):
        self.message_post(body=message)

    def create_call(self):
        for call in self:
            if not call.phone:
                call._post_log("Phone number is required to initiate a call.")
                continue

            # Get API credentials and URL from settings
            access_key, access_secret = self._get_maqsam_api_credentials()
            api_url = f"{self._get_maqsam_api_url(version='v2')}/calls"
            headers = {"Content-Type": "application/x-www-form-urlencoded"}

            payload = {
                "email": call.agent_email,
                "phone": call.phone,
            }

            try:
                response = requests.post(
                    api_url,
                    headers=headers,
                    data=payload,
                    auth=HTTPBasicAuth(access_key, access_secret),
                    timeout=50,
                )
                response.raise_for_status()
                result = response.json()

                if result.get("message") == "success":
                    call._post_log("Call created successfully.")
                else:
                    error_msg = result.get("message", "Unknown error.")
                    call._post_log(f"Failed to create call: {error_msg}")
                    _logger.error("Maqsam API error response: %s", error_msg)

            except requests.exceptions.RequestException as e:
                _logger.exception("Error during Maqsam API call")
                call._post_log(f"Failed to create call due to API error: {e}")


class ListContact(models.TransientModel):
    _name = "list.contact"
    _description = "List of Contacts"

    name = fields.Char()
    contact_ids = fields.Many2many("call.erp", string="Contacts")

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        all_contacts = self.env["call.erp"].search([]).ids
        res.update({"contact_ids": [(6, 0, all_contacts)]})
        return res


class MaqsamDialerCall(models.Model):
    _name = "call.dialer"
    _inherit = ["mail.thread", "maqsam.base.api"]
    _description = "Maqsam Dialer Call"
    _rec_name = "caller"

    phone = fields.Char(string="Phone Number", required=True)
    caller = fields.Char(string="Caller Name")

    def _post_log(self, message):
        self.message_post(body=message)

    def create_call_dialer(self):
        base_url = self._get_maqsam_portal_url()

        for call in self:
            if not call.phone:
                call._post_log("Phone number is required to initiate a call.")
                continue

            autodial_url = f"{base_url}/phone/dialer#autodial={call.phone}"
            _logger.info("Maqsam autodial URL generated: %s", autodial_url)

            call._post_log(f"Initiated call to {call.phone}.")

            return {
                "type": "ir.actions.act_url",
                "url": autodial_url,
                "target": "new",
            }
