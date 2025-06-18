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

    # def exportQuotations_to_sf(self, is_from_cron=False):
    #     if len(self) > 1 and not is_from_cron:
    #         raise UserError(_("Please Select 1 record to Export"))

    #     if not self.contract_id and self.state == "sale" and not is_from_cron:
    #         raise UserError(_("Please add contract1"))

    #     if not self.opportunity_id and not is_from_cron:
    #         raise UserError(_("Please add Opportunity"))

    #     # PREPARE DICT FOR SENDING TO SALESFORCE
    #     if is_from_cron:
    #         sf_config = (
    #             self.env["salesforce.instance"]
    #             .sudo()
    #             .search([("is_default_instance", "=", True)], limit=1)
    #         )
    #     else:
    #         sf_config = (
    #             self.env["salesforce.instance"]
    #             .sudo()
    #             .search([("company_id", "=", self.env.company.id)], limit=1)
    #         )

    #     if not sf_config and not is_from_cron:
    #         raise ValidationError(_("There is no Salesforce instance"))

    #     quote_dict = {}
    #     quote_line_list = []
    #     quote_line_dict = {}

    #     if self.opportunity_id and self.opportunity_id.x_salesforce_id_oppo:
    #         quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
    #     elif self.opportunity_id and not self.opportunity_id.x_salesforce_id_oppo:
    #         opportunity_export = self.opportunity_id.exportOpportunity_to_sf()
    #         quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
    #     if self.contract_id and self.contract_id.x_salesforce_id:
    #         quote_dict["ContractId"] = self.contract_id.x_salesforce_id
    #     elif self.contract_id and not self.contract_id.x_salesforce_id:
    #         contract_export = self.contract_id.exportContract_to_sf()
    #         quote_dict["ContractId"] = self.contract_id.x_salesforce_id
    #     quote_dict["Status"] = "Draft"

    #     # Create a entry in price-book in salesforce
    #     if self.name:
    #         quote_dict["Name"] = self.name
    #     if self.amount_tax:
    #         quote_dict["Tax"] = self.amount_tax
    #     if self.validity_date:
    #         quote_dict["ExpirationDate"] = str(self.validity_date)
    #     if sf_config.sf_access_token:
    #         sf_access_token = sf_config.sf_access_token

    #     if sf_access_token:
    #         headers = sf_config.get_sf_headers(type=True)

    #     # Get Standard Price-book Id
    #     endpoint = "/services/data/v40.0/query/?q=select Id from pricebook2 where name = '{}'".format(
    #         "Standard Price Book"
    #     )
    #     res = requests.request(
    #         "GET", sf_config.sf_url + endpoint, headers=headers, timeout=180
    #     )
    #     if res.status_code == 200:
    #         parsed_resp = json.loads(str(res.text))
    #         if parsed_resp.get("records") and parsed_resp.get("records")[0].get("Id"):
    #             quote_dict["Pricebook2Id"] = parsed_resp.get("records")[0].get("Id")

    #     result = self.sendQuoteDataToSf(quote_dict, is_cron=is_from_cron)
    #     line_sf_id = ""
    #     if result:
    #         if self.order_line:
    #             for line in self.order_line:
    #                 if line.x_salesforce_id and line.quotation_order_line_updated:
    #                     delete_quotation_line = (
    #                         self.delete_quotation_line_to_salesforce(
    #                             line, line.x_salesforce_id, is_cron=is_from_cron
    #                         )
    #                     )
    #                     if delete_quotation_line:
    #                         if line.product_id and line.product_id.x_salesforce_id:
    #                             quote_line_dict = {
    #                                 "Product2Id": line.product_id.x_salesforce_id,
    #                                 "Quantity": line.product_uom_qty,
    #                                 "UnitPrice": line.price_unit,
    #                                 "QuoteId": self.x_salesforce_id,
    #                             }

    #                         elif (
    #                             line.product_id and not line.product_id.x_salesforce_id
    #                         ):
    #                             line.product_id.exportProduct_to_sf(
    #                                 is_from_cron=is_from_cron
    #                             )
    #                             quote_line_dict = {
    #                                 "Product2Id": line.product_id.x_salesforce_id,
    #                                 "Quantity": line.product_uom_qty,
    #                                 "UnitPrice": line.price_unit,
    #                                 "QuoteId": self.x_salesforce_id,
    #                             }
    #                         line_id = line.id
    #                         # Create a entry in pricebook in salesforce
    #                         if sf_config.sf_access_token:
    #                             sf_access_token = sf_config.sf_access_token

    #                         if sf_access_token:
    #                             headers = sf_config.get_sf_headers(type=True)

    #                         salesforce_pbe = ""
    #                         pricebook_id = ""
    #                         quote_data = requests.request(
    #                             "GET",
    #                             sf_config.sf_url
    #                             + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
    #                             headers=headers,
    #                             timeout=180,
    #                         )
    #                         if quote_data.text:
    #                             quote_data = json.loads(str(quote_data.text))
    #                             pricebook_id = quote_data.get("records")[0].get(
    #                                 "Pricebook2Id"
    #                             )
    #                         PricebookEntryData = requests.request(
    #                             "GET",
    #                             sf_config.sf_url
    #                             + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
    #                                 quote_line_dict["Product2Id"]
    #                             ),
    #                             headers=headers,
    #                             timeout=180,
    #                         )
    #                         if PricebookEntryData.text:
    #                             pricebookentry_data = json.loads(
    #                                 str(PricebookEntryData.text)
    #                             )
    #                             for pricebook in pricebookentry_data.get("records"):
    #                                 line.product_id.x_salesforce_pbe = pricebook.get(
    #                                     "Id"
    #                                 )
    #                             quote_line_dict["PricebookEntryId"] = (
    #                                 line.product_id.x_salesforce_pbe
    #                             )
    #                         if line.discount:
    #                             quote_line_dict["Discount"] = line.discount
    #                         if quote_line_dict:
    #                             result = self.sendQuoteLineDataToSf(
    #                                 quote_line_dict,
    #                                 line_sf_id,
    #                                 line_id,
    #                                 is_cron=is_from_cron,
    #                             )
    #                         self.x_salesforce_exported = True

    #                 elif not line.x_salesforce_id:
    #                     if line.product_id and line.product_id.x_salesforce_id:
    #                         quote_line_dict = {
    #                             "Product2Id": line.product_id.x_salesforce_id,
    #                             "Quantity": line.product_uom_qty,
    #                             "UnitPrice": line.price_unit,
    #                             "QuoteId": self.x_salesforce_id,
    #                         }
    #                     elif line.product_id and not line.product_id.x_salesforce_id:
    #                         line.product_id.exportProduct_to_sf(
    #                             is_from_cron=is_from_cron
    #                         )
    #                         quote_line_dict = {
    #                             "Product2Id": line.product_id.x_salesforce_id,
    #                             "Quantity": line.product_uom_qty,
    #                             "UnitPrice": line.price_unit,
    #                             "QuoteId": self.x_salesforce_id,
    #                         }
    #                     line_id = line.id
    #                     # Create a entry in price-book in salesforce
    #                     if sf_config.sf_access_token:
    #                         sf_access_token = sf_config.sf_access_token

    #                     if sf_access_token:
    #                         headers = sf_config.get_sf_headers(type=True)

    #                     salesforce_pbe = ""
    #                     pricebook_id = ""
    #                     quote_data = requests.request(
    #                         "GET",
    #                         sf_config.sf_url
    #                         + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
    #                         headers=headers,
    #                         timeout=180,
    #                     )
    #                     if quote_data.text:
    #                         quote_data = json.loads(str(quote_data.text))
    #                         pricebook_id = quote_data.get("records")[0].get(
    #                             "Pricebook2Id"
    #                         )
    #                     PricebookEntryData = requests.request(
    #                         "GET",
    #                         sf_config.sf_url
    #                         + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where  Product2Id='{}'".format(
    #                             quote_line_dict["Product2Id"]
    #                         ),
    #                         headers=headers,
    #                         timeout=180,
    #                     )
    #                     if PricebookEntryData.text:
    #                         pricebookentry_data = json.loads(
    #                             str(PricebookEntryData.text)
    #                         )
    #                         for pricebook in pricebookentry_data.get("records"):
    #                             line.product_id.x_salesforce_pbe = pricebook.get("Id")
    #                         quote_line_dict["PricebookEntryId"] = (
    #                             line.product_id.x_salesforce_pbe
    #                         )
    #                     if line.discount:
    #                         quote_line_dict["Discount"] = line.discount
    #                     if quote_line_dict:
    #                         result = self.sendQuoteLineDataToSf(
    #                             quote_line_dict,
    #                             line_sf_id,
    #                             line_id,
    #                             is_cron=is_from_cron,
    #                         )
    #                     self.x_salesforce_exported = True

    # def exportQuotations_to_sf(self, is_from_cron=False):
    #     if len(self) > 1 and not is_from_cron:
    #         raise UserError(_("Please Select 1 record to Export"))

    #     if not self.contract_id and self.state == "sale" and not is_from_cron:
    #         raise UserError(_("Please add contract1"))

    #     if not self.opportunity_id and not is_from_cron:
    #         raise UserError(_("Please add Opportunity"))

    #     # PREPARE DICT FOR SENDING TO SALESFORCE
    #     if is_from_cron:
    #         sf_config = (
    #             self.env["salesforce.instance"]
    #             .sudo()
    #             .search([("is_default_instance", "=", True)], limit=1)
    #         )
    #     else:
    #         sf_config = (
    #             self.env["salesforce.instance"]
    #             .sudo()
    #             .search([("company_id", "=", self.env.company.id)], limit=1)
    #         )

    #     if not sf_config and not is_from_cron:
    #         raise ValidationError(_("There is no Salesforce instance"))

    #     quote_dict = {}
    #     quote_line_list = [] # This variable isn't used in the provided snippet's logic, consider removing if truly unused.
    #     quote_line_dict = {}

    #     if self.opportunity_id and self.opportunity_id.x_salesforce_id_oppo:
    #         quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
    #     elif self.opportunity_id and not self.opportunity_id.x_salesforce_id_oppo:
    #         # Ensure exportOpportunity_to_sf returns a success indicator if needed, or handle its exceptions.
    #         # Assuming it successfully populates x_salesforce_id_oppo
    #         opportunity_export = self.opportunity_id.exportOpportunity_to_sf()
    #         quote_dict["OpportunityId"] = str(self.opportunity_id.x_salesforce_id_oppo)
    #     if self.contract_id and self.contract_id.x_salesforce_id:
    #         quote_dict["ContractId"] = self.contract_id.x_salesforce_id
    #     elif self.contract_id and not self.contract_id.x_salesforce_id:
    #         # Assuming exportContract_to_sf successfully populates x_salesforce_id
    #         contract_export = self.contract_id.exportContract_to_sf()
    #         quote_dict["ContractId"] = self.contract_id.x_salesforce_id
    #     quote_dict["Status"] = "Draft"

    #     # Create a entry in price-book in salesforce
    #     if self.name:
    #         quote_dict["Name"] = self.name
    #     if self.amount_tax:
    #         quote_dict["Tax"] = self.amount_tax
    #     if self.validity_date:
    #         quote_dict["ExpirationDate"] = str(self.validity_date)

    #     # Access token and headers should be retrieved once per main operation if possible
    #     # to avoid redundant calls within loops.
    #     sf_access_token = None
    #     if sf_config.sf_access_token:
    #         sf_access_token = sf_config.sf_access_token

    #     headers = None
    #     if sf_access_token:
    #         headers = sf_config.get_sf_headers(type=True)

    #     # Get Standard Price-book Id
    #     # Ensure 'timeout' is consistently applied
    #     endpoint = "/services/data/v40.0/query/?q=select Id from pricebook2 where name = '{}'".format(
    #         "Standard Price Book"
    #     )
    #     res = requests.request(
    #         "GET", sf_config.sf_url + endpoint, headers=headers, timeout=60 # Reduced timeout from 180
    #     )
    #     if res.status_code == 200:
    #         parsed_resp = json.loads(str(res.text))
    #         if parsed_resp.get("records") and parsed_resp.get("records")[0].get("Id"):
    #             quote_dict["Pricebook2Id"] = parsed_resp.get("records")[0].get("Id")

    #     # Assuming self.sendQuoteDataToSf creates/updates the Quote and populates self.x_salesforce_id
    #     result = self.sendQuoteDataToSf(quote_dict, is_cron=is_from_cron)
    #     line_sf_id = "" # This variable doesn't seem to be used for its initial value, only assigned inside loops.

    #     if result and self.x_salesforce_id: # Ensure Quote ID is available before handling lines/attachments
    #         # --- ATTACHMENT EXPORT CALL ---
    #         self._export_attachments_to_sf(sf_config, self.x_salesforce_id, timeout=60)
    #         # --- END ATTACHMENT EXPORT ---

    #         if self.order_line:
    #             for line in self.order_line:
    #                 # Retrieve headers again if they can expire within the loop, otherwise, use the one from outside.
    #                 # For simplicity, assuming headers are stable for the duration of this method.
    #                 if not headers: # Re-check headers if they might be None from earlier conditions
    #                     headers = sf_config.get_sf_headers(type=True)

    #                 if line.x_salesforce_id and line.quotation_order_line_updated:
    #                     delete_quotation_line = (
    #                         self.delete_quotation_line_to_salesforce(
    #                             line, line.x_salesforce_id, is_cron=is_from_cron
    #                         )
    #                     )
    #                     if delete_quotation_line:
    #                         if line.product_id and line.product_id.x_salesforce_id:
    #                             quote_line_dict = {
    #                                 "Product2Id": line.product_id.x_salesforce_id,
    #                                 "Quantity": line.product_uom_qty,
    #                                 "UnitPrice": line.price_unit,
    #                                 "QuoteId": self.x_salesforce_id,
    #                             }

    #                         elif (
    #                             line.product_id and not line.product_id.x_salesforce_id
    #                         ):
    #                             line.product_id.exportProduct_to_sf(
    #                                 is_from_cron=is_from_cron
    #                             )
    #                             quote_line_dict = {
    #                                 "Product2Id": line.product_id.x_salesforce_id,
    #                                 "Quantity": line.product_uom_qty,
    #                                 "UnitPrice": line.price_unit,
    #                                 "QuoteId": self.x_salesforce_id,
    #                             }
    #                         line_id = line.id

    #                         # Standard Price Book Entry ID fetch (inside loop, ensure efficiency or move if possible)
    #                         # Duplicated code block, consider refactoring this into a helper method.
    #                         # Also, ensure timeouts are applied consistently.
    #                         quote_data_res = requests.request( # Renamed variable to avoid conflict with quote_data below
    #                             "GET",
    #                             sf_config.sf_url
    #                             + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
    #                             headers=headers,
    #                             timeout=60, # Reduced timeout
    #                         )
    #                         pricebook_id = ""
    #                         if quote_data_res.text:
    #                             quote_data = json.loads(str(quote_data_res.text))
    #                             if quote_data.get("records"): # Check for records
    #                                 pricebook_id = quote_data.get("records")[0].get(
    #                                     "Pricebook2Id"
    #                                 )
    #                             # else: handle no records found for pricebook ID if applicable

    #                         PricebookEntryData = requests.request(
    #                             "GET",
    #                             sf_config.sf_url
    #                             + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where Product2Id='{}'".format(
    #                                 quote_line_dict["Product2Id"]
    #                             ),
    #                             headers=headers,
    #                             timeout=60, # Reduced timeout
    #                         )
    #                         if PricebookEntryData.text:
    #                             pricebookentry_data = json.loads(
    #                                 str(PricebookEntryData.text)
    #                             )
    #                             for pricebook in pricebookentry_data.get("records", []): # Iterate safely
    #                                 line.product_id.x_salesforce_pbe = pricebook.get(
    #                                     "Id"
    #                                 )
    #                             quote_line_dict["PricebookEntryId"] = (
    #                                 line.product_id.x_salesforce_pbe
    #                             )
    #                         if line.discount:
    #                             quote_line_dict["Discount"] = line.discount
    #                         if quote_line_dict:
    #                             result = self.sendQuoteLineDataToSf(
    #                                 quote_line_dict,
    #                                 line_sf_id, # This seems to be an empty string, check its intended use.
    #                                 line_id,
    #                                 is_cron=is_from_cron,
    #                             )
    #                         self.x_salesforce_exported = True

    #                 elif not line.x_salesforce_id:
    #                     if line.product_id and line.product_id.x_salesforce_id:
    #                         quote_line_dict = {
    #                             "Product2Id": line.product_id.x_salesforce_id,
    #                             "Quantity": line.product_uom_qty,
    #                             "UnitPrice": line.price_unit,
    #                             "QuoteId": self.x_salesforce_id,
    #                         }
    #                     elif line.product_id and not line.product_id.x_salesforce_id:
    #                         line.product_id.exportProduct_to_sf(
    #                             is_from_cron=is_from_cron
    #                         )
    #                         quote_line_dict = {
    #                             "Product2Id": line.product_id.x_salesforce_id,
    #                             "Quantity": line.product_uom_qty,
    #                             "UnitPrice": line.price_unit,
    #                             "QuoteId": self.x_salesforce_id,
    #                         }
    #                     line_id = line.id

    #                     # Duplicated code block for pricebook entry, refactor!
    #                     # Ensure timeouts are applied consistently.
    #                     quote_data_res = requests.request( # Renamed variable
    #                         "GET",
    #                         sf_config.sf_url
    #                         + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
    #                         headers=headers,
    #                         timeout=60, # Reduced timeout
    #                     )
    #                     pricebook_id = ""
    #                     if quote_data_res.text:
    #                         quote_data = json.loads(str(quote_data_res.text))
    #                         if quote_data.get("records"):
    #                             pricebook_id = quote_data.get("records")[0].get(
    #                                 "Pricebook2Id"
    #                             )
    #                     PricebookEntryData = requests.request(
    #                         "GET",
    #                         sf_config.sf_url
    #                         + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where Product2Id='{}'".format(
    #                             quote_line_dict["Product2Id"]
    #                         ),
    #                         headers=headers,
    #                         timeout=60, # Reduced timeout
    #                     )
    #                     if PricebookEntryData.text:
    #                         pricebookentry_data = json.loads(
    #                             str(PricebookEntryData.text)
    #                         )
    #                         for pricebook in pricebookentry_data.get("records", []):
    #                             line.product_id.x_salesforce_pbe = pricebook.get("Id")
    #                         quote_line_dict["PricebookEntryId"] = (
    #                             line.product_id.x_salesforce_pbe
    #                         )
    #                     if line.discount:
    #                         quote_line_dict["Discount"] = line.discount
    #                     if quote_line_dict:
    #                         result = self.sendQuoteLineDataToSf(
    #                             quote_line_dict,
    #                             line_sf_id, # This seems to be an empty string.
    #                             line_id,
    #                             is_cron=is_from_cron,
    #                         )
    #                     self.x_salesforce_exported = True

    # def _export_attachments_to_sf(self, sf_config, sf_record_id, api_version='v52.0', timeout=60):
    #     """
    #     Exports attachments linked to the current Odoo record to Salesforce
    #     and links them to the specified Salesforce record ID.
    #     :param sf_config: Salesforce instance configuration record.
    #     :param sf_record_id: The Salesforce ID of the record (e.g., Quote ID) to link attachments to.
    #     :param api_version: Salesforce API version to use.
    #     :param timeout: Timeout for API requests in seconds.
    #     """
    #     if not sf_config.sf_access_token:
    #         _logger.warning("No Salesforce access token available for attachment export.")
    #         return False

    #     headers = sf_config.get_sf_headers(type=True) # Assuming this gets correct headers including auth

    #     # Find attachments linked to this Odoo sale order
    #     attachments = self.env['ir.attachment'].search([
    #         ('res_model', '=', 'sale.order'),
    #         ('res_id', '=', self.id)
    #     ])

    #     if not attachments:
    #         _logger.info(f"No attachments found for Sale Order {self.name} (ID: {self.id}). Skipping attachment export.")
    #         return True # No attachments to export, so consider it successful for this part

    #     _logger.info(f"Exporting {len(attachments)} attachments for Sale Order {self.name} to Salesforce record {sf_record_id}.")

    #     for attachment in attachments:
    #         try:
    #             # 1. Upload ContentVersion (the file itself)
    #             cv_endpoint = f"/services/data/{api_version}/sobjects/ContentVersion"
    #             # Salesforce requires Base64 encoded file data
    #             version_data = attachment.datas.decode('utf-8') if attachment.datas else ''

    #             cv_payload = {
    #                 "Title": attachment.name,
    #                 "PathOnClient": attachment.name, # Use filename
    #                 "VersionData": version_data,
    #                 "Origin": "H", # 'H' for Salesforce Files, 'C' for Content
    #                 # Optional: "Description": attachment.description,
    #                 # Optional: "FirstPublishLocationId": sf_record_id # Can link directly during upload for some cases
    #             }

    #             _logger.info(f"Uploading attachment {attachment.name} (ID: {attachment.id}) to ContentVersion.")
    #             cv_res = requests.request("POST", sf_config.sf_url + cv_endpoint, headers=headers, json=cv_payload, timeout=timeout)
    #             cv_res.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

    #             cv_response_data = cv_res.json()
    #             content_document_id = cv_response_data.get('id') # This 'id' is actually ContentDocumentId for new ContentVersion

    #             if not content_document_id:
    #                 _logger.error(f"Failed to get ContentDocumentId after uploading ContentVersion for {attachment.name}. Response: {cv_response_data}")
    #                 continue

    #             _logger.info(f"Successfully uploaded ContentVersion for {attachment.name}. ContentDocumentId: {content_document_id}")

    #             # 2. Link ContentDocument to the Salesforce record (e.g., Quote)
    #             cdl_endpoint = f"/services/data/{api_version}/sobjects/ContentDocumentLink"
    #             cdl_payload = {
    #                 "ContentDocumentId": content_document_id,
    #                 "LinkedEntityId": sf_record_id, # The Salesforce Quote ID
    #                 "ShareType": "V", # 'V' for Viewer, 'C' for Collaborator, 'I' for Inferred (default)
    #                 "Visibility": "AllUsers" # 'AllUsers', 'InternalUsers'
    #             }

    #             _logger.info(f"Linking ContentDocument {content_document_id} to Salesforce record {sf_record_id}.")
    #             cdl_res = requests.request("POST", sf_config.sf_url + cdl_endpoint, headers=headers, json=cdl_payload, timeout=timeout)
    #             cdl_res.raise_for_status()

    #             _logger.info(f"Successfully linked attachment {attachment.name} to Salesforce record {sf_record_id}.")

    #         except requests.exceptions.Timeout:
    #             _logger.error(f"Timeout occurred while exporting attachment {attachment.name} (ID: {attachment.id}) to Salesforce.")
    #             # You might want to log this in a specific Odoo error log as well
    #         except requests.exceptions.RequestException as e:
    #             _logger.error(f"Error exporting attachment {attachment.name} (ID: {attachment.id}) to Salesforce: {e}. Response: {e.response.text if e.response else 'No response'}")
    #             # Log the full error from Salesforce for debugging
    #         except Exception as e:
    #             _logger.error(f"An unexpected error occurred during attachment export for {attachment.name}: {e}")

    #     return True # Indicate completion of attachment export process

    def _export_attachments_to_sf(
        self, sf_config, sf_record_id, api_version="v52.0", timeout=180
    ):
        """
        Exports attachments linked to the current Odoo record to Salesforce
        and links them to the specified Salesforce record ID.
        :param sf_config: Salesforce instance configuration record.
        :param sf_record_id: The Salesforce ID of the record (e.g., Quote ID) to link attachments to.
        :param api_version: Salesforce API version to use.
        :param timeout: Timeout for API requests in seconds.
        """
        if not sf_record_id:
            _logger.warning(
                f"Salesforce record ID is missing for Sale Order {self.name}. Cannot export attachments."
            )
            return False

        if not sf_config.sf_access_token:
            _logger.warning(
                "No Salesforce access token available for attachment export."
            )
            return False

        headers = sf_config.get_sf_headers(type=True)

        attachments = self.env["ir.attachment"].search(
            [("res_model", "=", "sale.order"), ("res_id", "=", self.id)]
        )

        if not attachments:
            _logger.info(
                f"No attachments found for Sale Order {self.name} (ID: {self.id}). Skipping attachment export."
            )
            return True

        _logger.info(
            f"Exporting {len(attachments)} attachments for Sale Order {self.name} to Salesforce record {sf_record_id}."
        )

        for attachment in attachments:
            try:
                # 1. Upload ContentVersion (the file itself)
                cv_endpoint = f"/services/data/{api_version}/sobjects/ContentVersion"

                # Salesforce requires Base64 encoded file data without the 'b' prefix and newlines
                # Odoo's ir.attachment stores 'datas' as base64 encoded bytes
                version_data = (
                    attachment.datas.decode("utf-8") if attachment.datas else ""
                )

                cv_payload = {
                    "Title": attachment.name,
                    "PathOnClient": attachment.name,
                    "VersionData": version_data,
                    "Origin": "H",  # 'H' for Salesforce Files, 'C' for Content
                    "ContentLocation": "S",  # 'S' for Salesforce, 'E' for External
                }

                _logger.info(
                    f"Attempting to upload attachment {attachment.name} (ID: {attachment.id}) to ContentVersion."
                )
                cv_res = requests.request(
                    "POST",
                    sf_config.sf_url + cv_endpoint,
                    headers=headers,
                    json=cv_payload,
                    timeout=timeout,
                )
                cv_res.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

                # --- NEW LOGGING ADDED HERE ---
                _logger.info(
                    f"ContentVersion upload response status: {cv_res.status_code}"
                )
                cv_response_data = cv_res.json()
                _logger.info(f"ContentVersion upload response data: {cv_response_data}")
                # --- END NEW LOGGING ---

                content_version_id = cv_response_data.get("id")
                if not content_version_id:
                    _logger.error(
                        f"Failed to get ContentVersionId after uploading ContentVersion for {attachment.name}. "
                        f"ContentVersion API Response: {cv_response_data}"
                    )
                    continue

                # Step: Query to get ContentDocumentId
                query = f"SELECT ContentDocumentId FROM ContentVersion WHERE Id = '{content_version_id}'"
                query_endpoint = f"/services/data/{api_version}/query/?q={query}"

                try:
                    _logger.info(
                        f"Querying ContentDocumentId for ContentVersionId: {content_version_id}"
                    )
                    query_res = requests.get(
                        sf_config.sf_url + query_endpoint,
                        headers=headers,
                        timeout=timeout,
                    )
                    query_res.raise_for_status()
                    query_data = query_res.json()

                    content_document_id = query_data["records"][0]["ContentDocumentId"]
                except Exception as e:
                    _logger.error(
                        f"Failed to retrieve ContentDocumentId for ContentVersionId {content_version_id}: {e}"
                    )
                    continue

                _logger.info(
                    f"Successfully uploaded ContentVersion for {attachment.name}. ContentDocumentId: {content_document_id}"
                )

                # 2. Link ContentDocument to the Salesforce record (e.g., Quote)
                cdl_endpoint = (
                    f"/services/data/{api_version}/sobjects/ContentDocumentLink"
                )
                cdl_payload = {
                    "ContentDocumentId": content_document_id,
                    "LinkedEntityId": sf_record_id,  # The Salesforce Quote ID (self.x_salesforce_id)
                    "ShareType": "I",  # 'V' for Viewer, 'C' for Collaborator, 'I' for Inferred (default)
                    "Visibility": "AllUsers",  # 'AllUsers', 'InternalUsers'
                }

                _logger.info(
                    f"Attempting to link ContentDocument {content_document_id} to Salesforce record {sf_record_id}."
                )
                cdl_res = requests.request(
                    "POST",
                    sf_config.sf_url + cdl_endpoint,
                    headers=headers,
                    json=cdl_payload,
                    timeout=timeout,
                )
                cdl_res.raise_for_status()

                _logger.info(
                    f"Successfully linked attachment {attachment.name} to Salesforce record {sf_record_id}."
                )

            except requests.exceptions.Timeout:
                _logger.error(
                    f"Timeout occurred while exporting attachment {attachment.name} (ID: {attachment.id}) to Salesforce."
                )
            except requests.exceptions.RequestException as e:
                error_response_text = "No response body received."
                if e.response is not None:
                    try:
                        error_response_text = e.response.json()
                    except json.JSONDecodeError:
                        error_response_text = e.response.text

                _logger.error(
                    f"Error exporting attachment {attachment.name} (ID: {attachment.id}) to Salesforce: {e}. "
                    f"Salesforce Response: {error_response_text}"
                )
            except Exception as e:
                _logger.error(
                    f"An unexpected error occurred during attachment export for {attachment.name}: {e}"
                )

        return True

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

        sf_access_token = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        headers = None
        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

        # Get Standard Price-book Id
        endpoint = "/services/data/v40.0/query/?q=select Id from pricebook2 where name = '{}'".format(
            "Standard Price Book"
        )
        res = requests.request(
            "GET", sf_config.sf_url + endpoint, headers=headers, timeout=60
        )
        if res.status_code == 200:
            parsed_resp = json.loads(str(res.text))
            if parsed_resp.get("records") and parsed_resp.get("records")[0].get("Id"):
                quote_dict["Pricebook2Id"] = parsed_resp.get("records")[0].get("Id")

        result = self.sendQuoteDataToSf(quote_dict, is_cron=is_from_cron)
        line_sf_id = ""

        if result and self.x_salesforce_id:
            # --- ATTACHMENT EXPORT CALL ---
            self._export_attachments_to_sf(sf_config, self.x_salesforce_id, timeout=180)
            # --- END ATTACHMENT EXPORT ---

            if self.order_line:
                for line in self.order_line:
                    if not headers:
                        headers = sf_config.get_sf_headers(type=True)

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

                            quote_data_res = requests.request(
                                "GET",
                                sf_config.sf_url
                                + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
                                headers=headers,
                                timeout=60,
                            )
                            pricebook_id = ""
                            if quote_data_res.text:
                                quote_data = json.loads(str(quote_data_res.text))
                                if quote_data.get("records"):
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
                                timeout=60,
                            )
                            if PricebookEntryData.text:
                                pricebookentry_data = json.loads(
                                    str(PricebookEntryData.text)
                                )
                                for pricebook in pricebookentry_data.get("records", []):
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

                        quote_data_res = requests.request(
                            "GET",
                            sf_config.sf_url
                            + f"/services/data/v40.0/query/?q=select Pricebook2Id from Quote where Id = '{self.x_salesforce_id}'",
                            headers=headers,
                            timeout=60,
                        )
                        pricebook_id = ""
                        if quote_data_res.text:
                            quote_data = json.loads(str(quote_data_res.text))
                            if quote_data.get("records"):
                                pricebook_id = quote_data.get("records")[0].get(
                                    "Pricebook2Id"
                                )
                        PricebookEntryData = requests.request(
                            "GET",
                            sf_config.sf_url
                            + "/services/data/v40.0/query/?q=select Id,UnitPrice from PricebookEntry where Product2Id='{}'".format(
                                quote_line_dict["Product2Id"]
                            ),
                            headers=headers,
                            timeout=60,
                        )
                        if PricebookEntryData.text:
                            pricebookentry_data = json.loads(
                                str(PricebookEntryData.text)
                            )
                            for pricebook in pricebookentry_data.get("records", []):
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
