# -*- coding: utf-8 -*-

import json
import requests
import logging, pprint
from werkzeug import urls
from datetime import datetime
from odoo.addons.vit_payment_tabby import const


from odoo import models, api, fields, _
from odoo.tools.float_utils import float_compare
from odoo.exceptions import ValidationError, UserError
from odoo.addons.vit_payment_tabby.controllers.main import PaymentTabbyController

_logger = logging.getLogger(__name__)
API_HOME = "https://api.tabby.ai"


class PaymenttabbyConnect(models.Model):
    _inherit = "payment.provider"

    code = fields.Selection(selection_add=[("tabby", "Tabby")], ondelete={"tabby": "set default"})
    tabby_public_key = fields.Char(string="Tabby Public Key")
    tabby_secret_key = fields.Char(string="Tabby Secret Key")
    tabby_merchant_code = fields.Char(string="Tabby Merchant Code")
    tabby_payment_id = fields.Char(string="Tabby Payment ID")
    tabby_reference_id = fields.Char(string="Tabby Reference ID")
    tabby_webhook_id = fields.Char(string="Tabby Webhook ID")

    def _get_supported_currencies(self):
        """ Override of `payment` to return the supported currencies. """
        supported_currencies = super()._get_supported_currencies()
        if self.code == 'tabby':
            supported_currencies = supported_currencies.filtered(
                lambda c: c.name in const.SUPPORTED_CURRENCIES
            )
        return supported_currencies

    def _get_default_payment_method_codes(self):
        """ Override of `payment` to return the default payment method codes. """
        default_codes = super()._get_default_payment_method_codes()
        if self.code != 'tabby':
            return default_codes
        return const.DEFAULT_PAYMENT_METHODS_CODES

    def _get_feature_support(self):
        res = super(PaymenttabbyConnect, self)._get_feature_support()
        res["authorize"].append("tabby")
        return res

    def _get_tabby_consumer_data(self, tabby_txn_values):
        consumer_data = dict()
        consumer_data["name"] = (
                tabby_txn_values.get("billing_partner_first_name")
                + " "
                + tabby_txn_values.get("billing_partner_last_name")
        )
        consumer_data["phone"] = (
                tabby_txn_values.get("billing_partner_phone") and tabby_txn_values.get("billing_partner_phone")[:33]
        )
        consumer_data["email"] = (
                tabby_txn_values.get("billing_partner_email") and tabby_txn_values.get("billing_partner_email")[:129]
        )
        return consumer_data

    def _get_tabby_shipping_address(self, tabby_txn_values):
        shipping_address = dict()
        shipping_address["address"] = ", ".join(
            [
                tabby_txn_values.get("billing_partner").street or "",
                tabby_txn_values.get("billing_partner").street2 or "",
            ]
        )
        shipping_address["zip"] = tabby_txn_values.get("billing_partner_zip")
        shipping_address["city"] = tabby_txn_values.get("billing_partner_city")
        shipping_address['phone'] = tabby_txn_values.get("billing_partner").phone or ''
        return shipping_address

    def _get_tabby_mechant_url(self, tabby_txn_values):
        merchant_urls = dict()
        reference = tabby_txn_values.get("reference")
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        merchant_urls["success"] = str(
            urls.url_join(base_url, PaymentTabbyController.success_url)
        ) + "?reference={}".format(reference)
        merchant_urls["failure"] = str(
            urls.url_join(base_url, PaymentTabbyController.failure_url)
        ) + "?reference={}".format(reference)
        merchant_urls["cancel"] = str(
            urls.url_join(base_url, PaymentTabbyController.cancel_url)
        ) + "?reference={}".format(reference)
        return merchant_urls

    def _get_tabby_items_detail(self, tabby_txn_values):
        items_data = []
        order = self.env["sale.order"].sudo().search([("name", "=", tabby_txn_values.get("reference").split("-")[0])])
        for line in order.order_line:
            if line.product_id.type not in ["service"]:
                line_item = dict()
                line_item["title"] = line.product_id.name
                line_item["quantity"] = int(line.product_uom_qty)
                line_item["unit_price"] = str(int(line.price_unit))
                line_item["category"] = line.product_id.categ_id.name
                line_item["reference_id"] = order.name + line.product_id.name
                items_data.append(line_item)
        return items_data

    def _tabby_make_data(self, tabby_txn_values):
        data = dict()
        context_dict = dict(self._context)
        order = self.env["sale.order"].sudo().search([("name", "=", tabby_txn_values.get("reference").split("-")[0])])
        data["payment"] = {}
        # data["payment"]["amount"] = str(tabby_txn_values.get("amount"))
        data["payment"]["amount"] = str("%.2f" % tabby_txn_values.get("amount"))
        data["payment"]["currency"] = tabby_txn_values.get("currency").name
        data["payment"]["description"] = tabby_txn_values.get("reference")
        data["payment"]["buyer"] = self._get_tabby_consumer_data(tabby_txn_values)
        data["payment"]["shipping_address"] = self._get_tabby_shipping_address(tabby_txn_values)
        data["payment"]["order"] = {
            "tax_amount": str(order.amount_tax),
            "shipping_amount": str(order.amount_delivery),
            "items": self._get_tabby_items_detail(tabby_txn_values),
            "reference_id": order.name
        }
        # New fields: buyer_history
        sales_orders = self.env["sale.order"].sudo().search_count(
            [("partner_id", "=", order.partner_id.id),("state", "=", "sale")])

        data["payment"]["buyer_history"] = {
            "registered_since": order.partner_id.create_date.strftime('%Y-%m-%dT%H:%M:%SZ'),
            "loyalty_level": sales_orders,
        }

        # New fields: order_history
        last_orders = self.env["sale.order"].sudo().search(
            [("partner_id", "=", order.partner_id.id)],
            order='date_order desc',
            limit=10
        )
        state_mapping = {
            'draft': 'new',
            'sent': 'processing',
            'sale': 'complete',
            'cancel': 'canceled'
        }
        order_history = []
        for last_order in last_orders:
            mapped_status = state_mapping.get(last_order.state,'unknown')
            order_history.append({
                "purchased_at": last_order.date_order.strftime('%Y-%m-%dT%H:%M:%SZ'),
                "amount": str(last_order.amount_total),
                # "payment_method": "card",
                "status": mapped_status,
                "buyer": self._get_tabby_consumer_data(tabby_txn_values),
                "shipping_address": self._get_tabby_shipping_address(tabby_txn_values),
            })
        data["payment"]["order_history"] = order_history

        data["lang"] = context_dict.get("lang").split("_")[0]
        data["merchant_code"] = self.tabby_merchant_code
        data["merchant_urls"] = self._get_tabby_mechant_url(tabby_txn_values)
        print('full data = ', data)
        return data

    def _tabby_send_request(self, request_data, method=None, path=None):
        HEADERS = {
            "Authorization": "Bearer " + self.tabby_secret_key,
            "Content-Type": "application/json",
        }
        try:
            _logger.info("######## POST REQUEST DATA ##########%s", (request_data))
            if method == "post":
                response = requests.post(url=API_HOME + path, headers=HEADERS, data=json.dumps(request_data))
                _logger.info("########POST RESPONSE DATA##########%s", response.text)
                return response
            elif method == "get":
                response = requests.get(url=API_HOME + path, headers=HEADERS)
                _logger.info("########GET RESPONSE DATA##########%s", response.text)
                return response
        except Exception as e:
            _logger.warning("#---tabby----Exception-----%r---------" % (e))
            raise UserError(e)

    def _tabby_verify_data(self, response):
        success = True
        data = dict()
        if response.status_code in range(200, 300):
            success = True
            data["success"] = success
            data["data"] = json.loads(response.text)
        else:
            success = False
            json_data = json.loads(response.text)
            data["success"] = success
            data["message"] = json_data.get("error")
        return data

    def _tabby_make_request(self, request_data, method=None, path=None):
        _logger.info("tabby Request Data %r", request_data)
        response = self._tabby_send_request(request_data, method=method, path=path)
        resp_data = self._tabby_verify_data(response)
        if resp_data.get("success") == False:
            raise UserError(resp_data.get("message"))
        return resp_data

    def _get_tabby_txn_url(self, tabby_txn_values):
        request_data = self._tabby_make_data(tabby_txn_values)
        resp_data = self._tabby_make_request(request_data, method="post", path="/api/v2/checkout")
        print("=======>>>>>>", resp_data)
        return resp_data.get("data")

    def tabby_form_generate_values(self, values):
        tabby_txn_values = dict(values)
        _logger.info("########tabby form generate values##########")
        self.tabby_reference_id = tabby_txn_values.get("reference")
        response_data = self._get_tabby_txn_url(tabby_txn_values)
        if response_data.get("status") == "expired":
            raise UserError("Payment request expired\n" + "You aborted the payment. Please retry or choose another payment method.\n"
                                                             "لقد ألغيت الدفعة. فضلاً حاول مجددًا أو اختر طريقة دفع أخرى.")

        if response_data.get("status") == "rejected":
            # raise UserError("Payment request rejected\n" + str(response_data.get("rejection_reason_code")))
            raise UserError("Payment request rejected\n" + "Sorry, Tabby is unable to approve this purchase. Please use an alternative payment method for your order.\n"
                                                             "نأسف، تابي غير قادرة على الموافقة على هذه العملية. الرجاء استخدام طريقة دفع أخرى.")

        self.tabby_payment_id = response_data.get("id")
        tabby_txn_values["tabby_payment_id"] = self.tabby_payment_id
        tabby_txn_values["tabby_checkout_id"] = response_data.get("id")
        tabby_txn_values["tabby_checkout_url"] = (
            response_data.get("configuration").get("available_products").get("installments")[0].get("web_url")
        )
        return tabby_txn_values

    def register_webhook(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        webhook_url = base_url + "/payment/tabby/notification"
        HEADERS = {
            "Authorization": "Bearer " + self.tabby_secret_key,
            "Content-Type": "application/json",
            "X-Merchant-Code": self.tabby_merchant_code,
        }
        request_data = {
            "url": webhook_url,
            "is_test": False if self.state == "enabled" else True,
        }
        try:
            response = requests.post(url=API_HOME + "/api/v1/webhooks", headers=HEADERS, data=json.dumps(request_data))
            if response.status_code != 200:
                raise UserError(response.json())
            self.tabby_webhook_id = response.json().get("id")
        except Exception as e:
            _logger.warning("#---tabby----Exception-----%r---------" % (e))
            raise UserError(e)


class PaymentTransactiontabby(models.Model):
    _inherit = "payment.transaction"

    def _get_buyer_billing_address(self, iyzico_txn_values: dict) -> dict:
        reference = iyzico_txn_values.get("reference").split("-")[0]
        sale_order = self.env["sale.order"].search([("name", "=", reference)])
        partner_id = sale_order.partner_id
        partner_invoice_id = sale_order.partner_invoice_id
        buyer_billing_data = {
            "billing_partner": partner_id,
            "billing_partner_first_name": partner_id.name,
            "billing_partner_last_name": partner_id.name,
            "billing_partner_phone": partner_id.phone,
            "billing_partner_email": partner_id.email or "",
            "billing_partner_address": str(partner_id.street) + str(partner_id.street2),
            "billing_partner_city": partner_id.city,
            "billing_partner_country": partner_id.country_id,
            "billing_partner_zip": partner_id.zip,
            "billing_partner_name": partner_invoice_id.name,
            "billing_partner_address": str(partner_invoice_id.street) + str(partner_invoice_id.street2),
            "billing_partner_city": partner_invoice_id.city,
            "billing_partner_country": partner_invoice_id.country_id,
            "billing_partner_zipCode": partner_invoice_id.zip,
        }
        return buyer_billing_data

    def _get_shipping_address(self, txn_obj):
        shipping_data = {
            "partner_name": txn_obj.partner_name,
            "partner_address": txn_obj.partner_address,
            "partner_city": txn_obj.partner_city,
            "partner_country": txn_obj.partner_country_id,
            "partner_zip": txn_obj.partner_zip,
        }
        return shipping_data

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "tabby":
            return res
        if isinstance(processing_values.get("currency_id"), int):
            record_currency = self.env["res.currency"].browse(processing_values.get("currency_id"))
        else:
            record_currency = processing_values.get("currency_id")
        processing_values.update({"currency": record_currency})
        shipping_address = self._get_shipping_address(self)
        buyer_address = self._get_buyer_billing_address(processing_values)
        processing_values.update(shipping_address)
        processing_values.update(buyer_address)
        _logger.info("######## PROCESSING DATA ##########%s", (processing_values))
        txValues = self.provider_id.tabby_form_generate_values(processing_values)
        txValues.update({"tabby_form": txValues.get("tabby_checkout_url")})
        txValues.update({"tabby_apikey": self.provider_id.tabby_public_key})
        txValues.update({"tabby_merchantcode": self.provider_id.tabby_merchant_code})
        return txValues

    def _process_notification_data(self, notification_data):
        super()._process_notification_data(notification_data)
        if self.provider_code != 'tabby':
            return

        # Force tabby as the payment method if it exists.
        self.payment_method_id = self.env['payment.method'].search(
            [('code', '=', 'tabby')], limit=1
        ) or self.payment_method_id

        _logger.info("Data In Processing Tabby Notify %r ",notification_data)
        _logger.info("Data 1 %r ",notification_data.get("reference"))
        _logger.info("Data 2 %r ",notification_data.get("payment_id"))
        _logger.info("Data 3 %r ",notification_data.get("paymentStatus"))
        reference, paymentId, payment_status = notification_data.get("reference"), notification_data.get("payment_id"), notification_data.get("paymentStatus")
        if not reference and not paymentId:
            _logger.info("Data 1 %r ",notification_data.get("description"))
            _logger.info("Data 2 %r ",notification_data.get("id"))
            _logger.info("Data 3 %r ",notification_data.get("status"))
            reference, paymentId, payment_status = notification_data.get("description"), notification_data.get("id"), notification_data.get("status")
            
        if not reference:
            _logger.info("Data 1 %r ",notification_data.get("order").get("reference_id"))
            reference = notification_data.get("order").get("reference_id")
            
        if self.state == "done":
            _logger.info("Tabby: trying to validate an already validated tx (ref %s)" % self.reference)
            return True

        if not all((reference, paymentId, payment_status)):
            raise ValidationError(
                "Tabby: " + _(
                    "Missing value for reference (%(reference)s) or paymentId (%(paymentId)s or payment_status (%(payment_status)s).",
                    reference=reference, paymentId=paymentId, payment_status=payment_status
                )
            )

        self.provider_reference = paymentId

        if payment_status in ("authorized", "closed"):
            _logger.info("Data 4 %r ",notification_data.get("payment_data"))
            
            payment_data = notification_data.get("payment_data")
            request_data = dict()
            req_path = ""
            if not payment_data:
                request_data["amount"] = str("%.2f" % (float(notification_data.get("amount"))))
                req_path = "/api/v1/payments/{}/captures".format(notification_data.get("id"))
            else:
                request_data["amount"] = str("%.2f" % (float(payment_data.get("amount"))))
                req_path = "/api/v1/payments/{}/captures".format(payment_data.get("id"))

            _logger.info("Data 5 %r ",request_data["amount"])
            _logger.info("Data 6 %r ",req_path)
            
            
            
            auth_response = self.provider_id._tabby_send_request(request_data, method="post", path=req_path)
            resp_data = self.provider_id._tabby_verify_data(auth_response)
            _logger.info("Data 7 %r ",resp_data)
            _logger.info("Data 8 %r ",resp_data.get("success"))
            if not resp_data.get("success"):
                self._set_pending(state_message="Tabby: Transaction Pending.")
            else:
                auth_json_data = resp_data.get("data")
                _logger.info("Data 9 %r ",auth_json_data)
                auth_status = auth_json_data.get("status")
                if auth_status == "CLOSED":
                    self._set_done(state_message="Tabby: Transaction Completed.")
                else:
                    self._set_pending(state_message="Tabby: Transaction Pending.")
        elif payment_status == "expired":
            self._set_canceled(state_message="You aborted the payment. Please retry or choose another payment method.\n لقد ألغيت الدفعة. فضلاً حاول مجددًا أو اختر طريقة دفع أخرى.")
        elif payment_status == "rejected":
            self._set_error(state_message="Sorry, Tabby is unable to approve this purchase. Please use an alternative payment method for your order.\n أسف، تابي غير قادرة على الموافقة على هذه العملية. الرجاء استخدام طريقة دفع أخرى.")
        else:
            _logger.info(
                "received data with invalid payment status (%s) for transaction with reference %s",
                payment_status, self.reference
            )
            self._set_error(
                "Tabby: " + _("Received data with invalid payment status: %s", payment_status)
            )

    def _get_tx_from_notification_data(self, provider_code, notification_data):
        """ Override of payment to find the transaction based on Tabby data.

        :param str provider_code: The code of the provider that handled the transaction
        :param dict notification_data: The notification data sent by the provider
        :return: The transaction if found
        :rtype: recordset of `payment.transaction`
        :raise: ValidationError if the data match no transaction
        """
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)
        if provider_code != 'tabby' or len(tx) == 1:
            return tx

        reference, paymentId, paymentStatus = notification_data.get("reference"), notification_data.get("payment_id"), notification_data.get("paymentStatus")
        if not reference or not paymentStatus:
            error_msg = _("Tabby: Received data with missing reference (%s) or paymentStatus (%s)") % (
                reference,
                paymentStatus,
            )
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        tx = self.search([("reference", "=", reference), ("provider_code", "=", "tabby")])
        if not tx or len(tx) > 1:
            error_msg = _("Tabby: Received data for reference %s") % (reference)
            if not tx:
                error_msg += _("; no order found")
            else:
                error_msg += _("; multiple order found")
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return tx

    def _send_capture_request(self, amount_to_capture=None):
        """ Override of `payment` to send a capture request to Tabby. """
        child_capture_tx = super()._send_capture_request(amount_to_capture=amount_to_capture)
        if self.provider_code != 'tabby':
            return child_capture_tx

        request_data = dict()
        request_data["order_id"] = self.provider_reference
        request_data["total_amount"] = {
            "amount": self.amount,
            "currency": self.currency_id.name,
        }
        request_data["shipping_info"] = {
            "shipped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%Sz"),
            "shipping_company": "Delivery Carrier",
        }
        req_path = "/payments/capture"
        capture_response = self.provider_id._tabby_make_request(request_data, method="post", path=req_path)
        capture_json_data = capture_response.get("data")
        if capture_json_data.get("capture_id"):
            capture_msg = "tabby: Transaction has been captured with capture id {}".format(
                capture_json_data.get("capture_id")
            )
            self._set_done(state_message=capture_msg)

        return child_capture_tx

    def _send_void_request(self, amount_to_void=None):
        """ Override of payment to send a void request to Tabby. """
        child_void_tx = super()._send_void_request(amount_to_void=amount_to_void)
        if self.provider_code != 'tabby':
            return child_void_tx

        request_data = dict()
        request_data["total_amount"] = {
            "amount": self.amount,
            "currency": self.currency_id.name,
        }
        req_path = "/orders/{}/cancel".format(self.provider_reference)
        cancel_response = self.provider_id._tabby_make_request(request_data, method="post", path=req_path)
        cancel_json_data = cancel_response.get("data")
        if cancel_json_data.get("cancel_id"):
            cancel_msg = "tabby: Transaction cancelled with cancelled id {}".format(cancel_json_data.get("cancel_id"))
            self._set_canceled(state_message=cancel_msg)

        return child_void_tx
