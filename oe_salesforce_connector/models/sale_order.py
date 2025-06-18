import json
import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrderCust(models.Model):
    _inherit = "sale.order"

    x_salesforce_id = fields.Char("Salesforce Id", copy=False)
    sale_order_salesforce_id = fields.Char(copy=False)
    contract_id = fields.Many2one("sf.contract", string="Contract")
    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce", default=False, copy=False
    )
    x_is_updated = fields.Boolean("x_is_updated", default=False, copy=False)
    x_salesforce_pbe = fields.Char("Salesforce Pricelist", copy=False)
    x_salesforce_ref = fields.Char("Salesforce Ref", copy=False)
    x_salesforce_quote_name = fields.Char("Quote Name", copy=False)
    x_order_shipping_address = fields.Text("Order Shipping Address", copy=False)
    x_order_billing_address = fields.Text("Order Billing Address", copy=False)

    @api.onchange("contract_id")
    def onchange_contract_id(self):
        if self.contract_id:
            if self.date_order.date() < self.contract_id.contract_start_date:
                raise UserError(
                    _(
                        "Order Start Date can't be earlier than the contract's start date.: Order Start Date."
                    )
                )
            if self.partner_id != self.contract_id.parent_id:
                raise UserError(
                    _("Order customer and contract customer should be same")
                )

    def sendDataToSf(self, order_dict, is_cron=False):
        if is_cron:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("is_default_instance", "=", True)], limit=1)
            )
        else:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

        if not sf_config and not is_cron:
            raise ValidationError(_("There is no Salesforce instance"))

        # """ GET ACCESS TOKEN """
        endpoint = None
        sf_access_token = None
        realmId = None
        is_create = False
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = "/services/data/v40.0/sobjects/Order"

            payload = json.dumps(order_dict)

            if self.sale_order_salesforce_id:
                # """ Try Updating it if already exported """
                res = requests.request(
                    "PATCH",
                    sf_config.sf_url + endpoint + "/" + self.sale_order_salesforce_id,
                    headers=headers,
                    data=payload,
                    timeout=180,
                )

                if res.status_code in (200, 201, 204):
                    self.x_is_updated = True
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_order",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully:- Updated data",
                                    },
                                )
                            ]
                        }
                    )
                    _logger.info(
                        "Sale order updated in salesforce %s",
                        self.sale_order_salesforce_id,
                    )
                    return self.sale_order_salesforce_id
                else:
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_order",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export the Updated data:- Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
            else:
                res = requests.request(
                    "POST",
                    sf_config.sf_url + endpoint,
                    headers=headers,
                    data=payload,
                    timeout=180,
                )
                if res.status_code in (200, 201):
                    parsed_resp = json.loads(str(res.text))
                    self.x_salesforce_exported = True
                    self.sale_order_salesforce_id = parsed_resp.get("id")
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_order",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully",
                                    },
                                )
                            ]
                        }
                    )
                    _logger.info(
                        "Sale order created in salesforce %s", parsed_resp.get("id")
                    )

                    return parsed_resp.get("id")
                else:
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_order",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False

    def sendLineDataToSf(self, order_line_dict, line_sf_id, line_id, is_cron=False):
        if is_cron:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("is_default_instance", "=", True)], limit=1)
            )
        else:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

        if not sf_config and not is_cron:
            raise ValidationError(_("There is no Salesforce instance"))

        # """ GET ACCESS TOKEN """
        endpoint = None
        sf_access_token = None
        realmId = None
        is_create = False
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = "/services/data/v40.0/sobjects/orderitem"

            payload = json.dumps(order_line_dict)
            if line_sf_id:
                # """ Try Updating it if already exported """
                res = requests.request(
                    "PATCH",
                    sf_config.sf_url + endpoint + "/" + line_sf_id,
                    headers=headers,
                    data=payload,
                    timeout=180,
                )
                if res.status_code == 204:
                    order_line = self.env["sale.order.line"].search(
                        [("id", "=", line_id)]
                    )
                    order_line.x_is_updated = True
                    _logger.info("Sale order line updated in odoo %s", line_sf_id)
            else:
                res = requests.request(
                    "POST",
                    sf_config.sf_url + endpoint,
                    headers=headers,
                    data=payload,
                    timeout=180,
                )
                if res.status_code in [200, 201]:
                    parsed_resp = json.loads(str(res.text))
                    order_line = self.env["sale.order.line"].search(
                        [("id", "=", line_id)]
                    )
                    order_line.x_salesforce_exported = True
                    order_line.sale_order_line_salesforce_id = parsed_resp.get("id")
                    _logger.info(
                        "Sale order line created in odoo %s",
                        order_line.sale_order_line_salesforce_id,
                    )

                    return parsed_resp.get("id")
                else:
                    return False

    def exportSaleOrder_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))
        if not self.contract_id and not is_from_cron:
            raise UserError(_("Please add contract2"))

        # """ PREPARE DICT FOR SENDING TO SALESFORCE """
        if is_from_cron:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("is_default_instance", "=", True)], limit=1)
            )
        else:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

        if not sf_config and not is_from_cron:
            raise ValidationError(_("There is no Salesforce instance."))

        order_dict = {}
        order_line_list = []
        order_line_dict = {}
        if self.date_order:
            order_dict["EffectiveDate"] = str(self.date_order.date())
        if self.partner_id and self.partner_id.x_salesforce_id:
            order_dict["AccountId"] = str(self.partner_id.x_salesforce_id)
        elif self.partner_id and not self.partner_id.x_salesforce_id:
            partner_export = self.partner_id.exportPartner_to_sf()
            order_dict["AccountId"] = str(self.partner_id.x_salesforce_id)
        if self.contract_id and self.contract_id.x_salesforce_id:
            order_dict["ContractId"] = self.contract_id.x_salesforce_id
        elif self.contract_id and not self.contract_id.x_salesforce_id:
            contract_export = self.contract_id.exportContract_to_sf()
            order_dict["ContractId"] = self.contract_id.x_salesforce_id
        order_dict["Status"] = "Draft"
        # """ Create a entry in price-book in salesforce"""
        # if self.amount_tax:
        #     order_dict['Tax'] = self.amount_tax
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

        # """ Get Standard Price-book Id"""
        endpoint = "/services/data/v40.0/query/?q=select Id from pricebook2 where name = '{}'".format(
            "Standard Price Book"
        )
        res = requests.request(
            "GET", sf_config.sf_url + endpoint, headers=headers, timeout=180
        )
        if res.status_code == 200:
            parsed_resp = json.loads(str(res.text))
            if parsed_resp.get("records") and parsed_resp.get("records")[0].get("Id"):
                order_dict["Pricebook2Id"] = parsed_resp.get("records")[0].get("Id")
        result = self.sendDataToSf(order_dict, is_cron=is_from_cron)
        line_sf_id = ""
        if result:
            if self.order_line:
                for line in self.order_line:
                    if (
                        line.sale_order_line_salesforce_id
                        and line.sale_order_line_updated
                    ):
                        delete_so_line = self.delete_sale_order_line_to_salesforce(
                            line,
                            line.sale_order_line_salesforce_id,
                            is_cron=is_from_cron,
                        )
                        if delete_so_line:
                            if line.product_id and line.product_id.x_salesforce_id:
                                order_line_dict = {
                                    "Product2Id": line.product_id.x_salesforce_id,
                                    "Quantity": line.product_uom_qty,
                                    "UnitPrice": line.price_unit,
                                    "OrderId": self.sale_order_salesforce_id,
                                }
                            elif (
                                line.product_id and not line.product_id.x_salesforce_id
                            ):
                                line.product_id.exportProduct_to_sf(
                                    is_from_cron=is_from_cron
                                )
                                order_line_dict = {
                                    "Product2Id": line.product_id.x_salesforce_id,
                                    "Quantity": line.product_uom_qty,
                                    "UnitPrice": line.price_unit,
                                    "OrderId": self.sale_order_salesforce_id,
                                }
                            line_id = line.id
                            line_sf_id = line.sale_order_line_salesforce_id
                            if sf_config.sf_access_token:
                                sf_access_token = sf_config.sf_access_token

                            if sf_access_token:
                                headers = sf_config.get_sf_headers(type=True)
                            salesforce_pbe = ""
                            pricebook_id = ""
                            order_data = requests.request(
                                "GET",
                                sf_config.sf_url
                                + f"/services/data/v40.0/query/?q=select Pricebook2Id from Order where Id = '{self.sale_order_salesforce_id}'",
                                headers=headers,
                                timeout=180,
                            )
                            if order_data.text:
                                order_data = json.loads(str(order_data.text))
                                pricebook_id = order_data.get("records")[0].get(
                                    "Pricebook2Id"
                                )
                            PricebookEntryData = requests.request(
                                "GET",
                                sf_config.sf_url
                                + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
                                    order_line_dict["Product2Id"]
                                ),
                                headers=headers,
                                timeout=180,
                            )

                            if PricebookEntryData.text:
                                pricebookentry_data = json.loads(
                                    str(PricebookEntryData.text)
                                )
                                for pricebook in pricebookentry_data.get("records"):
                                    line.product_id.x_salesforce_pbe = pricebook.get(
                                        "Id"
                                    )
                                order_line_dict["PricebookEntryId"] = (
                                    line.product_id.x_salesforce_pbe
                                )

                        elif line.product_id and not line.product_id.x_salesforce_id:
                            line.product_id.exportProduct_to_sf()
                            order_line_dict = {
                                "Product2Id": line.product_id.x_salesforce_id,
                                "Quantity": line.product_uom_qty,
                                "UnitPrice": line.price_unit,
                            }

                        line_sf_id = line.sale_order_line_salesforce_id
                        line_id = line.id
                        if order_line_dict:
                            result = self.sendLineDataToSf(
                                order_line_dict,
                                line_sf_id,
                                line_id,
                                is_cron=is_from_cron,
                            )
                        self.x_salesforce_exported = True
                    elif not line.sale_order_line_salesforce_id:
                        if line.product_id and line.product_id.x_salesforce_id:
                            order_line_dict = {
                                "Product2Id": line.product_id.x_salesforce_id,
                                "Quantity": line.product_uom_qty,
                                "UnitPrice": line.price_unit,
                                "OrderId": self.sale_order_salesforce_id,
                            }

                        elif line.product_id and not line.product_id.x_salesforce_id:
                            line.product_id.exportProduct_to_sf()
                            order_line_dict = {
                                "Product2Id": line.product_id.x_salesforce_id,
                                "Quantity": line.product_uom_qty,
                                "UnitPrice": line.price_unit,
                                "OrderId": self.sale_order_salesforce_id,
                            }
                        line_id = line.id
                        line_sf_id = line.sale_order_line_salesforce_id

                        # """ Create a entry in price-book in salesforce"""
                        if sf_config.sf_access_token:
                            sf_access_token = sf_config.sf_access_token

                        if sf_access_token:
                            headers = sf_config.get_sf_headers(type=True)
                        salesforce_pbe = ""
                        pricebook_id = ""
                        order_data = requests.request(
                            "GET",
                            sf_config.sf_url
                            + f"/services/data/v40.0/query/?q=select Pricebook2Id from Order where Id = '{self.sale_order_salesforce_id}'",
                            headers=headers,
                            timeout=180,
                        )
                        if order_data.text:
                            order_data = json.loads(str(order_data.text))
                            pricebook_id = order_data.get("records")[0].get(
                                "Pricebook2Id"
                            )
                        PricebookEntryData = requests.request(
                            "GET",
                            sf_config.sf_url
                            + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
                                order_line_dict["Product2Id"]
                            ),
                            headers=headers,
                            timeout=180,
                        )

                        if PricebookEntryData.text:
                            pricebookentry_data = json.loads(
                                str(PricebookEntryData.text)
                            )
                            for pricebook in pricebookentry_data.get("records"):
                                line.product_id.x_salesforce_pbe = pricebook.get("Id")
                            order_line_dict["PricebookEntryId"] = (
                                line.product_id.x_salesforce_pbe
                            )
                        if order_line_dict:
                            result = self.sendLineDataToSf(
                                order_line_dict,
                                line_sf_id,
                                line_id,
                                is_cron=is_from_cron,
                            )
                    self.x_salesforce_exported = True

                    # Export attachments to Salesforce (after exporting sale order and lines)
                    if self.sale_order_salesforce_id:
                        try:
                            export_result = self._export_attachments_to_sf(
                                sf_config=sf_config,
                                sf_record_id=self.sale_order_salesforce_id,
                                api_version="v52.0",  # adjust if needed
                                timeout=180,
                            )
                            if export_result:
                                _logger.info(
                                    f"Attachments successfully exported for Sale Order {self.name}."
                                )
                            else:
                                _logger.warning(
                                    f"Attachments were not fully exported for Sale Order {self.name}."
                                )
                        except Exception as e:
                            _logger.error(
                                f"Error exporting attachments for Sale Order {self.name}: {e}"
                            )

    def delete_sale_order_line_to_salesforce(self, line_id, sf_id, is_cron=False):
        if is_cron:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("is_default_instance", "=", True)], limit=1)
            )
        else:
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

            if sf_access_token:
                headers = sf_config.get_sf_headers(type=True)

                endpoint = "/services/data/v52.0/sobjects/orderitem/" + str(sf_id)
                res = requests.request(
                    "DELETE", sf_config.sf_url + endpoint, headers=headers, timeout=180
                )
                if (
                    res.status_code == 200
                    or res.status_code == 201
                    or res.status_code == 204
                ):
                    _logger.info(
                        "Sale order line is deleted from SALESFORCE==========================="
                    )
                    line_id.sale_order_line_updated = False
                    line_id.sale_order_line_salesforce_id = False
                    return True
                else:
                    return False

    @api.model
    def _scheduler_export_orders_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance.")
            return False

        if sf_config.export_limit:
            orders = self.search(
                [("state", "in", ("sale", "done"))], limit=sf_config.export_limit
            )
        else:
            orders = self.search([("state", "in", ("sale", "done"))])
        for order in orders:
            try:
                order.exportSaleOrder_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  exporting orders to SALESFORCE %s", e
                )

    def exportToSalesForce(self):
        if len(self) > 1:
            raise UserError(_("Please Select 1 record to Export"))

        if self.state in ("draft", "sent"):
            self.exportQuotations_to_sf()
        elif self.state in ("sale", "done", "cancel"):
            self.exportSaleOrder_to_sf()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    x_salesforce_id = fields.Char("Salesforce Id", copy=False)
    sale_order_line_salesforce_id = fields.Char(copy=False)
    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce", default=False, copy=False
    )
    x_is_updated = fields.Boolean("x_is_updated", default=False, copy=False)
    sale_order_line_updated = fields.Boolean("Sale order is updated", default=False)
    quotation_order_line_updated = fields.Boolean("Quotation is updated", default=False)
    sf_shipping_cost_line = fields.Boolean("Shipping Cost Line", copy=False)

    def write(self, vals):
        for rec in self:
            if rec.state == "draft" and rec.x_salesforce_id:
                vals["quotation_order_line_updated"] = True
            elif rec.state == "sale" and rec.sale_order_line_salesforce_id:
                vals["sale_order_line_updated"] = True
        return super().write(vals)

    def unlink(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)], limit=1)
        )
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

            if sf_access_token:
                headers = sf_config.get_sf_headers(type=True)

            for record in self:
                if (
                    record.x_salesforce_id or record.sale_order_line_salesforce_id
                ) and (
                    record.order_id.state == "draft"
                    or record.order_id.state == "cancel"
                ):
                    endpoint = "/services/data/v52.0/sobjects/QuoteLineItem/" + str(
                        record.x_salesforce_id
                    )
                    res = requests.request(
                        "DELETE",
                        sf_config.sf_url + endpoint,
                        headers=headers,
                        timeout=180,
                    )
                    if (
                        res.status_code == 200
                        or res.status_code == 201
                        or res.status_code == 204
                    ):
                        _logger.info(
                            "Quote Line is deleted from SALESFORCE==========================="
                        )

                    if res.status_code == 404 or res.status_code == 400:
                        endpoint = "/services/data/v52.0/sobjects/OrderItem/" + str(
                            record.sale_order_line_salesforce_id
                        )
                        res = requests.request(
                            "DELETE",
                            sf_config.sf_url + endpoint,
                            headers=headers,
                            timeout=180,
                        )
                        if (
                            res.status_code == 200
                            or res.status_code == 201
                            or res.status_code == 204
                        ):
                            _logger.info(
                                "Order Line is deleted from SALESFORCE==========================="
                            )

        return super().unlink()
