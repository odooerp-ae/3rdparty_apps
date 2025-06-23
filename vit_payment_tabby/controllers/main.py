# -*- coding: utf-8 -*-
import pprint
import logging
from requests import request as pyrequest

from odoo import http, _
from odoo.exceptions import ValidationError
from odoo.http import request

_logger = logging.getLogger(__name__)

class PaymentTabbyController(http.Controller):
    success_url      = "/payment/tabby/success"
    failure_url      = "/payment/tabby/failure"
    cancel_url       = "/payment/tabby/cancel"
    notification_url = "/payment/tabby/notification"

    @http.route(
        [success_url, failure_url, cancel_url],
        type="http", auth="public", csrf=False, website=True
    )
    def payment_checkout_tabby_return(self, **kwargs):
        _logger.info("tabby: return payload %s", pprint.pformat(kwargs))

        # 1) Lookup the transaction
        ref = kwargs.get("reference")
        if not ref:
            return request.redirect("/shop/cart")
        tx = request.env["payment.transaction"].sudo().search([
            ("reference","=",ref),
            ("provider_code","=","tabby"),
        ], limit=1)
        if not tx:
            return request.redirect("/shop/cart")

        # 2) Fetch Tabby API status
        try:
            headers = {"Authorization": f"Bearer {tx.provider_id.tabby_secret_key}"}
            res = pyrequest(
                "GET",
                f"https://api.tabby.ai/api/v2/payments/{kwargs.get('payment_id')}",
                headers=headers
            ).json()
        except Exception as e:
            raise ValidationError(_("Tabby: failed to fetch status:\n%s") % str(e))

        # 3) Decide the final status
        if request.httprequest.path == self.cancel_url:
            # **force** cancel when Tabby hits your cancel URL
            status = "cancel"
        else:
            raw = (res.get("status") or "").lower()
            if raw in ("created",):
                status = "pending"
            elif raw in ("authorized", "approved"):
                status = "authorized"
            elif raw in ("captured", "partially_captured"):
                status = "closed"
            elif raw in ("expired", "canceled", "cancelled", "declined"):
                status = "cancel"
            else:
                status = "pending"
        kwargs["paymentStatus"] = status
        kwargs["payment_data"]   = res
        _logger.info("tabby: using status %r (path=%s)", status, request.httprequest.path)

        # 4) If this is a Cancel, restore the cart now
        if status == "cancel" and tx.sale_order_ids:
            order = tx.sale_order_ids.sudo()[0]
            order.state                    = "draft"
            order.is_abandoned_cart        = False
            order.cart_recovery_email_sent = False
            request.session["sale_order_id"]               = order.id
            request.session["website_sale_order_line_ids"] = order.order_line.ids
            request.session["last_website_so_id"]          = order.id
            # Prevent the site from thinking “the order was just confirmed”
            request.session.pop("sale_last_order_id", None)
            _logger.info("tabby: cancel → restored cart for SO %s", order.name)

        # 5) Tell Odoo about the status update
        tx = tx.sudo()
        tx._handle_notification_data("tabby", kwargs)

        # 6) Render vs Redirect
        if status == "cancel":
            # inline‐render the standard status template with your red “You aborted…” banner
            return request.render(
                "payment.payment_status",
                {"tx": tx, "order": tx.sale_order_ids.sudo()[0] if tx.sale_order_ids else None}
            )
        # success/failure → go through the normal flow (which will clear the cart on done)
        return request.redirect(f"/payment/status?reference={ref}")


    @http.route([notification_url], type="json", auth="public", methods=["POST"], csrf=False)
    def tabby_notification(self, **kwargs):
        data = request.jsonrequest
        ref = data.get("reference")
        if not ref:
            raise ValidationError(_("Tabby notification missing reference:\n%s") % pprint.pformat(data))
        tx = request.env["payment.transaction"].sudo().search([("reference","=",ref)], limit=1)
        if not tx:
            raise ValidationError(_("Tabby notify with unknown reference:\n%s") % pprint.pformat(data))

        _logger.info("tabby: notification payload %r", data)
        # map raw Tabby → Odoo
        raw = (data.get("status") or "").lower()
        if raw in ("authorized", "approved"):
            data["status"] = "authorized"
        elif raw in ("captured", "partially_captured"):
            data["status"] = "closed"
        elif raw in ("expired", "canceled", "cancelled", "declined"):
            data["status"] = "cancel"
        elif raw in ("created",):
            data["status"] = "pending"
        else:
            data["status"] = "pending"

        try:
            tx._handle_notification_data("tabby", data)
        except Exception as e:
            _logger.error("tabby notify error: %s", e)
        return {"success": True}
