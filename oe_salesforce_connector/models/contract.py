import json
import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SFContract(models.Model):
    _name = "sf.contract"
    _description = " "

    name = fields.Char()
    contract_start_date = fields.Date()
    parent_id = fields.Many2one(
        "res.partner", "Company", domain="[('is_company', '=', True)]"
    )
    contacr_term_month = fields.Integer("Contract Term (months)")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("activated", "Activated"),
            ("approval", "In Approval Process"),
        ]
    )

    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce", default=False, copy=False
    )
    x_salesforce_id = fields.Char("Salesforce Id", copy=False)
    x_is_updated = fields.Boolean("x_is_updated", default=False, copy=False)

    def sendDataToSf(self, contract_dict, is_cron=False):
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

            endpoint = "/services/data/v40.0/sobjects/Contract"

            payload = json.dumps(contract_dict)
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
                                        "type": "contract",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully:- Updated data",
                                    },
                                )
                            ]
                        }
                    )
                else:
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contract",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export the Updated data:- Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False
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
                                        "type": "contract",
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
                                        "type": "contract",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False

    def activate_contract(self):
        if not self.x_salesforce_id:
            _logger.warning("Salesforce Id is missing. Cannot activate the contract.")
            return False

        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )

        if not sf_config:
            _logger.error("There is no Salesforce Instance")
            return False

        endpoint = f"/services/data/v40.0/sobjects/Contract/{self.x_salesforce_id}"
        headers = sf_config.get_sf_headers(type=True)

        payload = json.dumps({"Status": "Activated"})

        _logger.info("Request URL: %s", sf_config.sf_url + endpoint)
        _logger.info("Request Headers: %s", headers)
        _logger.info("Request Payload: %s", payload)

        try:
            res = requests.request(
                "PATCH",
                sf_config.sf_url + endpoint,
                headers=headers,
                data=payload,
                timeout=180,
            )
            if res.status_code == 200:
                _logger.info("Contract activated successfully in Salesforce.")
                return True
            else:
                _logger.error(
                    "Failed to activate the contract in Salesforce. Status code: %s",
                    res.status_code,
                )
                return False

        except Exception as e:
            _logger.error(
                "An error occurred while activating the contract in Salesforce: %s", e
            )
            return False

    def exportContract_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export."))

        # PREPARE DICT FOR SENDING TO SALESFORCE
        contract_dict = {}
        if self.contract_start_date:
            contract_dict["StartDate"] = str(self.contract_start_date)
        if self.parent_id:
            contract_dict["AccountId"] = str(self.parent_id.x_salesforce_id)
        if self.state:
            contract_dict["Status"] = dict(self._fields["state"].selection).get(
                self.state
            )
        if self.contacr_term_month:
            contract_dict["ContractTerm"] = self.contacr_term_month
        result = self.sendDataToSf(contract_dict, is_cron=is_from_cron)
        if result:
            self.x_salesforce_exported = True
            if self.state == "activated" and self.x_salesforce_id:
                try:
                    self.activate_contract(self.x_salesforce_id)
                except Exception:
                    _logger.error("'Failed to activate contract in Salesforce: %s', e")

    @api.model
    def _scheduler_export_contracts_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            contracts = self.search([], limit=sf_config.export_limit)
        else:
            contracts = self.search([])

        for contract in contracts:
            try:
                contract.exportContract_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  exporting contracts to SALESFORCE %s", e
                )
