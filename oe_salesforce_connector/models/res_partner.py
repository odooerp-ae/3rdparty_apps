import json
import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class ResPartnerCustomization(models.Model):
    _inherit = "res.partner"

    x_salesforce_id = fields.Char("SalesForce ID", copy=False)
    x_salesforce_exported = fields.Boolean(
        "Exported To Salesforce", default=False, copy=False
    )
    x_is_updated = fields.Boolean("x_is_updated", default=False, copy=False)
    x_last_modified_on = fields.Datetime("SF last Modified.", copy=False)

    """ For Update Version """

    def write(self, vals):
        if vals:
            if "x_last_modified_on" in vals.keys():
                if vals["x_last_modified_on"]:
                    vals["x_is_updated"] = True
                else:
                    vals["x_is_updated"] = False
            else:
                vals["x_is_updated"] = False

        res = super().write(vals)
        return res

    def updateExistingCustomer(self):
        endpoint = None
        # """ Check first if x_quickbooks_id exists in quickbooks or not"""
        if self.x_salesforce_exported or self.x_salesforce_id:
            # """ Hit request ot salesforce and check response """
            sf_config = (
                self.env["salesforce.instance"]
                .sudo()
                .search([("company_id", "=", self.env.company.id)], limit=1)
            )

            # """ GET ACCESS TOKEN """

            sf_access_token = None
            realmId = None
            if sf_config.sf_access_token:
                sf_access_token = sf_config.sf_access_token

            if sf_access_token:
                headers = sf_config.get_sf_headers(type=True)

                if self.is_company:
                    endpoint = "/services/data/v40.0/sobjects/Account/"
                else:
                    endpoint = "/services/data/v40.0/sobjects/Contact/"
                result = requests.request(
                    "GET",
                    sf_config.sf_url + endpoint + self.x_salesforce_id,
                    headers=headers,
                    timeout=180,
                )
                if result.status_code in [200, 201]:
                    parsed_result = result.json()
                    if parsed_result.get("Id"):
                        customer_id_retrieved = parsed_result.get("Id")
                        if customer_id_retrieved:
                            # """ HIT UPDATE REQUEST """
                            result = self.prepareSFDictStructure(
                                is_update=True,
                                customer_id_retrieved=customer_id_retrieved,
                            )
                            if result:
                                return result
                            else:
                                return False
                else:
                    return False

    def sendDataToSalesforceForUpdate(self, dict):
        # sf_config = self.env.user.company_id
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)], limit=1)
        )
        if not sf_config:
            return False

        # """ GET ACCESS TOKEN """
        sf_access_token = None
        parsed_dict = json.dumps(dict)
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            if self.is_company:
                endpoint = "/services/data/v39.0/sobjects/Account/"
            else:
                endpoint = "/services/data/v39.0/sobjects/Contact/"

            result = requests.request(
                "PATCH",
                sf_config.sf_url + endpoint + self.x_salesforce_id,
                headers=headers,
                data=parsed_dict,
                timeout=180,
            )
            if result.status_code in [204]:
                self.x_is_updated = True
                return True
            else:
                raise UserError(_("Error Occurred While Updating" + result.text))

    def prepareSFDictStructure(
        self,
        obj=False,
        record_type=False,
        customer_id_retrieved=False,
        is_update=False,
        sync_token=False,
    ):
        data_object = None
        if obj:
            data_object = obj
        else:
            data_object = self

        if data_object.is_company:
            record_type = "company"

        # """ This Function Exports Record to Quickbooks """
        dict = {}
        dict_phone = {}
        dict_email = {}
        dict_mobile = {}
        dict_billAddr = {}
        dict_shipAddr = {}
        # dict_fax = {}
        dict_parent_ref = {}
        dict_job = {}

        if record_type != "company":
            if data_object.mobile:
                dict["MobilePhone"] = str(data_object.mobile)

        if record_type == "company":
            if data_object.website:
                dict["Website"] = str(data_object.website)

        if data_object.comment:
            dict["Description"] = data_object.comment
        #
        if record_type != "company":
            if data_object.name:
                name_split = data_object.name.split()
                dict["FirstName"] = name_split[0]
                if len(name_split) > 1:
                    lastname = name_split[1::]

                    dict["LastName"] = " ".join(lastname)
                else:
                    dict["LastName"] = "."
        else:
            if data_object.name:
                dict["Name"] = str(data_object.name)

        if record_type != "company":
            if data_object.title:
                dict["Salutation"] = data_object.title.name

            if data_object.function:
                dict["Title"] = data_object.function

        if record_type != "company":
            if data_object.email:
                dict_email["Email"] = str(data_object.email)

        if data_object.phone:
            dict_phone["Phone"] = str(data_object.phone)

        if (
            data_object.type == "invoice"
            or data_object.type == "contact"
            and record_type == "company"
        ):
            if data_object.street and data_object.street2:
                dict["BillingStreet"] = data_object.street + data_object.street2
            elif data_object.street and not data_object.street2:
                dict["BillingStreet"] = data_object.street
            elif data_object.street2 and not data_object.street:
                dict["BillingStreet"] = data_object.street2
            else:
                dict["BillingStreet"] = "NA"
            dict["BillingCity"] = data_object.city
            dict["BillingState"] = data_object.state_id.name
            dict["BillingPostalCode"] = data_object.zip
            dict["BillingCountry"] = data_object.country_id.name

        elif (
            data_object.type == "invoice"
            or data_object.type == "contact"
            and record_type != "company"
        ):
            if data_object.street and data_object.street2:
                dict["MailingStreet"] = data_object.street + data_object.street2
            elif data_object.street and not data_object.street2:
                dict["MailingStreet"] = data_object.street
            elif data_object.street2 and not data_object.street:
                dict["MailingStreet"] = data_object.street2
            else:
                dict["MailingStreet"] = "NA"
            dict["MailingCity"] = data_object.city
            dict["MailingState"] = data_object.state_id.name
            dict["MailingPostalCode"] = data_object.zip
            dict["MailingCountry"] = data_object.country_id.name

        if self.type == "delivery" and record_type == "company":
            dict["ShippingStreet"] = data_object.street + data_object.street2
            dict["ShippingCity"] = data_object.city
            dict["ShippingState"] = data_object.state_id.name
            dict["ShippingPostalCode"] = data_object.zip
            dict["ShippingCountry"] = data_object.country_id.name

        # if data_object.fax:
        #     dict_fax['Fax'] = str(data_object.fax)

        dict.update(dict_email)
        dict.update(dict_phone)
        dict.update(dict_billAddr)
        dict.update(dict_shipAddr)
        # dict.update(dict_fax)

        if customer_id_retrieved and record_type and record_type == "indv_company":
            dict_parent_ref["AccountId"] = str(customer_id_retrieved)
            dict.update(dict_parent_ref)

        if is_update and customer_id_retrieved:
            result = self.sendDataToSalesforceForUpdate(dict)
        else:
            result = self.sendDataToSalesforce(dict, record_type=record_type)

        if result:
            return result
        else:
            return False

    def createParentInSalesforce(self, odoo_partner_object, sf_config):
        """This Function Creates a new record in salesforce and returns its Id
        For attaching with the record of customer which will be created in exportPartner Function"""

        if odoo_partner_object and sf_config:
            result = self.prepareSFDictStructure(
                odoo_partner_object, record_type="company"
            )
            if result:
                return result
        else:
            return False

        # """STEP 1 : Retrieve All Data from odoo_partner_object to form a dictionary which will be passed
        # to Quickbooks"""

    def checkPartnerInSalesforce(self, odoo_partner_object):
        """Check This Name in Quickbooks"""
        customer_id_retrieved = None
        #         sf_config = self.env['res.users'].search([('id','=',self._uid)],limit=1).company_id
        # sf_config = self.env.user.company_id
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)], limit=1)
        )
        if sf_config:
            sf_access_token = None
            realmId = None
            if sf_config.sf_access_token:
                sf_access_token = sf_config.sf_access_token

            if sf_access_token:
                # """ Hit SF and Check Availability """
                headers = sf_config.get_sf_headers(type=True)

                q_para = str(odoo_partner_object.name)
                query = f"select Id from account where Name = '{q_para}'"

                result = requests.request(
                    "GET",
                    sf_config.sf_url
                    + f"/services/data/v40.0/query/?q=select Id from account where Name = '{q_para}'",
                    headers=headers,
                    timeout=180,
                )
                if result.status_code == 200:
                    parsed_result = result.json()

                    if parsed_result.get("records") and parsed_result.get("records")[
                        0
                    ].get("Id"):
                        customer_id_retrieved = parsed_result.get("records")[0].get(
                            "Id"
                        )
                        if customer_id_retrieved:
                            return customer_id_retrieved
                    if not parsed_result.get("records"):
                        new_sf_parent_id = self.createParentInSalesforce(
                            odoo_partner_object, sf_config
                        )
                        if new_sf_parent_id:
                            odoo_partner_object.x_salesforce_exported = True
                            odoo_partner_object.x_salesforce_id = new_sf_parent_id
                            return new_sf_parent_id
                        return False
                else:
                    raise UserError(
                        _("Error Occurred In Partner Search Request" + result.text)
                    )
                return False

    def sendDataToSalesforce(self, dict, record_type=False):
        # sf_config = self.env['res.users'].search([('id','=',self._uid)],limit=1).company_id.
        # sf_config = self.env.user.company_id
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("company_id", "=", self.env.company.id)], limit=1)
        )
        if not sf_config:
            return False

        # """ GET ACCESS TOKEN """
        sf_access_token = None
        realmId = None
        endpoint = None
        parsed_dict = json.dumps(dict)
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            if self.is_company or record_type == "company":
                endpoint = "/services/data/v40.0/sobjects/Account"
            else:
                endpoint = "/services/data/v40.0/sobjects/Contact"

            result = requests.request(
                "POST",
                sf_config.sf_url + endpoint,
                headers=headers,
                data=parsed_dict,
                timeout=180,
            )
            if result.status_code in [200, 201]:
                parsed_result = result.json()
                if parsed_result.get("id"):
                    if self.parent_id:
                        self.parent_id.x_salesforce_exported = True
                    if not self.parent_id:
                        self.x_salesforce_exported = True
                    self.x_salesforce_id = parsed_result.get("id")
                    return parsed_result.get("id")
                else:
                    return False
            else:
                raise UserError(
                    "Error Occurred While Exporting"
                    + result.text
                    + str(result.status_code)
                )

    def create_partner_in_sf(self, sf_partner_dict, is_from_cron=False):
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

        if not is_from_cron and not sf_config:
            raise ValidationError(_("There is no Salesforce instance"))

        if not sf_config.sf_access_token:
            return False

        headers = sf_config.get_sf_headers(True)

        if self.is_company:
            endpoint = "/services/data/v40.0/sobjects/Account"
        else:
            endpoint = "/services/data/v40.0/sobjects/Contact"

        parsed_dict = json.dumps(sf_partner_dict)

        result = requests.request(
            "POST",
            sf_config.sf_url + endpoint,
            headers=headers,
            data=parsed_dict,
            timeout=180,
        )

        if result.status_code in (200, 201):
            parsed_result = result.json()
            if parsed_result.get("id"):
                self.x_is_updated = True
                self.x_salesforce_exported = True
                self.x_last_modified_on = datetime.now()
                self.x_salesforce_id = parsed_result.get("id")
                # self.commit()
                _logger.info("Updated companies in salesforce")
                sf_config.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "contact",
                                    "date_time": datetime.now(),
                                    "state": "success",
                                    "message": "Exported Successfully:- Updated data",
                                },
                            )
                        ]
                    }
                )
                return parsed_result.get("id")
            else:
                return False
        elif result.status_code == 401:
            sf_config.write(
                {
                    "salesforce_instance_line_ids": [
                        (
                            0,
                            0,
                            {
                                "type": "contact",
                                "date_time": datetime.now(),
                                "state": "error",
                                "message": "Enable to Export may be ACCESS TOKEN EXPIRED.",
                            },
                        )
                    ]
                }
            )
            sf_config.refresh_salesforce_token_from_access_token(is_cron=is_from_cron)
            _logger.info("ACCESS TOKEN EXPIRED, GETTING NEW REFRESH TOKEN...")
            return False
        else:
            parsed_json = result.json()
            sf_config.write(
                {
                    "salesforce_instance_line_ids": [
                        (
                            0,
                            0,
                            {
                                "type": "contact",
                                "date_time": datetime.now(),
                                "state": "error",
                                "message": (
                                    "Enable to Export:- %s."
                                    % (str(parsed_json[0].get("message")))
                                ),
                            },
                        )
                    ]
                }
            )
            _logger.error(
                "response Of Partner creation in salesforce  (%s)",
                str(parsed_json[0].get("message")),
            )
            return False

    def update_partner_in_sf(self, sf_partner_dict, is_from_cron=False):
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

        if not is_from_cron and not sf_config:
            raise ValidationError(_("There is no Salesforce instance"))

        parsed_dict = json.dumps(sf_partner_dict)

        if not sf_config.sf_access_token:
            return False

        headers = sf_config.get_sf_headers(True)

        if self.is_company:
            endpoint = "/services/data/v40.0/sobjects/Account/"
        else:
            endpoint = "/services/data/v40.0/sobjects/Contact/"

        result = requests.request(
            "PATCH",
            sf_config.sf_url + endpoint + self.x_salesforce_id,
            headers=headers,
            data=parsed_dict,
            timeout=180,
        )
        if result.status_code in (200, 201, 204):
            self.x_is_updated = True
            self.x_last_modified_on = datetime.now()
            sf_config.write(
                {
                    "salesforce_instance_line_ids": [
                        (
                            0,
                            0,
                            {
                                "type": "contact",
                                "date_time": datetime.now(),
                                "state": "success",
                                "message": "Exported Successfully",
                            },
                        )
                    ]
                }
            )
            _logger.info("Exported companies in salesforce")
            return True
        elif result.status_code == 401:
            sf_config.write(
                {
                    "salesforce_instance_line_ids": [
                        (
                            0,
                            0,
                            {
                                "type": "contact",
                                "date_time": datetime.now(),
                                "state": "error",
                                "message": "Enable to Export",
                            },
                        )
                    ]
                }
            )
            sf_config.refresh_salesforce_token_from_access_token(is_cron=is_from_cron)
            return False
        else:
            sf_config.write(
                {
                    "salesforce_instance_line_ids": [
                        (
                            0,
                            0,
                            {
                                "type": "contact",
                                "date_time": datetime.now(),
                                "state": "error",
                                "message": "Enable to Export:- Error Occurred While Updating",
                            },
                        )
                    ]
                }
            )
            _logger.error("Error Occurred While Updating : %s ", result.text)
            return False

    def create_contact_sf_dict(self):
        contact_dict = {}
        name_split = self.name.split(" ", 1)
        contact_dict["FirstName"] = name_split[0]
        if len(name_split) > 1:
            lastname = name_split[-1]
            contact_dict["LastName"] = lastname
        else:
            contact_dict["LastName"] = "."
        if self.parent_id:
            if self.parent_id.x_salesforce_id:
                contact_dict["AccountId"] = self.parent_id.x_salesforce_id
        if self.mobile:
            contact_dict["MobilePhone"] = str(self.mobile).replace(" ", "")
        if self.title:
            contact_dict["Salutation"] = self.title.name
        if self.email:
            contact_dict["Email"] = str(self.email)
        if self.function:
            contact_dict["Title"] = self.function
        if self.comment:
            contact_dict["Description"] = self.comment
        if self.phone:
            contact_dict["Phone"] = str(self.phone).replace(" ", "")

        if self.street and self.street2:
            contact_dict["MailingStreet"] = self.street + self.street2
        elif self.street and not self.street2:
            contact_dict["MailingStreet"] = self.street
        elif self.street2 and not self.street:
            contact_dict["MailingStreet"] = self.street2
        if self.city:
            contact_dict["MailingCity"] = self.city
        if self.state_id.name:
            contact_dict["MailingState"] = self.state_id.name
        if self.zip:
            contact_dict["MailingPostalCode"] = self.zip
        if self.country_id.name:
            contact_dict["MailingCountry"] = self.country_id.name

        return contact_dict

    def create_company_sf_dict(self):
        company_dict = {}
        company_dict["Name"] = str(self.name)
        if self.parent_id.is_company and self.parent_id.x_salesforce_id:
            company_dict["ParentId"] = str(self.parent_id.x_salesforce_id)
        if self.comment:
            company_dict["Description"] = self.comment
        if self.phone:
            company_dict["Phone"] = str(self.phone)
        if self.website:
            company_dict["Website"] = str(self.website)
        billing_addr_dict = {}
        if self.street or self.street2:
            billing_addr_dict["BillingStreet"] = self.street or "" + self.street2 or ""
        billing_addr_dict["BillingCity"] = self.city if self.city else ""
        billing_addr_dict["BillingState"] = self.state_id.name if self.state_id else ""
        billing_addr_dict["BillingPostalCode"] = self.zip if self.zip else ""
        billing_addr_dict["BillingCountry"] = (
            self.country_id.name if self.country_id else ""
        )
        company_dict.update(billing_addr_dict)
        return company_dict

    @api.model
    def _scheduler_export_companies_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            companies = self.search(
                [
                    ("x_is_updated", "=", False),
                    ("id", "not in", [1, 2, 3]),
                    ("is_company", "=", True),
                ],
                limit=sf_config.export_limit,
            )
        else:
            companies = self.search(
                [
                    ("x_is_updated", "=", False),
                    ("id", "not in", [1, 2, 3]),
                    ("is_company", "=", True),
                ]
            )

        for company in companies:
            try:
                sf_company_dict = company.create_company_sf_dict()
                if company.x_salesforce_id:
                    company.update_partner_in_sf(sf_company_dict, is_from_cron=True)
                else:
                    company.create_partner_in_sf(sf_company_dict, is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  creating/updating partner in SALESFORCE %s", e
                )

    @api.model
    def _scheduler_export_contacts_to_sf(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            contacts = self.search(
                [
                    ("x_is_updated", "=", False),
                    ("id", "not in", [1, 2, 3]),
                    ("is_company", "=", False),
                    ("type", "=", "contact"),
                ],
                limit=sf_config.export_limit,
            )
        else:
            contacts = self.search(
                [
                    ("x_is_updated", "=", False),
                    ("id", "not in", [1, 2, 3]),
                    ("is_company", "=", False),
                    ("type", "=", "contact"),
                ]
            )

        for contact in contacts:
            try:
                sf_company_dict = contact.create_contact_sf_dict()
                if contact.x_salesforce_id:
                    contact.update_partner_in_sf(sf_company_dict, is_from_cron=True)
                else:
                    contact.create_partner_in_sf(sf_company_dict, is_from_cron=True)
            except Exception as e:
                _logger.error(
                    "Oops Some error in  creating/updating partner in SALESFORCE %s", e
                )

    def create_contact_sf_delivery_address_dict(self):
        delivery_contact_dict = {}
        delivery_contact_dict["Name"] = self.name
        if self.city:
            delivery_contact_dict["City__c"] = self.city
        if self.parent_id and self.parent_id.x_salesforce_id:
            delivery_contact_dict["Contact_Name__c"] = self.parent_id.x_salesforce_id
            if self.parent_id.is_company and self.parent_id.x_salesforce_id:
                delivery_contact_dict["Account__c"] = self.parent_id.x_salesforce_id

        formatted_address = ""
        if self.street:
            formatted_address += self.street + " "
        if self.street2:
            formatted_address += self.street2 + " "
        if self.city:
            formatted_address += self.city + " "
        if self.state_id:
            formatted_address += self.state_id.name + " "
        if self.country_id:
            formatted_address += self.country_id.name + " "
        if self.zip:
            formatted_address += self.zip + " "
        delivery_contact_dict["Formatted_Address__c"] = formatted_address

        if self.street:
            delivery_contact_dict["Street__c"] = self.street

        return delivery_contact_dict

    def create_partner_delivery_address_in_sf(
        self, delivery_contact_data, is_from_cron=False
    ):
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

        if not is_from_cron and not sf_config:
            raise ValidationError(_("There is no Salesforce instance"))

        if not sf_config.sf_access_token:
            _logger.error("There is no Salesforce instance Access Token.")
            return False

        headers = sf_config.get_sf_headers(True)
        endpoint = "/services/data/v40.0/sobjects/Delivery_Address__c"
        try:
            result = requests.request(
                "POST",
                sf_config.sf_url + endpoint,
                headers=headers,
                data=json.dumps(delivery_contact_data),
                timeout=180,
            )

            if result.status_code in (200, 201):
                parsed_result = result.json()
                if parsed_result.get("id"):
                    self.x_is_updated = True
                    self.x_salesforce_exported = True
                    self.x_last_modified_on = datetime.now()
                    self.x_salesforce_id = parsed_result.get("id")
                    # self.commit()
                    _logger.info("Updated companies in salesforce")
                    sf_config.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contact",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Exported Successfully:- Updated data",
                                    },
                                )
                            ]
                        }
                    )
                    return parsed_result.get("id")
                else:
                    return False
            elif result.status_code == 401:
                sf_config.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "contact",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Export may be ACCESS TOKEN EXPIRED.",
                                },
                            )
                        ]
                    }
                )
                sf_config.refresh_salesforce_token_from_access_token(
                    is_cron=is_from_cron
                )
                _logger.info("ACCESS TOKEN EXPIRED, GETTING NEW REFRESH TOKEN...")
                return False
            else:
                parsed_json = result.json()
                sf_config.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "contact",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": (
                                        "Enable to Export:- %s."
                                        % (str(parsed_json[0].get("message")))
                                    ),
                                },
                            )
                        ]
                    }
                )
                _logger.error(
                    "response Of Partner creation in salesforce  (%s)",
                    str(parsed_json[0].get("message")),
                )
                return False

        except Exception as e:
            if is_from_cron:
                _logger.error("Something went wrong :- ", e)
                return False
            else:
                raise ValidationError(_("Something went wrong"))

    @api.model
    def exportPartner_to_sf(self):
        active_ids = self.env.context.get("active_ids")
        if not active_ids:
            raise UserError(_("No ids selected"))
        account_id = False
        for partner in self.browse(active_ids):
            if partner.is_company:
                sf_company_dict = partner.create_company_sf_dict()
                if partner.x_salesforce_id:
                    partner.update_partner_in_sf(sf_company_dict)
                else:
                    partner.create_partner_in_sf(sf_company_dict)
            elif not partner.is_company:
                sf_company_dict = partner.create_contact_sf_dict()

                if partner.x_salesforce_id:
                    partner.update_partner_in_sf(sf_company_dict)
                    delivery_addresses = partner.child_ids.filtered(
                        lambda l: l.type == "delivery" and l.x_salesforce_id is False
                    )
                    if delivery_addresses:
                        for dla in delivery_addresses:
                            sf_contact_delivery_address_dict = (
                                dla.create_contact_sf_delivery_address_dict()
                            )
                            dla.create_partner_delivery_address_in_sf(
                                sf_contact_delivery_address_dict
                            )
                else:
                    partner.create_partner_in_sf(sf_company_dict)

                    # this is for adding the delivery address
                    delivery_addresses = partner.child_ids.filtered(
                        lambda l: l.type == "delivery" and l.x_salesforce_id is False
                    )
                    if delivery_addresses:
                        for dla in delivery_addresses:
                            sf_contact_delivery_address_dict = (
                                dla.create_contact_sf_delivery_address_dict()
                            )
                            dla.create_partner_delivery_address_in_sf(
                                sf_contact_delivery_address_dict
                            )
