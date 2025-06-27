# -*- coding: utf-8 -*-

import json
import requests
import logging
from werkzeug import urls
from datetime import datetime

from odoo import models, api, fields, _
from odoo.tools.float_utils import float_compare
from odoo.exceptions import ValidationError, UserError
from odoo.addons.oe_tabby_payment_integration.controllers.main import PaymentTabbyController

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
    tabby_webhook_id = fields.Char()

    @api.model
    def _get_compatible_providers(
            self, company_id, partner_id, amount, currency_id=None, force_tokenization=False,
            is_express_checkout=False, is_validation=False, website_id=None, sale_order_id=None, **kwargs
    ):
        res = super(PaymenttabbyConnect, self)._get_compatible_providers(company_id, partner_id, amount,
                                                                         currency_id=None, force_tokenization=False,
                                                                         is_express_checkout=False, is_validation=False,
                                                                         website_id=website_id,
                                                                         sale_order_id=sale_order_id, **kwargs)
        sale_order = self.env['sale.order'].browse(sale_order_id)
        if sale_order and sale_order.pricelist_id.currency_id.name != 'AED':
            res = res.filtered(lambda p: p.code != 'tabby')
        return res



    def _get_feature_support(self):
        res = super(PaymenttabbyConnect, self)._get_feature_support()
        res["authorize"].append("tabby")
        return res

    def _get_tabby_consumer_data(self, tabby_txn_values):
        consumer_data = dict()
        name = ''
        if tabby_txn_values.get("billing_partner_first_name"):
            name += tabby_txn_values.get("billing_partner_first_name") + ' '
        if tabby_txn_values.get("billing_partner_last_name"):
            name += tabby_txn_values.get("billing_partner_last_name")
        consumer_data["name"] = name
        # consumer_data["phone"] = str(
        #     tabby_txn_values.get("billing_partner_phone") and tabby_txn_values.get("billing_partner_phone")[:33]
        # )
        # consumer_data["email"] = str(
        #     tabby_txn_values.get("billing_partner_email") and tabby_txn_values.get("billing_partner_email")[:129]
        # )
        consumer_data["phone"] = '+923317528570'
        if tabby_txn_values.get("billing_partner_phone"):
            consumer_data["phone"] = str(
                tabby_txn_values.get("billing_partner_phone") and tabby_txn_values.get("billing_partner_phone")[:33]
            )
        consumer_data["email"] = ''
        if tabby_txn_values.get("billing_partner_email"):
            consumer_data["email"] = str(
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
        shipping_address["city"] = ''
        if tabby_txn_values.get("billing_partner_city"):
            shipping_address["city"] = str(tabby_txn_values.get("billing_partner_city"))
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
                line_item["reference_id"] = str(order.name + line.product_id.name)
                items_data.append(line_item)
        return items_data

    def _tabby_make_data(self, tabby_txn_values):
        data = dict()
        context_dict = dict(self._context)
        _logger.info("Values %s" % tabby_txn_values)
        order = self.env["sale.order"].sudo().search([("name", "=", tabby_txn_values.get("reference").split("-")[0])])
        data["payment"] = {}
        data["payment"]["amount"] = str(tabby_txn_values.get("amount"))
        data["payment"]["currency"] = tabby_txn_values.get("currency").name
        data["payment"]["description"] = tabby_txn_values.get("reference")
        data["payment"]["buyer"] = self._get_tabby_consumer_data(tabby_txn_values)
        data["payment"]["shipping_address"] = self._get_tabby_shipping_address(tabby_txn_values)
        data["payment"]["order"] = {
            "tax_amount": str(order.amount_tax),
            "shipping_amount": str(order.amount_delivery),
            "items": self._get_tabby_items_detail(tabby_txn_values),
            "reference_id": str(order.name)
        }
        data["lang"] = context_dict.get("lang").split("_")[0]
        data["merchant_code"] = self.tabby_merchant_code
        data["merchant_urls"] = self._get_tabby_mechant_url(tabby_txn_values)
        _logger.info("data %s" % data)
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

        _logger.info("response %s" % response)
        _logger.info("resp_data %s" % resp_data)
        if resp_data.get("success") == False:
            raise UserError(resp_data.get("message"))
        return resp_data

    def _get_tabby_txn_url(self, tabby_txn_values):
        request_data = self._tabby_make_data(tabby_txn_values)
        resp_data = self._tabby_make_request(request_data, method="post", path="/api/v2/checkout")
        return resp_data.get("data")

    def tabby_form_generate_values(self, values):
        tabby_txn_values = dict(values)
        _logger.info("########tabby form generate values##########")
        self.tabby_reference_id = tabby_txn_values.get("reference")
        response_data = self._get_tabby_txn_url(tabby_txn_values)

        _logger.info("response_data %s" % response_data)
        if response_data.get("status") == "rejected":
            raise UserError("Payment request rejected\n" + str(response_data.get("warnings")))
        self.tabby_payment_id = response_data.get("id")
        tabby_txn_values["tabby_payment_id"] = self.tabby_payment_id
        tabby_txn_values["tabby_checkout_id"] = response_data.get("id")
        tabby_txn_values["tabby_checkout_url"] = (
            response_data.get("configuration").get("available_products").get("installments")[0].get("web_url")
        )
        _logger.info("tabby_txn_values %s" % tabby_txn_values)
        return tabby_txn_values

    def _get_default_payment_method_id(self,code=False):
        self.ensure_one()
        if self.code != "tabby":
            return super()._get_default_payment_method_id(code=code)
        return self.env.ref("oe_tabby_payment_integration.payment_tabby_connect").id

    def register_webhook(self):
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        webhook_url = "https://odooerp-ae-mdv16-pre-production-13300120.dev.odoo.com/payment/tabby/notification"
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
        partner_phone = partner_id.phone
        if not partner_phone:
            partner_phone = partner_id.mobile
        buyer_billing_data = {
            "billing_partner": partner_id,
            "billing_partner_first_name": partner_id.name,
            "billing_partner_last_name": partner_id.name,
            "billing_partner_phone": partner_phone,
            "billing_partner_email": partner_id.email or "",
            "billing_partner_address": str(partner_id.street) + str(partner_id.street2),
            "billing_partner_city": partner_id.state_id.name,
            "billing_partner_country": partner_id.country_id,
            "billing_partner_zip": partner_id.zip if partner_id.zip else '12345',
            "billing_partner_name": partner_invoice_id.name,
            "billing_partner_address": str(partner_invoice_id.street) + str(partner_invoice_id.street2),
            "billing_partner_city": partner_invoice_id.state_id.name,
            "billing_partner_country": partner_invoice_id.country_id,
            "billing_partner_zipCode": partner_invoice_id.zip if partner_invoice_id.zip else '12345',
        }
        return buyer_billing_data

    def _get_shipping_address(self, txn_obj):
        shipping_data = {
            "partner_name": txn_obj.partner_name,
            "partner_address": txn_obj.partner_address,
            "partner_city": txn_obj.partner_city,
            "partner_country": txn_obj.partner_country_id,
            "partner_zip": txn_obj.partner_zip,
            "partner_phone": txn_obj.partner_phone,

        }
        return shipping_data

    def _get_specific_rendering_values(self, processing_values):
        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "tabby":
            return res
        else:
            if isinstance(processing_values.get("currency_id"), int):
                record_currency = self.env["res.currency"].browse(processing_values.get("currency_id"))
            else:
                record_currency = processing_values.get("currency_id")
            processing_values.update({"currency": record_currency})
            # rendering_values = processing_values
            shipping_address = self._get_shipping_address(self)
            buyer_address = self._get_buyer_billing_address(processing_values)
            processing_values.update(shipping_address)
            processing_values.update(buyer_address)
            _logger.info("######## PROCESSING DATA ##########%s", (processing_values))
            txValues = self.provider_id.tabby_form_generate_values(processing_values)
            txValues.update({"tabby_form": txValues.get("tabby_checkout_url")})
            txValues.update({"tabby_apikey": self.provider_id.tabby_public_key})
            txValues.update({"tabby_merchant_code": self.provider_id.tabby_merchant_code})
        return txValues

    @api.model
    def _get_tx_from_feedback_data(self, provider, data):
        tx = super()._get_tx_from_feedback_data(provider, data)
        if provider != "tabby":
            return tx
        reference, paymentId, paymentStatus = data.get("reference"), data.get("payment_id"), data.get("paymentStatus")
        if not reference or not paymentStatus:
            error_msg = _("tabby: received data with missing reference (%s) or paymentStatus (%s)") % (
                reference,
                paymentStatus,
            )
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        tx = self.search([("reference", "=", reference), ("provider_code", "=", "tabby")])
        if not tx or len(tx) > 1:
            error_msg = _("tabby: received data for reference %s") % (reference)
            if not tx:
                error_msg += _("; no order found")
            else:
                error_msg += _("; multiple order found")
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return tx

    def _tabby_form_get_invalid_parameters(self, data):
        reference, paymentId, paymentStatus = data.get("reference"), data.get("payment_id"), data.get("paymentStatus")
        if paymentStatus == "canceled":
            return
        invalid_parameters = []
        req_path = "/orders/" + str(paymentId)
        order_details = self.provider_id._tabby_make_request(False, method="get", path=req_path)
        data = order_details.get("data")
        total_amount = data.get("total_amount").get("amount")
        currency = data.get("total_amount").get("currency")
        if float_compare(float(total_amount), self.amount, 2) != 0:
            invalid_parameters.append(("Amount", total_amount, "%.2f" % self.amount))
        if currency != self.currency_id.name:
            invalid_parameters.append(("Currency", currency, self.currency_id.name))
        if reference != self.reference:
            invalid_parameters.append(("Reference", reference, self.reference))
        return invalid_parameters

    def _process_tabby_notification_data(self, data):
        reference, paymentId, paymentStatus = data.get("reference"), data.get("payment_id"), data.get("paymentStatus")
        if not reference and not paymentId:
            reference, paymentId, paymentStatus = data.get("description"), data.get("id"), data.get("status")
        if self.state == "done":
            _logger.warning("Tabby: trying to validate an already validated tx (ref %s)" % self.reference)
            return True

        _logger.info("_process_tabby_notification_data %s" % reference)
        _logger.info("_process_tabby_notification_data %s" % paymentId)
        _logger.info("_process_tabby_notification_data %s" % paymentStatus)
        if paymentStatus == "authorized":
            payment_data = data.get("payment_data")
            request_data = dict()
            request_data["amount"] = str("%.2f" % (float(payment_data.get("amount"))))
            req_path = "/api/v1/payments/{}/captures".format(payment_data.get("id"))
            auth_response = self.provider_id._tabby_send_request(request_data, method="post", path=req_path)
            resp_data = self.provider_id._tabby_verify_data(auth_response)
            if not resp_data.get("success"):
                self.write(
                    {
                        "provider_id": self.env['payment.provider'].search([('code','=','tabby')]).id,
                        "state_message": "Tabby: Transaction Pending",
                    }
                )
                self._set_pending()
                return True
            else:
                auth_json_data = resp_data.get("data")
                auth_status = auth_json_data.get("status")
                if auth_status == "CLOSED":
                    self.write({"provider_id": self.env['payment.provider'].search([('code','=','tabby')]).id})
                    self._set_done()
                    self._create_payment()
                    return True
                else:
                    self.write({"provider_id": self.env['payment.provider'].search([('code','=','tabby')]).id})
                    self._set_pending()
                    return True
        elif paymentStatus == "expired":
            cancel_msg = "Tabby: Transaction Expired"
            self.write(
                {
                    "provider_id": self.env['payment.provider'].search([('code','=','tabby')]).id,
                    "state_message": cancel_msg,
                }
            )
            self._set_canceled()
            return True
        elif paymentStatus == "rejected":
            error_msg = "Transaction Rejected"
            self.write(
                {
                    "provider_id": self.env['payment.provider'].search([('code', '=', 'tabby')]).id,
                    "state_message": error_msg,
                }
            )
            self._set_error(error_msg)
            return True

        else:
            error_msg = "tabby: Received unknown status for tabby reference %s, set as error:  %s" % (
                self.reference,
                paymentStatus,
            )
            _logger.info(error_msg)
            self.write(
                {
                    "provider_id": self.env['payment.provider'].search([('code','=','tabby')]).id,
                    "state_message": error_msg,
                }
            )
            self._set_error(error_msg)
            return False

    def tabby_s2s_capture_transaction(self):
        self.ensure_one()
        request_data = dict()
        request_data["order_id"] = self.provider_id
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

        _logger.info("capture_json_data %s" % capture_json_data)
        if capture_json_data.get("capture_id"):
            capture_msg = "tabby: Transaction has been captured with capture id {}".format(
                capture_json_data.get("capture_id")
            )
            self.write(
                {
                    "state_message": capture_msg,
                }
            )
            self._set_done()
            self._create_payment()

    def tabby_s2s_void_transaction(self):
        self.ensure_one()
        request_data = dict()
        request_data["total_amount"] = {
            "amount": self.amount,
            "currency": self.currency_id.name,
        }
        req_path = "/orders/{}/cancel".format(self.provider_id)
        cancel_response = self.provider_id._tabby_make_request(request_data, method="post", path=req_path)
        cancel_json_data = cancel_response.get("data")
        if cancel_json_data.get("cancel_id"):
            cancel_msg = "tabby: Transaction cancelled with cancelled id {}".format(cancel_json_data.get("cancel_id"))
            self.write(
                {
                    "state_message": cancel_msg,
                }
            )
            self._set_transaction_cancel()
