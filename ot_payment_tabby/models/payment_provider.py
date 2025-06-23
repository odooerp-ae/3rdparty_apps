# -*- coding: utf-8 -*-
import hashlib
import hmac
import requests
from odoo import api, fields, models
import json

class PaymentProvider(models.Model):
    _inherit = 'payment.provider'

    code = fields.Selection(
        selection_add=[('tabby_payment', "Tabby Payment")], ondelete={'tabby_payment': 'set default'})
    tabby_public_key = fields.Char(
        string="Public Key", required_if_provider='tabby_payment', groups='base.group_system')
    tabby_secret_key = fields.Char(
        string="Secret Key",
        required_if_provider='tabby_payment',
        groups='base.group_system',
        default='dummy'
    )
    tabby_merchant_code = fields.Char(string="Merchant Code", required_if_provider='tabby_payment', groups='base.group_system',default="DUmmy")
    tabby_redirect_url = fields.Char(string='redirect URL', help='It will be redirect return to url')

    def _tabby_get_api_url(self):
        """ Return the URL of the API corresponding to the provider's state.

        :return: The API URL.
        :rtype: str
        """
        self.ensure_one()

        if self.state == 'enabled':
            return 'https://api.tabby.ai'
        else:  # 'test'
            return 'https://api.tabby.ai'

