# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import ast
import werkzeug

class TapController(http.Controller):
    
    
    @http.route("/payment_tabby/get_credentials", type='json', auth='public', csrf=False, save_session=False)
    def tabby_get_credentials(self, **data):
        provider = request.env['payment.provider'].sudo().search([('code','=','tabby_payment')],limit=1)
        return {"tabby_public_key":provider.tabby_public_key,"tabby_merchant_code":provider.tabby_merchant_code}
    
    @http.route("/payment/tabby/success", type='http', auth='public', csrf=False, save_session=False)
    def tabby_return_from_checkout(self, **data):
        """ Process the notification data sent by Tap after redirection from checkout."""
        # Retrieve the tx based on the tx reference included in the return url
        tx_sudo = request.env['payment.transaction'].sudo().search([('tabby_payment_unique_id','=',data.get('payment_id'))])

        # Handle the notification data crafted with Peach API objects
        tx_sudo._handle_notification_data('tabby_payment', data)
        tx_sudo._set_done()
        # Redirect the user to the status page
        return request.redirect('/payment/status')
    
    @http.route("/payment/tabby/cancel", type='http', auth='public', csrf=False, save_session=False)
    def tabby_cancel_from_checkout(self, **data):
        """ Process the notification data sent by Tap after redirection from checkout."""
        # Retrieve the tx based on the tx reference included in the return url
        tx_sudo = request.env['payment.transaction'].sudo().search([('tabby_payment_unique_id','=',data.get('payment_id'))])

        # Handle the notification data crafted with Peach API objects
        tx_sudo._handle_notification_data('tabby_payment', data)
        tx_sudo._set_canceled()
        # Redirect the user to the status page
        return request.redirect('/payment/status')
    
    @http.route("/payment/tabby/failure", type='http', auth='public', csrf=False, save_session=False)
    def tabby_failure_from_checkout(self, **data):
        """ Process the notification data sent by Tap after redirection from checkout."""
        # Retrieve the tx based on the tx reference included in the return url
        tx_sudo = request.env['payment.transaction'].sudo().search([('tabby_payment_unique_id','=',data.get('payment_id'))])

        # Handle the notification data crafted with Peach API objects
        tx_sudo._handle_notification_data('tabby_payment', data)
        tx_sudo._set_error("Transaction Failed")
        # Redirect the user to the status page
        return request.redirect('/payment/status')
    
    @http.route("/tabby/preorder/process", type='http', auth='public', csrf=False, save_session=False)
    def tabby_preorder_process_checkout(self, **data):
        """ Process the notification data sent by Tap after redirection from checkout."""
        return werkzeug.utils.redirect(data.get('web_url'))


    @http.route('/website_sale/get_pricelist_available', type='json', auth='public', website=True)
    def get_pricelist_available(self):
        # Get the active pricelist for the website
        pricelist = request.website._get_current_pricelist()
        print('pricelist',pricelist.currency_id.read(['id', 'name'])[0])
        # Ensure the pricelist exists and return its currency
        if pricelist:
            return {
                'currency_id': pricelist.currency_id.read(['id', 'name'])[0]
            }
        return {'currency_id': None}

