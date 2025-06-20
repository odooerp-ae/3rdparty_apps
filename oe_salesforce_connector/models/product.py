import json
import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ProductTemplateCust(models.Model):
    _inherit = "product.product"

    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce", default=False, copy=False
    )
    x_salesforce_id = fields.Char("Salesforce Id", copy=False)
    x_is_updated = fields.Boolean("x_is_updated", default=False, copy=False)
    x_salesforce_pbe = fields.Char("x_salesforce_pbe", copy=False)

    product_price = None

    def sendDataToSf(self, product_dict, is_from_cron=False):
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

            endpoint = "/services/data/v40.0/sobjects/product2"

            payload = json.dumps(product_dict)
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
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully:- Updated data",
                                    },
                                )
                            ]
                        }
                    )

                # Update Price as well
                endpoint = "/services/data/v40.0/sobjects/pricebookentry"
                payload = {
                    "IsActive": True,
                    "UnitPrice": self.list_price,
                    "UseStandardPrice": False,
                }

                payload = json.dumps(payload)
                res_new = ""
                if self.x_salesforce_pbe:
                    res_new = requests.request(
                        "PATCH",
                        sf_config.sf_url + endpoint + "/" + self.x_salesforce_pbe,
                        headers=headers,
                        data=payload,
                        timeout=180,
                    )
                if res.status_code == 404:
                    is_create = True
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export the Updated data:- Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                else:
                    pass
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
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully",
                                    },
                                )
                            ]
                        }
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
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False

    def exportProduct_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))
        # PREPARE DICT FOR SENDING TO SALESFORCE
        product_dict = {}
        if self.name:
            product_dict["Name"] = self.name
        if self.active:
            product_dict["IsActive"] = "true"
        else:
            product_dict["IsActive"] = "false"
        if self.description_sale:
            product_dict["Description"] = self.description_sale

        if self.categ_id:
            product_dict["Family"] = self.categ_id.name
        if self.default_code:
            product_dict["ProductCode"] = self.default_code

        result = self.sendDataToSf(product_dict, is_from_cron=is_from_cron)
        if result:
            self.x_salesforce_exported = True
            sf_access_token = None
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

            if not sf_config and not is_from_cron:
                raise ValidationError(
                    _(
                        "There is no Salesforce instance for this company %s.",
                        self.env.company.name,
                    )
                )

            # Create a entry in price-book in salesforce
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
                if res.status_code in (200, 201):
                    parsed_resp = json.loads(str(res.text))
                    if parsed_resp.get("records") and parsed_resp.get("records")[0].get(
                        "Id"
                    ):
                        payload = {
                            "IsActive": True,
                            "UnitPrice": self.list_price,
                            "UseStandardPrice": False,
                            "Product2Id": result,
                            "Pricebook2Id": parsed_resp.get("records")[0].get("Id"),
                        }
                        payload = json.dumps(payload)
                        endpoint = "/services/data/v40.0/sobjects/pricebookentry"
                        res = requests.request(
                            "POST",
                            sf_config.sf_url + endpoint,
                            headers=headers,
                            data=payload,
                            timeout=180,
                        )
                        if res.status_code in (200, 201):
                            resp = json.loads(str(res.text))
                            self.x_salesforce_pbe = resp.get("id")

    @api.model
    def _scheduler_export_products_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            products = self.search([], limit=sf_config.export_limit)
        else:
            products = self.search([])

        for product in products:
            try:
                product.exportProduct_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  exporting products to SALESFORCE %s", e
                )
