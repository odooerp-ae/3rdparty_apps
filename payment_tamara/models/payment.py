# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

import json
import logging
from datetime import datetime

# import typing_extensions
import requests
from odoo import models, api, fields, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools.float_utils import float_compare
from werkzeug import urls

from odoo.addons.payment_tamara.controllers.main import PaymentTamaraController

_logger = logging.getLogger(__name__)


class PaymentTamaraConnect(models.Model):
    _inherit = "payment.provider"

    APIEND = {
        "test_url": "https://api-sandbox.tamara.co",
        "live_url": "https://api.tamara.co",
    }

    code = fields.Selection(selection_add=[("tamara", "Tamara")], ondelete={"tamara": "set default"})
    tamara_merchant_token = fields.Char(string="Tamara Merchant Token")
    tamara_notification_token = fields.Char(string="Tamara Notification Token")
    tamara_order_id = fields.Char(string="Tamara Order ID")
    tamara_reference_id = fields.Char(string="Tamara Reference ID")

    def _compute_feature_support_fields(self):
        super()._compute_feature_support_fields()
        self.filtered(lambda p: p.code == "tamara").update(
            {
                "support_manual_capture": True,
                "support_refund": "partial",
                "support_tokenization": False,
            }
        )

    def _get_tamara_consumer_data(self, tamara_txn_values):
        consumer_data = dict()
        consumer_data["first_name"] = (
            tamara_txn_values.get("billing_partner_first_name")
            and tamara_txn_values.get("billing_partner_first_name")[:51]
        )
        consumer_data["last_name"] = (
            tamara_txn_values.get("billing_partner_last_name")
            and tamara_txn_values.get("billing_partner_last_name")[:51]
        )
        consumer_data["phone_number"] = (
            tamara_txn_values.get("billing_partner_phone") and tamara_txn_values.get("billing_partner_phone")[:33]
        )
        consumer_data["email"] = (
            tamara_txn_values.get("billing_partner_email") and tamara_txn_values.get("billing_partner_email")[:129]
        )
        return consumer_data

    def _get_tamara_shipping_address(self, tamara_txn_values):
        shipping_address = dict()
        shipping_address["first_name"] = tamara_txn_values.get("billing_partner_first_name")
        shipping_address["last_name"] = tamara_txn_values.get("billing_partner_last_name")
        shipping_address["line1"] = (
            tamara_txn_values.get("billing_partner").street and tamara_txn_values.get("billing_partner").street[:129]
        )
        shipping_address["line2"] = (
            tamara_txn_values.get("billing_partner").street2 and tamara_txn_values.get("billing_partner").street2[:129]
        )
        shipping_address["postal_code"] = tamara_txn_values.get("billing_partner_zip")
        shipping_address["city"] = tamara_txn_values.get("billing_partner_city")
        shipping_address["country_code"] = tamara_txn_values.get("billing_partner_country").code
        shipping_address["phone_number"] = tamara_txn_values.get("billing_partner_phone")
        return shipping_address

    def _get_tamara_tax_amount(self, tamara_txn_values):
        tax_amount = dict()
        tax_cost = (
            self.env["sale.order"]
            .sudo()
            .search([("name", "=", tamara_txn_values.get("reference").split("-")[0])])
            .amount_tax
        )
        tax_amount["amount"] = tax_cost
        tax_amount["currency"] = tamara_txn_values.get("currency").name
        return tax_amount

    def _get_tamara_total_amount(self, tamara_txn_values):
        total_amount = dict()
        total_amount["amount"] = tamara_txn_values.get("amount")
        total_amount["currency"] = tamara_txn_values.get("currency").name
        return total_amount

    def _get_tamara_shipping_amount(self, tamara_txn_values):
        shipping_amount = dict()
        sale_order = (
            self.env["sale.order"].sudo().search([("name", "=", tamara_txn_values.get("reference").split("-")[0])])
        )

        shipping_cost = sum(line.price_total for line in sale_order.order_line.filtered(lambda l: l.is_delivery))
        shipping_amount["amount"] = shipping_cost
        shipping_amount["currency"] = tamara_txn_values.get("currency").name
        return shipping_amount

    def _get_tamara_mechant_url(self, tamara_txn_values):
        merchant_urls = dict()
        reference = tamara_txn_values.get("reference")
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        merchant_urls["success"] = str(
            urls.url_join(base_url, PaymentTamaraController.success_url)
        ) + "?reference={}".format(reference)
        merchant_urls["failure"] = str(
            urls.url_join(base_url, PaymentTamaraController.failure_url)
        ) + "?reference={}".format(reference)
        merchant_urls["cancel"] = str(
            urls.url_join(base_url, PaymentTamaraController.cancel_url)
        ) + "?reference={}".format(reference)
        merchant_urls["notification"] = str(
            urls.url_join(base_url, PaymentTamaraController.notification_url)
        ) + "?reference={}".format(reference)
        return merchant_urls

    def _get_tamara_items_detail(self, tamara_txn_values):
        items_data = []
        order = self.env["sale.order"].sudo().search([("name", "=", tamara_txn_values.get("reference").split("-")[0])])
        for line in order.order_line:
            if line.product_id.type not in ["service"]:
                line_item = dict()
                line_item["reference_id"] = order.name + line.product_id.name
                line_item["type"] = line.product_id.categ_id.name
                line_item["name"] = line.product_id.name
                line_item["sku"] = line.product_id.default_code or line.product_id.hs_code
                line_item["quantity"] = int(line.product_uom_qty)
                line_item["total_amount"] = {
                    "amount": line.price_total,
                    "currency": tamara_txn_values.get("currency").name,
                }
                items_data.append(line_item)
        return items_data

    def _tamara_make_data(self, tamara_txn_values):
        data = dict()
        context_dict = dict(self._context)
        data["order_reference_id"] = tamara_txn_values.get("reference")
        data["total_amount"] = self._get_tamara_total_amount(tamara_txn_values)
        data["description"] = tamara_txn_values.get("reference")
        data["country_code"] = tamara_txn_values.get("partner_country").code
        data["payment_type"] = "PAY_BY_LATER"
        data["locale"] = context_dict.get("lang")
        data["items"] = self._get_tamara_items_detail(tamara_txn_values)
        data["consumer"] = self._get_tamara_consumer_data(tamara_txn_values)
        data["shipping_address"] = self._get_tamara_shipping_address(tamara_txn_values)
        data["tax_amount"] = self._get_tamara_tax_amount(tamara_txn_values)
        data["shipping_amount"] = self._get_tamara_shipping_amount(tamara_txn_values)
        data["merchant_url"] = self._get_tamara_mechant_url(tamara_txn_values)
        return data

    def get_payment_type(self, headers, api_end, path, request_data):
        # if self.state == 'test':
        api_end += path
        payment_type = "/payment-types"
        if request_data.get("country_code"):
            user_country_id = request_data["country_code"]
        else:
            user_country_id = self.env.user.partner_id.country_id.code

        if not user_country_id:
            user_country_id = self.company_id.country_id.code if self.company_id.country_id else ""
        _logger.info("######## User Country Code %s ############", user_country_id)
        response = requests.get(
            url=api_end + payment_type, headers=headers, data=json.dumps({"country": user_country_id})
        )
        return response

    def _tamara_send_request(self, request_data, method=None, path=None):
        HEADERS = {
            "Authorization": "Bearer " + self.tamara_merchant_token,
            "Content-Type": "application/json",
        }
        api_end = self.APIEND.get("test_url") if self.state == "test" else self.APIEND.get("live_url")

        try:
            if path == "/checkout":
                result = self.get_payment_type(HEADERS, api_end, path, request_data)
                content_result = json.loads(result.content)
                if not isinstance(content_result, list):
                    raise UserError(content_result.get("message"))
                payment_type = content_result[0].get("name", False)
                if payment_type:
                    request_data.update({"payment_type": payment_type})
            _logger.info("######## POST REQUEST DATA ##########%s", (request_data))
            if method == "post":
                # _logger.info(
                #     "######## API END ##########%s", api_end+path)
                # _logger.info(pprint.pprint(request_data))
                # _logger.info(
                #     "######## POST REQUEST DATA ##########%s", json.dumps(request_data))
                response = requests.post(url=api_end + path, headers=HEADERS, data=json.dumps(request_data))
                _logger.info("########POST RESPONSE DATA##########%s", response.text)
                return response
            elif method == "get":
                # _logger.info("########GET REQUEST DATA##########")
                response = requests.get(url=api_end + path, headers=HEADERS)
                _logger.info("########GET RESPONSE DATA##########%s", response.text)
                return response
        except Exception as e:
            _logger.warning("#WKDEBUG---TAMARA----Exception-----%r---------" % (e))
            raise UserError(e)

    def _tamara_verify_data(self, response):
        success = True
        data = dict()
        if response.status_code in range(200, 300):
            success = True
            data["success"] = success
            data["data"] = json.loads(response.text)
        else:
            success = False
            _logger.info("sdskks %s" % response.status_code)
            json_data = json.loads(response.text)
            data["success"] = success
            data["message"] = json_data.get("message")
            errors = []

            for error in json_data.get("errors", []):
                if error.get("error_code"):
                    errors.append(error.get("error_code"))
            data["errors"] = errors
        return data

    def _tamara_make_request(self, request_data, method=None, path=None):
        _logger.info("Tamara Request Data %r", request_data)
        response = self._tamara_send_request(request_data, method=method, path=path)
        resp_data = self._tamara_verify_data(response)

        if resp_data.get("success") == False:
            for error in resp_data.get("errors"):
                _logger.error("WK---Tamara-Err-Resp------%s", error)
            raise UserError(resp_data.get("message"))
        return resp_data

    def _get_tamara_txn_url(self, tamara_txn_values):
        request_data = self._tamara_make_data(tamara_txn_values)
        resp_data = self._tamara_make_request(request_data, method="post", path="/checkout")
        return resp_data.get("data")

    def tamara_form_generate_values(self, values):
        tamara_txn_values = dict(values)
        _logger.info("########Tamara form generate values##########")
        self.tamara_reference_id = tamara_txn_values.get("reference")
        response_data = self._get_tamara_txn_url(tamara_txn_values)
        self.tamara_order_id = response_data.get("order_id")
        tamara_txn_values["tamara_order_id"] = self.tamara_order_id
        tamara_txn_values["tamara_checkout_id"] = response_data.get("checkout_id")
        tamara_txn_values["tamara_checkout_url"] = response_data.get("checkout_url")
        return tamara_txn_values

    """Default method of the core"""

    def _get_default_payment_method_id(self, code):
        self.ensure_one()
        if self.code != "tamara":
            return super()._get_default_payment_method_id(self.code)
        return self.env.ref("payment_tamara.payment_tamara_connect").id


class PaymentTransactionTamara(models.Model):
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

    """Default methode of the core"""

    def _get_specific_rendering_values(self, processing_values):
        """Override of payment to return Alipay-specific rendering values.
        Note: self.ensure_one() from `_get_processing_values`
        :param dict processing_values: The generic and specific processing values of the transaction
        :return: The dict of acquirer-specific processing values
        :rtype: dict
        """

        res = super()._get_specific_rendering_values(processing_values)
        if self.provider_code != "tamara":
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
            txValues = self.provider_id.tamara_form_generate_values(processing_values)
            txValues.update({"tamara_form": txValues.get("tamara_checkout_url")})
        return txValues

    @api.model
    def _get_tx_from_notification_data(self, provider_code, notification_data):
        tx = super()._get_tx_from_notification_data(provider_code, notification_data)

        if provider_code != "tamara":
            return tx

        reference, orderId, paymentStatus = (
            notification_data.get("reference"),
            notification_data.get("orderId"),
            notification_data.get("paymentStatus"),
        )
        if not reference or not paymentStatus:
            error_msg = _("Tamara: received data with missing reference (%s) or paymentStatus (%s)") % (
                reference,
                paymentStatus,
            )
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        tx = self.search([("reference", "=", reference), ("provider_code", "=", "tamara")])
        if not tx or len(tx) > 1:
            error_msg = _("Tamara: received data for reference %s") % (reference)
            if not tx:
                error_msg += _("; no order found")
            else:
                error_msg += _("; multiple order found")
            _logger.info(error_msg)
            raise ValidationError(error_msg)
        return tx

    def _tamara_form_get_invalid_parameters(self, data):
        reference, orderId, paymentStatus = data.get("reference"), data.get("orderId"), data.get("paymentStatus")
        if paymentStatus == "canceled":
            return
        invalid_parameters = []
        req_path = "/orders/" + str(orderId)
        order_details = self.provider_id._tamara_make_request(False, method="get", path=req_path)
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

    # def _tamara_form_validate(self, data):
    # def _process_feedback_data(self, data):
    def _process_notification_data(self, data):
        super()._process_notification_data(data)
        if self.provider_code != "tamara":
            return
        reference, orderId, paymentStatus = data.get("reference"), data.get("orderId"), data.get("paymentStatus")
        if self.state == "done":
            _logger.warning("Tamara: trying to validate an already validated tx (ref %s)" % self.reference)
            return True

        self.check_payment_status_tamara(orderId, paymentStatus)

    def check_payment_status_tamara(self, orderId, paymentStatus):
        if paymentStatus == "approved":
            request_data = dict()
            request_data["orderId"] = orderId
            req_path = "/orders/{}/authorise".format(orderId)
            auth_response = self.provider_id._tamara_send_request(request_data, method="post", path=req_path)
            resp_data = self.provider_id._tamara_verify_data(auth_response)

            if self.sale_order_ids:
                shopping_carts = self.env["shopping.cart"].search(
                    [("sale_order_id", "in", self.sale_order_ids.ids), ("status", "!=", "completed")]
                )
                if shopping_carts:
                    shopping_carts.write({"status": "completed"})

            if resp_data.get("success") == False:
                self.write({"provider_reference": orderId})
                self._set_pending(resp_data.get("message"))
                return True
            else:
                auth_json_data = resp_data.get("data")
                auth_status = auth_json_data.get("status")
                self.write({"provider_reference": orderId})

                if auth_status == "authorised":
                    _logger.info("Before Capture")
                    self._set_authorized()
                    self.action_capture()
                    _logger.info("After Capture")
                    return True
                elif auth_status == "fully_captured":
                    capture_msg = "Tamara: Transaction already fully captured"
                    self._set_done(capture_msg)
                    self._finalize_post_processing()
                    return True
                else:
                    self._set_pending()
                    return True

        elif paymentStatus == "canceled":
            cancel_msg = "Tamara: Transaction cancelled by customer"
            self.write({"provider_reference": orderId})
            self._set_canceled(cancel_msg)
            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()

            return True

        elif paymentStatus == "declined":
            error_msg = "Transaction Declined"
            self.write({"provider_reference": orderId})
            self._set_error(error_msg)

            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()

            return True

        elif paymentStatus == "expired":
            error_msg = "Checkout session is expired"
            self.write({"provider_reference": orderId})
            self._set_error(error_msg)

            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()

            return True

        elif paymentStatus == "single_checkout_recoverable":
            error_msg = "Single Checkout Recoverable"
            self.write({"provider_reference": orderId})
            self._set_error(error_msg)

            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()

            return True
        else:
            error_msg = "Tamara: Received unknown status for Tamara reference %s, set as error:  %s" % (
                self.reference,
                paymentStatus,
            )
            _logger.info(error_msg)
            self.write({"provider_reference": orderId})
            self._set_error(error_msg)

            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()
            return False

    def _process_notification_data_custom(self, data):
        reference, orderId, paymentStatus = (
            data.get("order_reference_id"),
            data.get("order_id"),
            data.get("order_status"),
        )
        if self.state == "done":
            _logger.warning("Tamara: trying to validate an already validated tx (ref %s)" % self.reference)
            return True

        self.check_payment_status_tamara(orderId, paymentStatus)

    def _send_capture_request(self):
        super()._send_capture_request()

        if self.provider_code != "tamara":
            return

        _logger.info("Run Send Capture Request")
        request_data = dict()
        request_data["order_id"] = self.provider_reference
        request_data["total_amount"] = {
            "amount": float(self.amount),
            "currency": self.currency_id.name,
        }
        request_data["shipping_info"] = {
            "shipped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%Sz"),
            "shipping_company": "Delivery Carrier",
        }
        req_path = "/payments/capture"
        capture_response = self.provider_id._tamara_make_request(request_data, method="post", path=req_path)
        capture_json_data = capture_response.get("data")
        if capture_json_data.get("capture_id"):
            capture_msg = "Tamara: Transaction has been captured with capture id {}".format(
                capture_json_data.get("capture_id")
            )
            self._set_done(capture_msg)
            self._finalize_post_processing()

    def _send_void_request(self):
        super()._send_void_request()

        if self.provider_code != "tamara":
            return

        request_data = dict()
        request_data["total_amount"] = {
            "amount": float(self.amount),
            "currency": self.currency_id.name,
        }
        req_path = "/orders/{}/cancel".format(self.provider_reference)
        cancel_response = self.provider_id._tamara_make_request(request_data, method="post", path=req_path)
        cancel_json_data = cancel_response.get("data")
        if cancel_json_data.get("cancel_id"):
            cancel_msg = "Tamara: Transaction cancelled with cancelled id {}".format(cancel_json_data.get("cancel_id"))
            self._set_cancel(cancel_msg)

            if self.sale_order_ids:
                self.sale_order_ids.action_cancel()
