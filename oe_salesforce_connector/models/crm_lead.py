import json
import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CRMLead(models.Model):
    _inherit = "crm.lead"

    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce from lead", default=False, copy=False
    )
    x_salesforce_id = fields.Char("Salesforce Id from lead", copy=False)
    x_is_updated = fields.Boolean("x_is_updated_from_lead", default=False, copy=False)
    sf_status = fields.Selection(
        [
            ("open", "Open - Not Contacted"),
            ("working", "Working - Contacted"),
            ("closed1", "Closed - Converted"),
            ("closed2", "Closed - Not Converted"),
        ]
    )

    def sendDataToSf(self, lead_dict, is_cron=False):
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
            endpoint = "/services/data/v40.0/sobjects/Lead"

            payload = json.dumps(lead_dict)
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
                                        "type": "lead",
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
                                        "type": "lead",
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
                                        "type": "lead",
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
                                        "type": "lead",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Export Something went Wrong.",
                                    },
                                )
                            ]
                        }
                    )
                    return False

    def exportLead_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))

        if not self.partner_name and not is_from_cron:
            raise UserError(_("Please add Company name"))

        if not self.contact_name or not self.title and not is_from_cron:
            raise UserError(_("Please add contact name and title"))

        if not self.sf_status and not is_from_cron:
            raise UserError(_("Please add SF Status"))

        # PREPARE DICT FOR SENDING TO SALESFORCE
        lead_dict = {}
        if self.name:
            lead_dict["LastName"] = self.name
        if self.partner_name:
            lead_dict["Company"] = self.partner_name
        if self.sf_status:
            lead_dict["Status"] = dict(self._fields["sf_status"].selection).get(
                self.sf_status
            )
        if self.title:
            lead_dict["Salutation"] = self.title.name
        if self.name:
            lead_dict["LastName"] = self.name
        if self.phone:
            lead_dict["Phone"] = self.phone
        if self.mobile:
            lead_dict["MobilePhone"] = self.mobile
        if self.email_from:
            lead_dict["Email"] = self.email_from
        if self.website:
            lead_dict["Website"] = self.website
        if self.description:
            lead_dict["Description"] = self.description
        if self.street:
            lead_dict["Street"] = self.street
        if self.city:
            lead_dict["City"] = self.city
        if self.zip:
            lead_dict["PostalCode"] = self.zip
        if self.country_id:
            lead_dict["Country"] = self.country_id.name
        if self.state_id:
            lead_dict["State"] = self.state_id.name

        result = self.sendDataToSf(lead_dict, is_cron=is_from_cron)
        if result:
            self.x_salesforce_exported = True

    def exportLeadDatatosaleforce(self):
        if self.type == "lead":
            self.exportLead_to_sf()
        elif self.type == "opportunity":
            self.exportOpportunity_to_sf()

    @api.model
    def _scheduler_export_leads_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            leads = self.search([("type", "=", "lead")], limit=sf_config.export_limit)
        else:
            leads = self.search([("type", "=", "lead")])
        for lead in leads:
            try:
                lead.exportLead_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error("Oops Some error in  exporting leads to SALESFORCE %s", e)
