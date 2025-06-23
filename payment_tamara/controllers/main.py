# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

import json
import logging
import pprint
import traceback

from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request
from odoo.tools.misc import get_lang

_logger = logging.getLogger(__name__)

try:
    import jwt
except Exception:
    _logger.error("Python's jwt Library is not installed.")

APIEND = {
    "test_url": "https://api-sandbox.tamara.co",
    "live_url": "https://api.tamara.co",
}


class PaymentTamaraController(http.Controller):
    success_url = "/payment/tamara/success"
    failure_url = "/payment/tamara/failure"
    cancel_url = "/payment/tamara/cancel"
    notification_url = "/payment/tamara/notification"

    @http.route([success_url, failure_url, cancel_url], type="http", auth="public", csrf=False)
    def payment_checkout_tamara_return(self, *args, **kwargs):
        jomla_website_url = (
            request.env["ir.config_parameter"].sudo().get_param("jomla_website_url", "https://odoo.jomla.ae")
        )
        lang = "ar"
        try:
            tx = False
            _logger.info("Tamara: Entering form_feedback with post data %s", pprint.pformat(kwargs))
            tx = request.env["payment.transaction"].sudo()._handle_notification_data("tamara", kwargs)

            sale_order = tx.sale_order_ids
            if sale_order.partner_id.lang:
                lang = get_lang(request.env, sale_order.partner_id.lang).url_code

            if tx.state == "cancel":
                return request.redirect(f"{jomla_website_url}/{lang}/checkout/?payment_status=cancelled", local=False)

            if tx.state == "error":
                return request.redirect(f"{jomla_website_url}/{lang}/checkout/?payment_status=failed", local=False)

            return request.redirect(f"{jomla_website_url}/{lang}/thank-you/?order_id={sale_order.id}", local=False)
        except Exception as e:
            traceback.print_exc()

            if tx:
                tx._set_error(e)

                if tx.sale_order_ids:
                    tx.sale_order_ids.action_cancel()

            return request.redirect(f"{jomla_website_url}/{lang}/checkout/?payment_status=failed", local=False)

    @http.route([notification_url], type="json", auth="public", methods=["POST"], csrf=False)
    def payment_checkout_tamara_notification(self, **kwargs):
        _logger.info("Tamara: Entering Notification with post data %s", pprint.pformat(kwargs))
        data = json.loads(request.httprequest.data)
        _logger.info("Tamara: post data %r", pprint.pformat(data))
        self._tamara_validate_notification(data)
        return "success"  # Return 'success' to stop receiving notifications for this tx

    def _validate_token(self, tx, token):
        data = False
        if tx.provider_id.tamara_notification_token:
            try:
                data = jwt.decode(token, tx.provider_id.tamara_notification_token, algorithms=["HS256"])
                _logger.info("Tamara: decoded data %r", data)
                return data
            except Exception as e:
                _logger.info("Tamara: Exception while decoding the token %s", str(e))
                raise ValidationError("Tamara: " + _("Merchant Verification Token is failed:\n%s", str(e)))
        else:
            raise ValidationError("Tamara: " + _("Merchant Verification Token is not set:\n%s", pprint.pformat(token)))

    def _tamara_validate_notification(self, data):
        if not data.get("order_reference_id"):
            raise ValidationError(
                "Tamara: " + _("Received notification data without reference:\n%s", pprint.pformat(data))
            )
        tx_sudo = request.env["payment.transaction"].sudo().search([("reference", "=", data.get("order_reference_id"))])
        if not tx_sudo or len(tx_sudo) > 1:
            raise ValidationError(
                "Tamara: " + _("Received notification data with unknown reference:\n%s", pprint.pformat(data))
            )
        # data = self._validate_token(tx_sudo, data.get('tamaraToken'))
        if data.get("order_id"):
            try:
                token = request.httprequest.args.get("tamaraToken")
                _logger.info("Tamara token %r", token)
                self._validate_token(tx_sudo, token)
                tx_sudo._process_notification_data_custom(data)
            except Exception as e:
                _logger.info("Exception Tamara: process notification data %r", str(e))


class ProductWidget(http.Controller):
    @http.route("/product/widget", type="json", auth="public", website=True)
    def product_widget(self):
        company = request.env.company

        vals = {
            "product_widget": company.product_widget,
            "data_disable_installment": company.data_disable_installment,
            "data_disable_paylater": company.data_disable_paylater,
            "data_payment_type": company.data_payment_type,
            "data_installment_minimum_amount": company.data_installment_minimum_amount,
            "data_installment_maximum_amount": company.data_installment_maximum_amount,
            "data_installment_available_amount": company.data_installment_available_amount,
            "data_pay_later_max_amount ": company.data_pay_later_max_amount,
        }

        return vals
