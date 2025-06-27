# -*- coding: utf-8 -*-

import json
import pprint
import werkzeug
import logging

from requests import request as pyrequest

from odoo import _, http
from odoo.http import request
from odoo.exceptions import ValidationError
from werkzeug.utils import redirect


_logger = logging.getLogger(__name__)

try:
    import jwt
except Exception as e:
    _logger.error("Python's jwt Library is not installed.(pip3 install jwt)")

APIEND = {
    "live_url": "https://api.tabby.co",
}


class PaymentTabbyController(http.Controller):
    success_url = "/payment/tabby/success"
    failure_url = "/payment/tabby/failure"
    cancel_url = "/payment/tabby/cancel"
    notification_url = "/payment/tabby/notification"

    @http.route([success_url, failure_url, cancel_url], type="http", auth="public", csrf=False)
    def payment_checkout_tabby_return(self, *args, **kwargs):
        _logger.info("tabby: Entering form_feedback with post data %s", pprint.pformat(kwargs))
        tx = (
            request.env["payment.transaction"]
                .sudo()
                .search([("reference", "=", kwargs.get("reference")), ("provider_code", "=", "tabby")])
        )
        try:
            headers = {"Authorization": "Bearer %s" % (tx.provider_id.tabby_secret_key)}
            res = pyrequest(
                "GET", "https://api.tabby.ai/api/v2/payments/%s" % (kwargs.get("payment_id")), headers=headers
            )
            res = res.json()

            _logger.info("res %s" % res)
            kwargs["paymentStatus"] = res.get("status").lower()
            kwargs["payment_data"] = res
        except Exception as e:
            raise ValidationError("tabby: " + _("Payment retrive request is failed:\n%s", str(e)))
        # transaction = request.env["payment.transaction"].sudo()._handle_feedback_data("tabby", kwargs)
        # _logger.info("transaction %s" % transaction)
        tx._process_tabby_notification_data(kwargs)
        # _logger.info("tx %s" % tx)
        if kwargs.get("paymentStatus") in ['cancel','error']:
            _logger.info("Redirect URL: %s/shop/payment?tabby_error_callback=true" % tx.company_id.website)
            return redirect("%s/shop/payment?tabby_error_callback=true" % tx.company_id.website)
        return request.redirect("/payment/status")

    @http.route([notification_url], type="json", auth="public", methods=["POST"], csrf=False)
    def payment_checkout_tabby_notification(self, **kwargs):
        _logger.info("tabby: Entering Notification with post data %s", pprint.pformat(kwargs))
        data = json.loads(request.httprequest.data)
        _logger.info("tabby: post data %r", pprint.pformat(data))
        self._tabby_validate_notification(data)
        return {"status": True}

    def _validate_token(self, tx, token):
        data = False
        if tx.acquirer_id.tabby_public_key:
            try:
                data = jwt.decode(token, tx.acquirer_id.tabby_public_key, algorithms=["HS256"])
                _logger.info("tabby: decoded data %r", data)
                return data
            except Exception as e:
                _logger.info("tabby: Exception while decoding the token %s", str(e))
                raise ValidationError("tabby: " + _("Merchant Verification Token is failed:\n%s", str(e)))
        else:
            raise ValidationError("tabby: " + _("Merchant Verification Token is not set:\n%s", pprint.pformat(token)))

    def _tabby_validate_notification(self, data):
        reference = data.get("description")
        if not reference:
            raise ValidationError(
                "tabby: " + _("Received notification data without reference:\n%s", pprint.pformat(data))
            )
        tx_sudo = request.env["payment.transaction"].sudo().search([("reference", "=", reference)])
        if not tx_sudo or len(tx_sudo) > 1:
            raise ValidationError(
                "tabby: " + _("Received notification data with unknown reference:\n%s", pprint.pformat(data))
            )
        try:
            tx_sudo._process_tabby_notification_data(data)

            _logger.info("tx_sudo %s" % tx_sudo)
        except Exception as e:
            _logger.info("Exception tabby: process notification data %r", str(e))
