from odoo import fields, models


class sf_response_message_wizard(models.TransientModel):
    _name = 'salseforce.message.wizard'
    _description = "Show response message on wizard"

    def _get_sf_message(self):
        return self._context['message']

    message = fields.Text("Response", default=_get_sf_message, readonly=True)
