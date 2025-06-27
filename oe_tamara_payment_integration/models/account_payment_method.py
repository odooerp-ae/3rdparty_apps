from odoo import api, models


class PaymentMethod(models.Model):
    _inherit = "payment.method"

    @api.model
    def _get_payment_method_information(self):
        res = super()._get_payment_method_information()
        res["tamara"] = {"mode": "unique", "domain": [("type", "=", "bank")]}
        return res
