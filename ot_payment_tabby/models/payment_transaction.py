# -*- coding: utf-8 -*-
import requests
from odoo import _, api, models, fields
import json
import urllib.parse
import werkzeug
from odoo.exceptions import AccessError, MissingError, ValidationError
import logging
_logger = logging.getLogger(__name__)

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    tabby_payment_unique_id = fields.Char(string="Payment Unique Id", readonly=True)
    tabby_trasaction_charges_details = fields.Text(string="Charges Details",readonly=True)
    
    def _get_checkout_tabby_details(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        data = {
              "payment": {
                "amount": str(self.amount),
                "currency": self.currency_id.name,
                "description": "Tabby Payment reference - %s"%(self.reference),
                "buyer": {
                  "phone": "500000001" if self.provider_id.state == 'test' else self.partner_phone,
                  "email": "card.success@tabby.ai" if self.provider_id.state == 'test' else self.partner_email,
                  "name": self.partner_id.name,
                },
                "shipping_address": {
                  "city": self.partner_city,
                  "address": self.partner_address,
                  "zip": self.partner_zip
                },
                "order": {
                  "tax_amount": str(self.sale_order_ids[0].amount_tax),
                  "reference_id": self.reference,
                  "items": [
                    {
                      "title": item.name,
                      "quantity": int(item.product_uom_qty),
                      "unit_price": str(item.price_unit),
                      "category":item.product_id.categ_id.name if item.product_id.categ_id else 'All'
                    }
                  for item in self.sale_order_ids[0].order_line]
                },
                "buyer_history": {
                  "registered_since": self.partner_id.create_date.isoformat().split('.')[0]+'Z',
                  "loyalty_level": int(len(self.env['sale.order'].sudo().search([('partner_id','=',self.partner_id.id),('state','=','sale')]))),#
                  "is_phone_number_verified": True if self.partner_phone else False,
                  "is_email_verified": True if self.partner_email else False,
                  "is_social_networks_connected": True,
                },
                "order_history": [
                  {
                    "purchased_at": self.sale_order_ids[0].create_date.isoformat().split('.')[0]+'Z',
                    "amount": str(self.amount),
                    "status": "complete",
                  }
                ],
                "meta": {
                  "order_id": self.reference,
                  "customer": self.partner_id.name
                },
              },
              "lang": "en",
              "merchant_code": self.provider_id.tabby_merchant_code,
              "merchant_urls": {
                "success": "%s/payment/tabby/success"%(base_url),
                "cancel": "%s/payment/tabby/cancel"%(base_url),
                "failure": "%s/payment/tabby/failure"%(base_url)
              },
              "create_token": False,
            }
        return data
    
    def _get_specific_rendering_values(self, processing_values):
        """ Override of payment to return Transfer-specific rendering values.

        Note: self.ensure_one() from `_get_processing_values`

        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of acquirer-specific processing values
        :rtype: dict
        """
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != 'tabby_payment':
            return res
        API_URL = self.provider_id._tabby_get_api_url()
        url = API_URL + '/api/v2/checkout'
        data = self._get_checkout_tabby_details()
#        _logger.info("---data->%s"%data)
        headers = {
                "accept": "application/json",
                "content-type": "application/json",
                "Authorization": "Bearer %s"%(self.provider_id.tabby_public_key)
            }
        response = requests.post(url, json=data, headers=headers)
        json_response = json.loads(response.text)
#        _logger.info("---json_response->%s"%json_response)
        if json_response.get('status') == 'error':
            raise ValidationError(json_response.get('error'))
        elif json_response.get('status') == 'rejected':
            if json_response.get('rejection_reason_code') == 'not_available':
                raise ValidationError('Sorry, Tabby is unable to approve this purchase. Please use an alternative payment method for your order.')
            elif json_response.get('rejection_reason_code') == 'order_amount_too_high':
                raise ValidationError('This purchase is above your current spending limit with Tabby, try a smaller cart or use another payment method')
            elif json_response.get('rejection_reason_code') == 'order_amount_too_low':
                raise ValidationError('The purchase amount is below the minimum amount required to use Tabby, try adding more items or use another payment method')
        self.write({
            'tabby_payment_unique_id':json_response.get('payment').get('id'),
            'tabby_trasaction_charges_details':response.text,
            'provider_reference':json_response.get('payment').get('id')
        })
        self._set_pending()
        parsed_url = urllib.parse.urlparse(json_response.get('configuration').get('available_products').get('installments')[-1].get('web_url'))
        # Get the query parameters as a dictionary
        query_params = urllib.parse.parse_qs(parsed_url.query)
#        'https://checkout.tabby.ai/?sessionId=ff38dc78-8c89-43c5-8675-ee8ff530319f&apiKey=pk_test_f4c94094-4308-4711-81b1-6f47b4ff86b5&product=installments&merchantCode=CMCSUAE',
        return {
            'api_url': '/tabby/preorder/process',
            'web_url': '%s'%(json_response.get('configuration').get('available_products').get('installments')[-1].get('web_url')),
            'sessionId': query_params.get('sessionId', [None])[0],
            "product":"installments",
            "apikey":self.provider_id.tabby_public_key,
            'merchantCode':self.provider_id.tabby_merchant_code
        }
    
