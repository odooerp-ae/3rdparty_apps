import json
import logging
from datetime import datetime

import requests

from odoo import _, api, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SaleOrderCust(models.Model):
    _inherit = "sale.order"

    def unlink(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)], limit=1)
        )
        if not sf_config:
            raise ValidationError(
                _(
                    "There is no Salesforce instance for this company '%s'."
                    % (self.env.company.name)
                )
            )

        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

            if sf_access_token:
                headers = sf_config.get_sf_headers(type=True)

            for record in self:
                if (record.x_salesforce_id or record.sale_order_salesforce_id) and (
                    record.state == "draft" or record.state == "cancel"
                ):
                    endpoint = "/services/data/v52.0/sobjects/Quote/" + str(
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
                            "Quote is deleted from SALESFORCE==========================="
                        )

                    if res.status_code == 404 or res.status_code == 400:
                        endpoint = "/services/data/v52.0/sobjects/Order/" + str(
                            record.sale_order_salesforce_id
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
                                "Order is deleted from SALESFORCE==========================="
                            )
        return super().unlink()

    def sendQuoteDataToSf(self, quote_dict, is_cron=False):
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

        # GET ACCESS TOKEN
        endpoint = None
        sf_access_token = None
        realmId = None
        is_create = False
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token
        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = "/services/data/v40.0/sobjects/Quote"

            payload = json.dumps(quote_dict)
            if self.x_salesforce_id:
                # Try Updating it if already exported
                res = requests.request(
                    "PATCH",
                    sf_config.sf_url + endpoint + "/" + self.x_salesforce_id,
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
                                        "type": "sale_quotation",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully:- Updated data",
                                    },
                                )
                            ]
                        }
                    )
                    _logger.info(
                        "Quotation is updated in salesforce %s", self.x_salesforce_id
                    )

                    return self.x_salesforce_id
                else:
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_quotation",
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
                    self.x_salesforce_id = parsed_resp.get("id")
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "sale_quotation",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully",
                                    },
                                )
                            ]
                        }
                    )
                    _logger.info(
                        "Quotation is created in salesforce %s", parsed_resp.get("id")
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
                                        "type": "sale_quotation",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False

    def sendQuoteLineDataToSf(
        self, quote_line_dict, line_sf_id, line_id, is_cron=False
    ):
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
        # GET ACCESS TOKEN

        endpoint = None
        sf_access_token = None
        realmId = None
        is_create = False
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = "/services/data/v40.0/sobjects/quotelineitem"

            payload = json.dumps(quote_line_dict)
            if line_sf_id:
                # Try Updating it if already exported
                res = requests.request(
                    "PATCH",
                    sf_config.sf_url + endpoint + "/" + line_sf_id,
                    headers=headers,
                    data=payload,
                    timeout=180,
                )
                if res.status_code == 204:
                    quote_line = self.env["sale.order.line"].search(
                        [("id", "=", line_id)]
                    )
                    quote_line.x_is_updated = True

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
                    quote_line = self.env["sale.order.line"].search(
                        [("id", "=", line_id)]
                    )
                    quote_line.x_salesforce_exported = True
                    quote_line.x_salesforce_id = parsed_resp.get("id")
                    return parsed_resp.get("id")
                else:
                    return False

    def exportQuotations_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))

        if not self.contract_id and self.state == "sale" and not is_from_cron:
            raise UserError(_("Please add contract1"))

        if not self.opportunity_id and not is_from_cron:
            raise UserError(_("Please add Opportunity"))

        # PREPARE DICT FOR SENDING TO SALESFORCE
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
            raise ValidationError(_("There is no Salesforce instance"))

        quote_dict = {}
        quote_line_list = []
        quote_line_dict = {}

        if self.opportunity_id and self.opportunity_id.x_salesforce_id_oppo:
            quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
        elif self.opportunity_id and not self.opportunity_id.x_salesforce_id_oppo:
            opportunity_export = self.opportunity_id.exportOpportunity_to_sf()
            quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
        if self.contract_id and self.contract_id.x_salesforce_id:
            quote_dict["ContractId"] = self.contract_id.x_salesforce_id
        elif self.contract_id and not self.contract_id.x_salesforce_id:
            contract_export = self.contract_id.exportContract_to_sf()
            quote_dict["ContractId"] = self.contract_id.x_salesforce_id
        quote_dict["Status"] = "Draft"

        # Create a entry in price-book in salesforce
        if self.name:
            quote_dict["Name"] = self.name
        if self.amount_tax:
            quote_dict["Tax"] = self.amount_tax
        if self.validity_date:
            quote_dict["ExpirationDate"] = str(self.validity_date)
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

        # Get Standard Price-book Id
        endpoint = "/services/data/v40.0/query/?q=select Id from pricebook2 where name = '{}'".format(
            "Standard Price Book"
        )
        res = requests.request(
            "GET", sf_config.sf_url + endpoint, headers=headers, timeout=180
        )
        if res.status_code == 200:
            parsed_resp = json.loads(str(res.text))
            if parsed_resp.get("records") and parsed_resp.get("records")[0].get("Id"):
                quote_dict["Pricebook2Id"] = parsed_resp.get("records")[0].get("Id")

        result = self.sendQuoteDataToSf(quote_dict, is_cron=is_from_cron)
        line_sf_id = ""
        if result:
            if self.order_line:
                for line in self.order_line:
                    if line.x_salesforce_id and line.quotation_order_line_updated:
                        delete_quotation_line = (
                            self.delete_quotation_line_to_salesforce(
                                line, line.x_salesforce_id, is_cron=is_from_cron
                            )
                        )
                        if delete_quotation_line:
                            if line.product_id and line.product_id.x_salesforce_id:
                                quote_line_dict = {
                                    "Product2Id": line.product_id.x_salesforce_id,
                                    "Quantity": line.product_uom_qty,
                                    "UnitPrice": line.price_unit,
                                    "QuoteId": self.x_salesforce_id,
                                }

                            elif (
                                line.product_id and not line.product_id.x_salesforce_id
                            ):
                                line.product_id.exportProduct_to_sf(
                                    is_from_cron=is_from_cron
                                )
                                quote_line_dict = {
                                    "Product2Id": line.product_id.x_salesforce_id,
                                    "Quantity": line.product_uom_qty,
                                    "UnitPrice": line.price_unit,
                                    "QuoteId": self.x_salesforce_id,
                                }
                            line_id = line.id
                            # Create a entry in pricebook in salesforce
                            if sf_config.sf_access_token:
                                sf_access_token = sf_config.sf_access_token

                            if sf_access_token:
                                headers = sf_config.get_sf_headers(type=True)

                            salesforce_pbe = ""
                            pricebook_id = ""
                            quote_data = requests.request(
                                "GET",
                                sf_config.sf_url
                                + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
                                headers=headers,
                                timeout=180,
                            )
                            if quote_data.text:
                                quote_data = json.loads(str(quote_data.text))
                                pricebook_id = quote_data.get("records")[0].get(
                                    "Pricebook2Id"
                                )
                            PricebookEntryData = requests.request(
                                "GET",
                                sf_config.sf_url
                                + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
                                    quote_line_dict["Product2Id"]
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
                                quote_line_dict["PricebookEntryId"] = (
                                    line.product_id.x_salesforce_pbe
                                )
                            if line.discount:
                                quote_line_dict["Discount"] = line.discount
                            if quote_line_dict:
                                result = self.sendQuoteLineDataToSf(
                                    quote_line_dict,
                                    line_sf_id,
                                    line_id,
                                    is_cron=is_from_cron,
                                )
                            self.x_salesforce_exported = True

                    elif not line.x_salesforce_id:
                        if line.product_id and line.product_id.x_salesforce_id:
                            quote_line_dict = {
                                "Product2Id": line.product_id.x_salesforce_id,
                                "Quantity": line.product_uom_qty,
                                "UnitPrice": line.price_unit,
                                "QuoteId": self.x_salesforce_id,
                            }
                        elif line.product_id and not line.product_id.x_salesforce_id:
                            line.product_id.exportProduct_to_sf(
                                is_from_cron=is_from_cron
                            )
                            quote_line_dict = {
                                "Product2Id": line.product_id.x_salesforce_id,
                                "Quantity": line.product_uom_qty,
                                "UnitPrice": line.price_unit,
                                "QuoteId": self.x_salesforce_id,
                            }
                        line_id = line.id
                        # Create a entry in price-book in salesforce
                        if sf_config.sf_access_token:
                            sf_access_token = sf_config.sf_access_token

                        if sf_access_token:
                            headers = sf_config.get_sf_headers(type=True)

                        salesforce_pbe = ""
                        pricebook_id = ""
                        quote_data = requests.request(
                            "GET",
                            sf_config.sf_url
                            + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
                            headers=headers,
                            timeout=180,
                        )
                        if quote_data.text:
                            quote_data = json.loads(str(quote_data.text))
                            pricebook_id = quote_data.get("records")[0].get(
                                "Pricebook2Id"
                            )
                        PricebookEntryData = requests.request(
                            "GET",
                            sf_config.sf_url
                            + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
                                quote_line_dict["Product2Id"]
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
                            quote_line_dict["PricebookEntryId"] = (
                                line.product_id.x_salesforce_pbe
                            )
                        if line.discount:
                            quote_line_dict["Discount"] = line.discount
                        if quote_line_dict:
                            result = self.sendQuoteLineDataToSf(
                                quote_line_dict,
                                line_sf_id,
                                line_id,
                                is_cron=is_from_cron,
                            )
                        self.x_salesforce_exported = True

    def delete_quotation_line_to_salesforce(self, line_id, sf_id, is_cron=False):
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

                endpoint = "/services/data/v52.0/sobjects/QuoteLineItem/" + str(sf_id)
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
                        "Quotation order line is deleted from SALESFORCE ==========================="
                    )
                    line_id.quotation_order_line_updated = False
                    line_id.x_salesforce_id = False
                    return True
                else:
                    return False

    @api.model
    def _scheduler_export_quotes_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            quotes = self.search(
                [("state", "in", ("draft", "sent"))], limit=sf_config.export_limit
            )
        else:
            quotes = self.search([("state", "in", ("draft", "sent"))])

        for quote in quotes:
            try:
                quote.exportQuotations_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  exporting quotes to SALESFORCE %s", e
                )
