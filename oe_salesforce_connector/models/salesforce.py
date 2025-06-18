import base64
import json
import logging
from datetime import datetime

import requests
from dateutil.parser import parse as duparse

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SalesForceMaster(models.Model):
    _name = "salesforce.instance"

    @api.model
    def _default_update_datetime(self):
        date = str(datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S"))
        return datetime.strptime("2020-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")

    # Company level QuickBooks Configuration fields
    name = fields.Char()
    sf_client_id = fields.Char(
        string="Consumer Key",
        help="The client ID you obtain from the developer dashboard.",
    )
    sf_client_secret = fields.Char(
        string="Consumer Secret",
        help="The client secret you obtain from the developer dashboard.",
    )

    sf_auth_base_url = fields.Char(
        string="Authorization URL",
        default="https://login.salesforce.com/services/oauth2/authorize",
        help="User authenticate uri",
    )
    sf_access_token_url = fields.Char(
        string="Authorization Token URL",
        default="https://login.salesforce.com/services/oauth2/token",
        help="Exchange code for refresh and access tokens",
    )
    sf_request_token_url = fields.Char(
        string="Redirect URL",
        default="http://localhost:8069/get_auth_code_from_sf",
        help="One of the redirect URIs listed for this project in the developer dashboard.",
    )
    sf_url = fields.Char(
        string="Instance URL",
        default="https://",
        help="SalesForce API URIs, use access token to call SalesForce API's",
    )

    # used for api calling, generated during authorization process.
    sf_auth_code = fields.Char(string="Auth Code")
    sf_access_token = fields.Char(
        string="Access Token",
        help="The token that must be used to access the SALESFORCE API.",
    )
    sf_refresh_token = fields.Char(string="Refresh Token")

    account_lastmodifieddate = fields.Datetime(
        string="Account Last Modified Time :- ", default=_default_update_datetime
    )
    contact_lastmodifieddate = fields.Datetime(
        string="Contact Last Modified Time :- ", default=_default_update_datetime
    )
    product_lastmodifieddate = fields.Datetime(
        string="Product Last Modified Time :- ", default=_default_update_datetime
    )
    quote_lastmodifieddate = fields.Datetime(
        string="Quotation Last Modified Time :- ", default=_default_update_datetime
    )
    order_lastmodifieddate = fields.Datetime(
        string="Sale Order Last Modified Time :- ", default=_default_update_datetime
    )
    lead_lastmodifieddate = fields.Datetime(
        string="Lead Last Modified Time :- ", default=_default_update_datetime
    )
    opportunity_lastmodifieddate = fields.Datetime(
        string="Opportunity Last Modified Time :- ", default=_default_update_datetime
    )
    contract_lastmodifieddate = fields.Datetime(
        string="Contract Last Modified Time :- ", default=_default_update_datetime
    )
    event_lastmodifieddate = fields.Datetime(
        string="Event Last Modified Time :- ", default=_default_update_datetime
    )
    task_lastmodifieddate = fields.Datetime(
        string="Task Last Modified Time :- ", default=_default_update_datetime
    )

    company_id = fields.Many2one(
        "res.company",
        string="Company",
        required=True,
        default=lambda self: self.env.company.id,
        readonly=True,
        store=True,
    )
    import_limit = fields.Integer(default=50)
    export_limit = fields.Integer(default=50)
    is_default_instance = fields.Boolean(string="Is default Instance for Cron")
    salesforce_instance_line_ids = fields.One2many(
        "salesforce.instance.line",
        "salesforce_instance_id",
        string="Salesforce Instance Line",
    )

    @api.model
    def _scheduler_salesforce_login_aunthetication(self, is_cron=False):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config and not is_cron:
            raise ValidationError(_("There is no Salesforce instance"))
        sf_config.refresh_salesforce_token_from_access_token(is_cron=True)

    def salesforce_login(self):
        url = (
            self.sf_auth_base_url
            + "?client_id="
            + self.sf_client_id
            + "&redirect_uri="
            + self.sf_request_token_url
            + "&response_type=code&display=popup"
        )
        return {"type": "ir.actions.act_url", "url": url, "target": "new"}

    @api.model
    def create(self, vals):
        result = super().create(vals)

        if self.search_count([("company_id", "=", result.company_id.id)]) > 1:
            raise ValidationError(_("Can't create two instance for the same company"))

        if vals.get("is_default_instance"):
            if self.search_count([("is_default_instance", "=", True)]) > 1:
                raise ValidationError(_("Can't create two instance as default"))

        return result

    def write(self, vals):
        if vals.get("company_id"):
            if self.search_count([("company_id", "=", vals.get("company_id"))]) >= 1:
                raise ValidationError(
                    _("Can't Update two instance for the same company")
                )

        if vals.get("is_default_instance"):
            if self.search_count([("is_default_instance", "=", True)]) >= 1:
                raise ValidationError(_("Can't create two instance as default"))

        return super().write(vals)

    def sanitize_sf_data(self, field_to_sanitize):
        """
        This method sanitizes the data to remove UPPERCASE and
        spaces between field chars
        @params : field_to_sanitize(char)
        @returns : field_to_sanitize(char)
        """
        return field_to_sanitize.strip()

    def get_sf_headers(self, type=False):
        headers = {}
        headers["Authorization"] = "Bearer " + str(self.sf_access_token)
        headers["accept"] = "application/json"
        if type:
            headers["Content-Type"] = "application/json"
        else:
            headers["Content-Type"] = "text/plain"

        return headers

    def salesforce_test(self):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v39.0/sobjects/connectedapplication",
                headers=headers,
                timeout=180,
            )

            if data.status_code == 200:
                return self.sf_sendMessage("CONNECTION SUCCESSFUL")
            if data.status_code == 401:
                self.refresh_salesforce_token_from_access_token()
                return self.sf_sendMessage("Session expired or invalid")
            else:
                raise UserError(_("CONNECTION UNSUCCESSFUL"))

    def refresh_salesforce_token_from_access_token(self, is_cron=False):
        """
        This method gets access token from refresh token
        and grant type is refresh_token,
        This token will be long-lived.
        """
        if not is_cron and not self.sf_refresh_token:
            raise UserError(_("Please authenticate first."))
        elif is_cron and not self.sf_refresh_token:
            _logger.error("Please authenticate first.")
            return False

        refresh_token_data = {}
        headers = {"content-type": "application/x-www-form-urlencoded"}
        sf_refresh_token = self.sanitize_sf_data(self.sf_refresh_token)
        sf_client_id = self.sanitize_sf_data(self.sf_client_id)
        sf_client_secret = self.sanitize_sf_data(self.sf_client_secret)
        sf_url = self.sanitize_sf_data(self.sf_url)

        refresh_token_data.update(
            {
                "grant_type": "refresh_token",
                "refresh_token": sf_refresh_token,
                "client_id": sf_client_id,
                "client_secret": sf_client_secret,
            }
        )
        refresh_token_response = requests.post(
            sf_url + "/services/oauth2/token",
            data=refresh_token_data,
            headers=headers,
            timeout=180,
        )
        if refresh_token_response.status_code == 200:
            try:
                # try getting JSON repr of it
                parsed_response = refresh_token_response.json()
                if "access_token" in parsed_response:
                    _logger.info(
                        "REFRESHING ACCESS TOKEN {}".format(
                            parsed_response.get("access_token")
                        )
                    )
                    self.sf_access_token = parsed_response.get("access_token")
            except Exception as ex:
                if not is_cron:
                    raise UserError(_(f"EXCEPTION : {ex}"))
                else:
                    _logger.error(f"EXCEPTION : {ex}")
                    return False
        elif refresh_token_response.status_code == 401:
            _logger.error("Access token/refresh token is expired")
        else:
            if not is_cron:
                raise UserError(
                    _(f"We got a issue !!!! Desc : {refresh_token_response.text}")
                )
            else:
                _logger.error(
                    f"We got a issue !!!! Desc : {refresh_token_response.text}"
                )

    @api.model
    def _scheduler_salesforce_login_authentication(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.refresh_salesforce_token_from_access_token(is_cron=True)

    def salesforce_login(self):
        url = (
            self.sf_auth_base_url
            + "?client_id="
            + self.sf_client_id
            + "&redirect_uri="
            + self.sf_request_token_url
            + "&response_type=code&display=popup"
        )
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
            "context": {"default_instance": self.id},
        }

    def sf_sendMessage(self, message):
        view_ref = self.env["ir.model.data"]._xmlid_to_res_id(
            "oe_salesforce_connector.salseforce_message_wizard_form"
        )
        if view_ref:
            return {
                "type": "ir.actions.act_window",
                "name": "Message",
                "res_model": "salseforce.message.wizard",
                "view_type": "form",
                "view_mode": "form",
                "view_id": view_ref or False,
                "context": {"message": message},
                "target": "new",
                "nodestroy": True,
            }

    def fetch_sf_cust_details(self, sf_id, is_account=False):
        """
        This Function fetches customer data from salesforce
        """
        if self.sf_access_token:
            headers = self.get_sf_headers(True)

            if is_account:
                endpoint = "/services/data/v40.0/sobjects/account/" + str(sf_id)

                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )
            else:
                endpoint = "/services/data/v40.0/sobjects/Contact/" + str(sf_id)

                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )

            if data.status_code == 200:
                if data.text:
                    parsed_json = json.loads(str(data.text))
                    return parsed_json
            else:
                return False

    def sf_createOdooParentId_Activity(self, sf_account_id, search_for):
        if sf_account_id:
            # """ GET DICTIONARY FROM QUICKBOOKS FOR CREATING A DICT """
            if search_for == "account":
                data = self.fetch_sf_cust_details(sf_account_id, is_account=True)
            else:
                data = self.fetch_sf_cust_details(sf_account_id)
            if data:
                cust = data
                if cust:
                    # """
                    #     Check if the Id from Salesforce is present in odoo or not if present
                    #     then dont insert, This will avoid duplications
                    # """
                    res_partner = self.env["res.partner"].search(
                        [("x_salesforce_id", "=", sf_account_id)], limit=1
                    )
                    if res_partner:
                        return res_partner.id
                    if not res_partner:
                        dict = {}
                        if cust.get("Phone"):
                            dict["phone"] = cust.get("Phone")
                        if cust.get("Email"):
                            dict["email"] = cust.get("Email")
                        if cust.get("Name"):
                            dict["name"] = cust.get("Name")
                        # if cust.get('Active'):
                        #     if str(cust.get('Active')) == 'true':
                        #         dict['active']=True
                        #     else:
                        #         dict['active']=False
                        if cust.get("Id"):
                            dict["x_salesforce_id"] = cust.get("Id")
                        if cust.get("Description"):
                            dict["comment"] = cust.get("Description")
                        dict["is_company"] = True
                        if cust.get("MobilePhone"):
                            dict["mobile"] = cust.get("MobilePhone")
                        # if cust.get('Fax'):
                        #     dict['fax'] = cust.get('Fax')
                        if cust.get("Website"):
                            dict["website"] = cust.get("Website")
                        dict["company_type"] = "company"
                        # nt "DICT TO ENTER IS : {}".format(dict)
                        create = res_partner.sudo().create(dict)
                        if create:
                            if cust.get("BillingAddress"):
                                # """
                                #     Getting BillAddr from salesforce and Checking
                                #     in odoo to get countryId, stateId and create
                                #     state if not exists in odoo
                                # """
                                dict = {}
                                # """
                                #     Get state id if exists else create new state and return it
                                # """
                                if cust.get("BillingAddress").get("state"):
                                    state_id = self.sf_attachCustomerState(
                                        cust.get("BillingAddress").get("state"),
                                        cust.get("BillingAddress").get(
                                            "country",
                                            cust.get("BillingAddress").get("state"),
                                        ),
                                    )
                                    if state_id:
                                        dict["state_id"] = state_id
                                country = cust.get("BillingAddress").get(
                                    "country", False
                                )
                                if country:
                                    country_id = self.env["res.country"].search(
                                        [("name", "=", country)], limit=1
                                    )
                                    if country_id:
                                        dict["country_id"] = country_id.id
                                    else:
                                        code = country[:2]
                                        code_exist = self.env["res.country"].search(
                                            [("code", "=", code)]
                                        )
                                        if code_exist:
                                            dict["country_id"] = code_exist.id
                                        else:
                                            country_id = (
                                                self.env["res.country"]
                                                .sudo()
                                                .create({"name": country, "code": code})
                                            )
                                            dict["country_id"] = country_id.id

                                dict["parent_id"] = create.id
                                dict["type"] = "invoice"
                                dict["zip"] = cust.get("BillingAddress").get(
                                    "postalCode", " "
                                )
                                dict["city"] = cust.get("BillingAddress").get("city")
                                dict["street"] = cust.get("BillingAddress").get(
                                    "street"
                                )
                                child_create = res_partner.sudo().create(dict)
                            if cust.get("ShippingAddress"):
                                # """
                                #     Getting ShippingAddress from salesforce and Checking
                                #     in odoo to get countryId, stateId and create
                                #     state if not exists in odoo
                                # """
                                dict = {}
                                if cust.get("ShippingAddress").get("state"):
                                    state_id = self.sf_attachCustomerState(
                                        cust.get("ShippingAddress").get("state"),
                                        cust.get("ShippingAddress").get("country"),
                                    )
                                    if state_id:
                                        dict["state_id"] = state_id
                                country = cust.get("ShippingAddress").get("country")
                                if country:
                                    country_id = self.env["res.country"].search(
                                        [("name", "=", country)], limit=1
                                    )
                                    if country_id:
                                        dict["country_id"] = country_id.id
                                    else:
                                        code = country[:2]
                                        code_exist = self.env["res.country"].search(
                                            [("code", "=", code)]
                                        )
                                        if code_exist:
                                            dict["country_id"] = code_exist.id
                                        else:
                                            country_id = self.env["res.country"].create(
                                                {"name": country, "code": code}
                                            )
                                            dict["country_id"] = country_id.id
                                dict["parent_id"] = create.id
                                dict["type"] = "delivery"
                                dict["zip"] = cust.get("ShippingAddress").get(
                                    "postalCode", " "
                                )
                                dict["city"] = cust.get("ShippingAddress").get("city")
                                dict["street"] = cust.get("ShippingAddress").get(
                                    "street"
                                )
                                child_create = res_partner.sudo().create(dict)
                                if child_create:
                                    pass
                                # self.x_quickbooks_last_customer_sync = fields.Datetime.now()
                                # self.x_quickbooks_last_customer_imported_id = int(cust.get('Id'))
                            return create.id

    def sf_createOdooParentId(self, sf_account_id):
        if sf_account_id:
            # """
            #     GET DICTIONARY FROM QUICKBOOKS FOR CREATING A DICT
            # """

            data = self.fetch_sf_cust_details(sf_account_id, is_account=True)
            if data:
                cust = data
                if cust:
                    # if int(cust.get('Id')) > self.x_quickbooks_last_customer_imported_id:
                    # """
                    #     Check if the Id from Salesforce is present in odoo or not if present
                    #     then dont insert, This will avoid duplications
                    # """
                    res_partner = self.env["res.partner"].search(
                        [("x_salesforce_id", "=", sf_account_id)], limit=1
                    )
                    if res_partner:
                        return res_partner.id
                    if not res_partner:
                        dict = {}
                        if cust.get("Phone"):
                            dict["phone"] = cust.get("Phone")
                        if cust.get("Email"):
                            dict["email"] = cust.get("Email")
                        if cust.get("Name"):
                            dict["name"] = cust.get("Name")
                        # if cust.get('Active'):
                        #     if str(cust.get('Active')) == 'true':
                        #         dict['active']=True
                        #     else:
                        #         dict['active']=False
                        if cust.get("Id"):
                            dict["x_salesforce_id"] = cust.get("Id")
                        if cust.get("Description"):
                            dict["comment"] = cust.get("Description")
                        dict["is_company"] = True
                        if cust.get("MobilePhone"):
                            dict["mobile"] = cust.get("MobilePhone")
                        # if cust.get('Fax'):
                        #     dict['fax'] = cust.get('Fax')
                        if cust.get("Website"):
                            dict["website"] = cust.get("Website")
                        dict["company_type"] = "company"
                        # nt "DICT TO ENTER IS : {}".format(dict)
                        create = res_partner.sudo().create(dict)
                        if create:
                            if cust.get("BillingAddress"):
                                # """
                                #     Getting BillAddr from salesforce and Checking
                                #     in odoo to get countryId, stateId and create
                                #     state if not exists in odoo
                                # """
                                dict = {}
                                # """
                                #     Get state id if exists else create new state and return it
                                # """
                                if cust.get("BillingAddress").get("state"):
                                    state_id = self.sf_attachCustomerState(
                                        cust.get("BillingAddress").get("state"),
                                        cust.get("BillingAddress").get(
                                            "country",
                                            cust.get("BillingAddress").get("state"),
                                        ),
                                    )
                                    if state_id:
                                        dict["state_id"] = state_id
                                country = cust.get("BillingAddress").get(
                                    "country", False
                                )
                                if country:
                                    country_id = self.env["res.country"].search(
                                        [("name", "=", country)], limit=1
                                    )
                                    if country_id:
                                        dict["country_id"] = country_id.id
                                    else:
                                        code = country[:2]
                                        code_exist = self.env["res.country"].search(
                                            [("code", "=", code)]
                                        )
                                        if code_exist:
                                            dict["country_id"] = code_exist.id
                                        else:
                                            country_id = self.env["res.country"].create(
                                                {"name": country, "code": code}
                                            )
                                            dict["country_id"] = country_id.id

                                dict["parent_id"] = create.id
                                dict["type"] = "invoice"
                                dict["zip"] = cust.get("BillingAddress").get(
                                    "postalCode", " "
                                )
                                dict["city"] = cust.get("BillingAddress").get("city")
                                dict["street"] = cust.get("BillingAddress").get(
                                    "street"
                                )
                                child_create = res_partner.sudo().create(dict)
                            if cust.get("ShippingAddress"):
                                # """
                                #     Getting ShippingAddress from salesforce and Checking
                                #     in odoo to get countryId, stateId and create
                                #     state if not exists in odoo
                                # """
                                dict = {}
                                if cust.get("ShippingAddress").get("state"):
                                    state_id = self.sf_attachCustomerState(
                                        cust.get("ShippingAddress").get("state"),
                                        cust.get("ShippingAddress").get("country"),
                                    )
                                    if state_id:
                                        dict["state_id"] = state_id
                                country = cust.get("ShippingAddress").get("country")
                                if country:
                                    country_id = self.env["res.country"].search(
                                        [("name", "=", country)], limit=1
                                    )
                                    if country_id:
                                        dict["country_id"] = country_id.id
                                    else:
                                        code = country[:2]
                                        code_exist = self.env["res.country"].search(
                                            [("code", "=", code)]
                                        )
                                        if code_exist:
                                            dict["country_id"] = code_exist.id
                                        else:
                                            country_id = self.env["res.country"].create(
                                                {"name": country, "code": code}
                                            )
                                            dict["country_id"] = country_id.id
                                dict["parent_id"] = create.id
                                dict["type"] = "delivery"
                                dict["zip"] = cust.get("ShippingAddress").get(
                                    "postalCode", " "
                                )
                                dict["city"] = cust.get("ShippingAddress").get("city")
                                dict["street"] = cust.get("ShippingAddress").get(
                                    "street"
                                )
                                child_create = res_partner.sudo().create(dict)
                                if child_create:
                                    pass
                                # self.x_quickbooks_last_customer_sync = fields.Datetime.now()
                                # self.x_quickbooks_last_customer_imported_id = int(cust.get('Id'))
                            return create.id

    def sf_attachCustomerTitle(self, title):
        res_partner_tile = self.env["res.partner.title"]
        title_id = False
        if title:
            title_id = res_partner_tile.search([("name", "=", title)], limit=1)
            if not title_id:
                # """ Create New Title in Odoo """
                create_id = res_partner_tile.create({"name": title})
                create_id = title_id.id
                if create_id:
                    return create_id.id
        return title_id.id

    def sf_attachCustomerState(self, state, country):
        res_partner_country = self.env["res.country"]
        res_partner_state = self.env["res.country.state"]
        state_id = False
        if state and country:
            country_id = res_partner_country.search([("name", "=", country)], limit=1)
            if country_id:
                state_id = res_partner_state.search([("name", "=", state)], limit=1)
                if state_id and state_id.country_id.id == country_id[0].id:
                    return state_id.id
                else:
                    # """ Create New State Under Country Id """
                    partner_exists = res_partner_state.search(
                        [("name", "=", state)], limit=1
                    )
                    if not partner_exists:
                        new_state_id = res_partner_state.sudo().create(
                            {"country_id": country_id.id, "code": state, "name": state}
                        )
                        if new_state_id:
                            return new_state_id.id
                    else:
                        return partner_exists.id

    def create_sf_contact(self, sf_contact_data):
        sf_modified_dt = self.convert_sfdate_toodoo(
            sf_contact_data.get("LastModifiedDate")
        )
        sf_cust_det = self.fetch_sf_cust_details(sf_contact_data.get("Id"))
        res_partner_srch = self.env["res.partner"].search(
            [
                ("x_salesforce_id", "=", str(sf_contact_data.get("Id"))),
                ("type", "=", "contact"),
            ],
            limit=1,
        )
        if res_partner_srch:
            if res_partner_srch.x_last_modified_on:
                if sf_modified_dt > res_partner_srch.x_last_modified_on:
                    contact_dict = self.create_odoo_sf_contact_dictionary(sf_cust_det)

                    parent_record_written = res_partner_srch.sudo().write(contact_dict)
                    return True
                else:
                    return True
            else:
                contact_dict = self.create_odoo_sf_contact_dictionary(sf_cust_det)
                parent_record_written = res_partner_srch.sudo().write(contact_dict)
                return True
        else:
            contact_dict = self.create_odoo_sf_contact_dictionary(sf_cust_det)
            partner_create_id = self.env["res.partner"].sudo().create(contact_dict)
            return True
        return False

    def import_sf_contacts(self):
        if self.sf_access_token:
            headers = self.get_sf_headers()
            temp_odoo_date = self.contact_lastmodifieddate
            sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

            query_url = ""
            if self.import_limit:
                query_url = f"/services/data/v40.0/query/?q=select Id, LastModifiedDate from contact where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
            else:
                query_url = f"/services/data/v40.0/query/?q=select Id, LastModifiedDate from contact where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

            contact_data = requests.request(
                "GET", self.sf_url + query_url, headers=headers, timeout=180
            )
            if contact_data.status_code in (200, 201):
                contact_parsed_data = json.loads(str(contact_data.text))
                _logger.info(
                    "Total Contacts in salesforce to import : %s ",
                    (str(contact_parsed_data.get("totalSize"))),
                )

                if contact_parsed_data.get("records"):
                    for contact in contact_parsed_data.get("records"):
                        try:
                            result = self.create_sf_contact(contact)
                            if result:
                                self.contact_lastmodifieddate = (
                                    self.convert_sfdate_toodoo(
                                        contact.get("LastModifiedDate")
                                    )
                                )
                                self._cr.commit()
                        except Exception as e:
                            _logger.error(
                                "Oops Some error in  creating/updating record from SALESFORCE Contact %s",
                                e,
                            )
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contact",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Imported Successfully",
                                    },
                                )
                            ]
                        }
                    )
                else:
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contact",
                                        "date_time": datetime.now(),
                                        "state": "nothing",
                                        "message": "Nothing to Import.",
                                    },
                                )
                            ]
                        }
                    )
            elif contact_data.status_code == 401:
                _logger.warning("Invalid Session")
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "contact",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import, may be Invalid Session.",
                                },
                            )
                        ]
                    }
                )
                self.refresh_salesforce_token_from_access_token()
            else:
                _logger.warning("Exception searching Contact %s ", contact_data.text)
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "contact",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import:- Exception searching Contact.",
                                },
                            )
                        ]
                    }
                )

    def import_sf_cust(self, product_partner=False, is_account=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()
                data = None

                dummy_dict = {}

                if (
                    product_partner != False
                    and not type(product_partner) == type(dummy_dict)
                    and is_account == False
                ):
                    endpoint = ""
                    if self.import_limit:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Contact where Id='{product_partner}' LIMIT {self.import_limit}"
                    else:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Contact where Id='{product_partner}'"
                    data = requests.request(
                        "GET", self.sf_url + endpoint, headers=headers, timeout=180
                    )
                elif (
                    is_account
                    and product_partner != False
                    and not type(product_partner) == type(dummy_dict)
                ):
                    endpoint = ""
                    if self.import_limit:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Account where Id='{product_partner}' LIMIT {self.import_limit}"
                    else:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Account where Id='{product_partner}'"

                    data = requests.request(
                        "GET", self.sf_url + endpoint, headers=headers, timeout=180
                    )
                elif is_account:
                    endpoint = ""
                    if self.import_limit:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Account LIMIT {product_partner}"
                    else:
                        endpoint = (
                            "/services/data/v40.0/query/?q=select Id from Account"
                        )

                    data = requests.request(
                        "GET", self.sf_url + endpoint, headers=headers, timeout=180
                    )
                else:
                    endpoint = ""
                    if self.import_limit:
                        endpoint = f"/services/data/v40.0/query/?q=select Id from Account LIMIT {product_partner}"
                    else:
                        endpoint = (
                            "/services/data/v40.0/query/?q=select Id from Account"
                        )

                    data = requests.request(
                        "GET", self.sf_url + endpoint, headers=headers, timeout=180
                    )

                if data:
                    recs = []
                    parsed_data = json.loads(str(data.text))
                    if parsed_data:
                        ids_lst = []
                        # loop in array and grab
                        if parsed_data.get("records"):
                            for pdata in parsed_data.get("records"):
                                if pdata.get("Id"):
                                    ids_lst.append(pdata.get("Id"))
                        if ids_lst:
                            for id in ids_lst:
                                if is_account:
                                    sf_cust_det = self.fetch_sf_cust_details(
                                        id, is_account=True
                                    )
                                else:
                                    pass
                                    sf_cust_det = self.fetch_sf_cust_details(id)
                                if sf_cust_det:
                                    # """ Check if the Id from Salesforce is present in odoo or not if present
                                    # then dont insert, This will avoid duplications"""
                                    res_partner = self.env["res.partner"].search(
                                        [
                                            (
                                                "x_salesforce_id",
                                                "=",
                                                str(sf_cust_det.get("Id")),
                                            )
                                        ]
                                    )
                                    dict = {}

                                    if sf_cust_det.get("Title"):
                                        dict["function"] = sf_cust_det.get("Title")

                                    if sf_cust_det.get("Phone"):
                                        dict["phone"] = sf_cust_det.get("Phone")
                                    if sf_cust_det.get("Email"):
                                        dict["email"] = sf_cust_det.get("Email")

                                    if sf_cust_det.get("Name"):
                                        dict["name"] = sf_cust_det.get("Name")
                                        # if cust.get('Active'):
                                        #     if str(cust.get('Active')) == 'true':
                                        #         dict['active']=True
                                        #     else:
                                        #         dict['active']=False
                                    if sf_cust_det.get("AccountId"):
                                        result = self.sf_createOdooParentId(
                                            sf_cust_det.get("AccountId")
                                        )
                                        if result:
                                            dict["parent_id"] = result
                                    if sf_cust_det.get("attributes").get("type"):
                                        if (
                                            sf_cust_det.get("attributes").get("type")
                                            == "Account"
                                        ):
                                            dict["company_type"] = "company"
                                        else:
                                            dict["company_type"] = "person"

                                    if sf_cust_det.get("Id"):
                                        dict["x_salesforce_id"] = sf_cust_det.get("Id")
                                    if sf_cust_det.get("Description"):
                                        dict["comment"] = sf_cust_det.get("Description")
                                    if sf_cust_det.get("AccountId"):
                                        dict["company_type"] = "person"
                                    if sf_cust_det.get("MobilePhone"):
                                        dict["mobile"] = sf_cust_det.get("MobilePhone")
                                    # if sf_cust_det.get('Fax'): not available in odoo 12 commented by priya
                                    #     dict['fax'] = sf_cust_det.get('Fax')
                                    if sf_cust_det.get("Salutation"):
                                        # """ If Title is present then first check in odoo if title exists or not
                                        # if exists attach Id of tile else create new and attach its ID"""
                                        dict["title"] = self.sf_attachCustomerTitle(
                                            sf_cust_det.get("Salutation")
                                        )
                                    if not res_partner:
                                        create = res_partner.sudo().create(dict)
                                        if create:
                                            recs.append(create.id)
                                            if not sf_cust_det.get("AccountId"):
                                                if sf_cust_det.get("MailingAddress"):
                                                    # """ Getting BillAddr from quickbooks and Checking
                                                    #     in odoo to get countryId, stateId and create
                                                    #     state if not exists in odoo
                                                    #     """
                                                    dict = {}
                                                    # """
                                                    # Get state id if exists else create new state and return it
                                                    # """
                                                    if sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("state"):
                                                        state_id = (
                                                            self.sf_attachCustomerState(
                                                                sf_cust_det.get(
                                                                    "MailingAddress"
                                                                ).get("state"),
                                                                sf_cust_det.get(
                                                                    "MailingAddress"
                                                                ).get("country"),
                                                            )
                                                        )
                                                        if state_id:
                                                            dict["state_id"] = state_id
                                                    country = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("country", False)
                                                    if country:
                                                        country_id = self.env[
                                                            "res.country"
                                                        ].search(
                                                            [("name", "=", country)],
                                                            limit=1,
                                                        )
                                                        if country_id:
                                                            dict["country_id"] = (
                                                                country_id.id
                                                            )
                                                        else:
                                                            code = country[:2]
                                                            code_exist = self.env[
                                                                "res.country"
                                                            ].search(
                                                                [("code", "=", code)]
                                                            )
                                                            if code_exist:
                                                                dict["country_id"] = (
                                                                    code_exist.id
                                                                )
                                                            else:
                                                                country_id = (
                                                                    self.env[
                                                                        "res.country"
                                                                    ]
                                                                    .sudo()
                                                                    .create(
                                                                        {
                                                                            "name": country,
                                                                            "code": code,
                                                                        }
                                                                    )
                                                                )
                                                                dict["country_id"] = (
                                                                    country_id.id
                                                                )
                                                    dict["parent_id"] = create.id
                                                    dict["type"] = "invoice"
                                                    dict["zip"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("postalCode", " ")
                                                    dict["city"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("city")
                                                    dict["street"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("street")
                                                    child_create = (
                                                        res_partner.sudo().create(dict)
                                                    )
                                                    # if sf_cust_det.get('MailingAddress'):
                                                    # """ Getting BillAddr from quickbooks and Checking
                                                    #     in odoo to get countryId, stateId and create
                                                    #     state if not exists in odoo
                                                    #     """
                                                    dict = {}
                                                    # """
                                                    # Get state id if exists else create new state and return it
                                                    # """
                                                    if sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("state"):
                                                        state_id = (
                                                            self.sf_attachCustomerState(
                                                                sf_cust_det.get(
                                                                    "MailingAddress"
                                                                ).get("state"),
                                                                sf_cust_det.get(
                                                                    "MailingAddress"
                                                                ).get("country"),
                                                            )
                                                        )
                                                        if state_id:
                                                            dict["state_id"] = state_id
                                                    country = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("country", False)
                                                    if country:
                                                        country_id = self.env[
                                                            "res.country"
                                                        ].search(
                                                            [("name", "=", country)],
                                                            limit=1,
                                                        )
                                                        if country_id:
                                                            dict["country_id"] = (
                                                                country_id.id
                                                            )
                                                        else:
                                                            code = country[:2]
                                                            code_exist = self.env[
                                                                "res.country"
                                                            ].search(
                                                                [("code", "=", code)]
                                                            )
                                                            if code_exist:
                                                                dict["country_id"] = (
                                                                    code_exist.id
                                                                )
                                                            else:
                                                                country_id = (
                                                                    self.env[
                                                                        "res.country"
                                                                    ]
                                                                    .sudo()
                                                                    .create(
                                                                        {
                                                                            "name": country,
                                                                            "code": code,
                                                                        }
                                                                    )
                                                                )
                                                                dict["country_id"] = (
                                                                    country_id.id
                                                                )
                                                    dict["parent_id"] = create.id
                                                    dict["type"] = "delivery"
                                                    dict["zip"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("postalCode", " ")
                                                    dict["city"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("city")
                                                    dict["street"] = sf_cust_det.get(
                                                        "MailingAddress"
                                                    ).get("street")
                                                    child_create = (
                                                        res_partner.sudo().create(dict)
                                                    )
                                            # self.x_quickbooks_last_customer_sync = fields.Datetime.now()
                                    else:
                                        res_partner.sudo().write(dict)
                        if recs:
                            return recs
                            #         self.x_quickbooks_last_customer_imported_id = max(recs)
                            # else:
                            #     dict = {}
                            #     if sf_cust_det.get('PrimayPhone'):
                            #         dict['phone'] = sf_cust_det.get('PrimaryPhone').get('FreeFormNumber',' ')
                            #
                            #     if sf_cust_det.get('PrimaryEmailAddr'):
                            #         dict['email'] = sf_cust_det.get('PrimaryEmailAddr').get('Address', ' ')
                            #     write = res_partner.write(dict)
                            #     if write :

        except Exception as e:
            raise UserError(_("Oops Some error Occurred" + str(e)))

    def fetch_sf_product_details(self, rec):
        """
        HIT SF FOR GETTING INDV PRODUCT DETAILS
        """
        if self.sf_access_token:
            headers = {}
            headers["Authorization"] = "Bearer " + str(self.sf_access_token)
            headers["accept"] = "application/json"
            headers["Content-Type"] = "text/plain"
            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/product2/" + str(rec),
                headers=headers,
                timeout=180,
            )
            file_data = requests.request(
                "GET",
                self.sf_url
                + "/services/data/v40.0/sobjects/ContentDocument/06904000000IMuCAAW",
                headers=headers,
                timeout=180,
            )
            if file_data.status_code:
                file_data1 = json.loads(str(file_data.text))
            if data.status_code == 200:
                if data.text:
                    products_data = json.loads(str(data.text))
                    return products_data
            else:
                return False

    def create_sf_Product(self, product_dict, sf_id):
        product_obj = self.env["product.product"]
        headers = self.get_sf_headers()

        product_exists = product_obj.search([("x_salesforce_id", "=", sf_id)])
        if not product_exists:
            if product_dict:
                res = product_obj.sudo().create(product_dict)
                if res:
                    # """ Write x_salesforce_id """
                    res.sudo().write({"x_salesforce_id": sf_id})
                    # data = requests.request('GET',
                    #                         self.sf_url + "/services/data/v40.0/query/?q=select UnitPrice, Pricebook2Id, Id from PricebookEntry where Product2Id='{}'".format(
                    #                             sf_id), headers=headers)
                    # if data.status_code == 200:
                    #     if data.text:
                    #         pricebookentry_data = json.loads(str(data.text))
                    #         for pricebook in pricebookentry_data.get('records'):
                    #             res.x_salesforce_pbe = pricebook.get('Id')
                    return res.id
                else:
                    return False
            else:
                return False
        else:
            # """ Write Product Data """
            if not product_exists.x_salesforce_pbe:
                data = requests.request(
                    "GET",
                    self.sf_url
                    + f"/services/data/v40.0/query/?q=select UnitPrice, Pricebook2Id, Id from PricebookEntry where Product2Id='{sf_id}'",
                    headers=headers,
                    timeout=180,
                )
                if data.status_code == 200:
                    if data.text:
                        pricebookentry_data = json.loads(str(data.text))
                        for pricebook in pricebookentry_data.get("records"):
                            product_exists.x_salesforce_pbe = pricebook.get("Id")
            product_exists.sudo().write(product_dict)

    def attach_sf_ProductCategory(self, categ_name):
        product_categ_obj = self.env["product.category"]

        product_categ_exists = product_categ_obj.search([("name", "=", categ_name)])
        if product_categ_exists:
            return product_categ_exists.id
        else:
            product_categ_create = product_categ_obj.sudo().create({"name": categ_name})
            if product_categ_create:
                return product_categ_create.id
            else:
                return False

    def getSfProductPrice(self, sf_id):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            query_url = ""
            if self.import_limit:
                query_url = f"/services/data/v40.0/query/?q=select UnitPrice from pricebookentry where Product2Id='{str(sf_id)}' LIMIT {self.import_limit}"
            else:
                query_url = f"/services/data/v40.0/query/?q=select UnitPrice from pricebookentry where Product2Id='{str(sf_id)}'"

            data = requests.request(
                "GET", self.sf_url + query_url, headers=headers, timeout=180
            )
            if data.status_code:
                product_list_price = 0
                recs = []
                parsed_data = json.loads(str(data.text))
                if parsed_data:
                    if (
                        parsed_data
                        and parsed_data.get("records")
                        and parsed_data.get("records")[0]
                    ):
                        product_list_price = parsed_data.get("records")[0].get(
                            "UnitPrice"
                        )
                        if product_list_price:
                            return product_list_price
                else:
                    return False
            else:
                return False

    def import_sf_products(self, is_from_cron=False):
        headers = self.get_sf_headers()
        temp_odoo_date = self.product_lastmodifieddate
        sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))
        url = ""

        if self.import_limit:
            url = f"/services/data/v40.0/query/?q=select Id from Product2 where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
        else:
            url = f"/services/data/v40.0/query/?q=select Id from Product2 where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

        data = requests.request("GET", self.sf_url + url, headers=headers, timeout=180)

        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()
                temp_odoo_date = self.product_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))
                query_url = ""
                if self.import_limit:
                    query_url = f"/services/data/v40.0/query/?q=select Id from Product2 where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
                else:
                    query_url = f"/services/data/v40.0/query/?q=select Id from Product2 where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

                data = requests.request(
                    "GET", self.sf_url + query_url, headers=headers, timeout=180
                )
                file_data = requests.request(
                    "GET",
                    self.sf_url
                    + "/services/data/v40.0/query/?q=select Id from ContentDocument",
                    headers=headers,
                    timeout=180,
                )

                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                product_dict = {}
                                product_read = self.fetch_sf_product_details(rec)
                                # """ PREPARE DICT FOR INSERTING IN PRODUCT.TEMPLATE """

                                if product_read.get("Name"):
                                    product_dict["name"] = product_read.get("Name")

                                if product_read.get("IsActive"):
                                    product_dict["active"] = product_read.get(
                                        "IsActive"
                                    )

                                if product_read.get("Description"):
                                    product_dict["description"] = product_read.get(
                                        "Description"
                                    )
                                    product_dict["description_sale"] = product_read.get(
                                        "Description"
                                    )

                                if product_read.get("ProductCode"):
                                    product_dict["default_code"] = product_read.get(
                                        "ProductCode"
                                    )

                                # """ GET PRICELISTENTRY AND ATTACH TO PRICE """
                                product_price = self.getSfProductPrice(
                                    product_read.get("Id")
                                )
                                if product_price:
                                    product_dict["list_price"] = product_price

                                if product_dict:
                                    # """ PRODUCT CATEGORY ATTACHMENT """
                                    if product_read.get("Family"):
                                        # """ SEARCH PRODUCT CATEGORY ELSE CREATE AND ATTACH NEW CATEG ID """
                                        categ_result = self.attach_sf_ProductCategory(
                                            product_read.get("Family")
                                        )
                                        if categ_result:
                                            product_dict["categ_id"] = categ_result
                                    self.create_sf_Product(
                                        product_dict, product_read.get("Id")
                                    )
                                    self.product_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            product_read.get("LastModifiedDate")
                                        )
                                    )
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "product",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "product",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token()
                else:
                    _logger.warning("Exception searching Products %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "product",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Products.",
                                    },
                                )
                            ]
                        }
                    )

        except Exception as e:
            if not is_from_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    def getSfQuoteData(self, quote_id):
        if self.sf_access_token:
            headers = self.get_sf_headers()
            data = requests.request(
                "GET",
                self.sf_url + f"/services/data/v40.0/sobjects/quote/{str(quote_id)}",
                headers=headers,
                timeout=180,
            )

            if data:
                if data.text:
                    parsed_data = json.loads(str(data.text))
                    if parsed_data:
                        return parsed_data
                    else:
                        return False
                else:
                    return False
            else:
                return False

    def getSfQuoteLineData(
        self, quote_id=None, quote_dict=None, is_so=False, so_id=None, is_cron=False
    ):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            endpoint = ""
            if is_so and so_id:
                endpoint = f"/services/data/v40.0/query/?q=select Id from orderitem where OrderId='{str(so_id)}'"
            else:
                endpoint = f"/services/data/v40.0/query/?q=select Id from quotelineitem where QuoteId='{str(quote_id)}'"

            if self.import_limit:
                endpoint += f"LIMIT {str(self.import_limit)}"

            data = requests.request(
                "GET", self.sf_url + endpoint, headers=headers, timeout=180
            )

            if data.status_code == 200:
                if data.text:
                    quote_item_ids = []
                    parsed_data = json.loads(str(data.text))
                    if parsed_data:
                        for rec in parsed_data.get("records"):
                            if rec.get("Id"):
                                quote_item_ids.append(str(rec.get("Id")))
                        # """ READ ITEM IDS DATA """
                        if quote_item_ids:
                            quote_line_lst = []
                            for q in quote_item_ids:
                                quote_line_dict = {}
                                if is_so and so_id:
                                    endpoint = (
                                        f"/services/data/v40.0/sobjects/orderitem/{q}"
                                    )
                                else:
                                    endpoint = f"/services/data/v39.0/sobjects/quotelineitem/{q}"
                                data = requests.request(
                                    "GET",
                                    self.sf_url + endpoint,
                                    headers=headers,
                                    timeout=180,
                                )
                                if data.status_code == 200:
                                    if data.text:
                                        parsed_data = json.loads(str(data.text))
                                        if parsed_data.get("Quantity"):
                                            quote_line_dict["product_uom_qty"] = (
                                                parsed_data.get("Quantity")
                                            )
                                        if parsed_data.get("UnitPrice"):
                                            quote_line_dict["price_unit"] = (
                                                parsed_data.get("UnitPrice")
                                            )
                                        if parsed_data.get("Discount"):
                                            quote_line_dict["discount"] = (
                                                parsed_data.get("Discount")
                                            )
                                        if parsed_data.get("Description"):
                                            quote_line_dict["name"] = parsed_data.get(
                                                "Description"
                                            )
                                        if quote_dict:
                                            if (
                                                "Tax" in quote_dict
                                                and "Subtotal" in quote_dict
                                            ):
                                                if (
                                                    quote_dict["Tax"]
                                                    and quote_dict["TotalPrice"]
                                                ):
                                                    order_total_price = round(
                                                        quote_dict["TotalPrice"], 2
                                                    )
                                                    calculated_tax = round(
                                                        (
                                                            (
                                                                quote_dict["Tax"]
                                                                / order_total_price
                                                            )
                                                            * 100
                                                        ),
                                                        7,
                                                    )
                                                    if calculated_tax:
                                                        account_tax = (
                                                            self.env["account.tax"]
                                                            .sudo()
                                                            .search(
                                                                [
                                                                    (
                                                                        "price_include",
                                                                        "=",
                                                                        False,
                                                                    ),
                                                                    (
                                                                        "amount",
                                                                        "=",
                                                                        calculated_tax,
                                                                    ),
                                                                ],
                                                                limit=1,
                                                            )
                                                        )
                                                        if account_tax:
                                                            custom_tax_id = [
                                                                (6, 0, [account_tax.id])
                                                            ]
                                                        else:
                                                            # if not self.country_id and not is_cron:
                                                            #     raise UserError('Please set the Country for Company')
                                                            # else:
                                                            #     _logger.error("Please set the Country for Company")
                                                            #     return False

                                                            custom_tax_id = (
                                                                self.env["account.tax"]
                                                                .sudo()
                                                                .create(
                                                                    {
                                                                        "name": str(
                                                                            calculated_tax
                                                                        )
                                                                        + "%",
                                                                        "type_tax_use": "sale",
                                                                        "amount": calculated_tax,
                                                                        # 'country_id': self.country_id.id
                                                                    }
                                                                )
                                                            )
                                                        quote_line_dict["tax_id"] = (
                                                            custom_tax_id
                                                        )
                                                else:
                                                    quote_line_dict["tax_id"] = None
                                            else:
                                                quote_line_dict["tax_id"] = None

                                        if parsed_data.get("Product2Id"):
                                            pass
                                        if parsed_data.get("Id"):
                                            quote_line_dict["Id"] = parsed_data.get(
                                                "Id"
                                            )
                                            # Check if product2Id is present in odoo or not, If present then
                                            # attach its id else create new product and attach its id

                                            product_exists = self.env[
                                                "product.product"
                                            ].search(
                                                [
                                                    (
                                                        "x_salesforce_id",
                                                        "=",
                                                        str(
                                                            parsed_data.get(
                                                                "Product2Id"
                                                            )
                                                        ),
                                                    )
                                                ]
                                            )
                                            if product_exists:
                                                quote_line_dict["product_id"] = (
                                                    product_exists.id
                                                )
                                            else:
                                                # """ READ PRODUCT DATA FROM API """
                                                endpoint = "/services/data/v40.0/sobjects/product2/{}".format(
                                                    str(parsed_data.get("Product2Id"))
                                                )
                                                data = requests.request(
                                                    "GET",
                                                    self.sf_url + endpoint,
                                                    headers=headers,
                                                    timeout=180,
                                                )

                                                if data.status_code == 200:
                                                    if data.text:
                                                        product_dict = {}
                                                        # """ GRAB DATA """
                                                        parsed_data = json.loads(
                                                            str(data.text)
                                                        )
                                                        product_read = parsed_data

                                                        if product_read.get("Name"):
                                                            product_dict["name"] = (
                                                                product_read.get("Name")
                                                            )

                                                        if product_read.get("IsActive"):
                                                            product_dict["active"] = (
                                                                product_read.get(
                                                                    "IsActive"
                                                                )
                                                            )

                                                        if product_read.get(
                                                            "Description"
                                                        ):
                                                            product_dict[
                                                                "description"
                                                            ] = product_read.get(
                                                                "Description"
                                                            )
                                                            product_dict[
                                                                "description_sale"
                                                            ] = product_read.get(
                                                                "Description"
                                                            )

                                                        if product_read.get(
                                                            "ProductCode"
                                                        ):
                                                            product_dict[
                                                                "default_code"
                                                            ] = product_read.get(
                                                                "ProductCode"
                                                            )

                                                        # """ GET PRICELISTENTRY AND ATTACH TO PRICE """
                                                        product_price = (
                                                            self.getSfProductPrice(
                                                                product_read.get("Id")
                                                            )
                                                        )
                                                        if product_price:
                                                            product_dict[
                                                                "list_price"
                                                            ] = product_price
                                                        if product_dict:
                                                            # """ PRODUCT CATEGORY ATTACHMENT """
                                                            if product_read.get(
                                                                "Family"
                                                            ):
                                                                # """ SEARCH PRODUCT CATEGORY ELSE CREATE AND ATTACH NEW CATEG ID """
                                                                categ_result = self.attach_sf_ProductCategory(
                                                                    product_read.get(
                                                                        "Family"
                                                                    )
                                                                )
                                                                if categ_result:
                                                                    product_dict[
                                                                        "categ_id"
                                                                    ] = categ_result
                                                            result = (
                                                                self.create_sf_Product(
                                                                    product_dict,
                                                                    product_read.get(
                                                                        "Id"
                                                                    ),
                                                                )
                                                            )
                                                            if result:
                                                                quote_line_dict[
                                                                    "product_id"
                                                                ] = result
                                                            else:
                                                                pass
                                quote_line_lst.append(quote_line_dict)
                            if quote_line_lst:
                                return quote_line_lst

                                #         quote_line_lst.append(quote_line_dict)
                                # if quote_line_lst:
                                #     return quote_line_lst
                    else:
                        return False
                else:
                    return False

    def getSfQuoteCustomer(self, opp_id):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url
                + f"/services/data/v40.0/sobjects/opportunity/{str(opp_id)}",
                headers=headers,
                timeout=180,
            )

            if data.status_code == 200:
                if data.text:
                    recs = json.loads(str(data.text))
                    if recs:
                        cust_name = recs.get("Name")
                        cust_exists = self.env["res.partner"].search(
                            [("display_name", "=", cust_name)], limit=1
                        )
                        if cust_exists:
                            return cust_exists.id
                        else:
                            # Create Customer
                            cust_create = (
                                self.env["res.partner"]
                                .sudo()
                                .create({"name": recs.get("Name")})
                            )
                            if cust_create:
                                cust_create.sudo().write(
                                    {"x_salesforce_id": recs.get("Id")}
                                )
                                return cust_create.id
                            else:
                                return False
                            return False
                    else:
                        return False

    def import_sf_quote(self, is_from_cron=False):
        # try:
        if self.sf_access_token:
            headers = self.get_sf_headers()
            salesforce_sale_order_id = ""

            temp_odoo_date = self.quote_lastmodifieddate
            sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

            query_url = ""
            if self.import_limit:
                query_url = f"/services/data/v40.0/query/?q=select Id from quote where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
            else:
                query_url = f"/services/data/v40.0/query/?q=select Id from quote where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

            data = requests.request(
                "GET", self.sf_url + query_url, headers=headers, timeout=180
            )

            if data.status_code in (200, 201):
                if data.text:
                    recs = json.loads(str(data.text))
                    if recs:
                        if recs.get("records"):
                            for r in recs.get("records"):
                                quote_dict = {}
                                sf_quotation_line_list = []
                                quote_data = self.getSfQuoteData(r.get("Id"))

                                if quote_data:
                                    if not quote_data.get(
                                        "OpportunityId"
                                    ) and not quote_data.get("ContactId"):
                                        _logger.info(
                                            "No Partner Or Opportunity Selected On Quote %s so skipped please select that first",
                                            quote_data.get("QuoteNumber"),
                                        )
                                        continue

                                    # """ Prepare Required Dict for quotations object """

                                    # Extract billing and shipping addresses
                                    billing = quote_data.get("BillingAddress", {})
                                    shipping = quote_data.get("ShippingAddress", {})

                                    if billing:
                                        # Format the addresses in a structured way
                                        billing_address = "\n".join(
                                            [
                                                f"Street: {billing.get('street', '')}",
                                                f"City: {billing.get('city', '')}",
                                                f"State: {billing.get('state', '')}",
                                                f"Postal Code: {billing.get('postalCode', '')}",
                                                f"Country: {billing.get('country', '')}",
                                            ]
                                        )
                                        quote_dict["x_order_billing_address"] = (
                                            billing_address
                                        )
                                    if shipping:
                                        shipping_address = "\n".join(
                                            [
                                                f"Street: {shipping.get('street', '')}",
                                                f"City: {shipping.get('city', '')}",
                                                f"State: {shipping.get('state', '')}",
                                                f"Postal Code: {shipping.get('postalCode', '')}",
                                                f"Country: {shipping.get('country', '')}",
                                            ]
                                        )
                                        quote_dict["x_order_shipping_address"] = (
                                            shipping_address
                                        )

                                    quote_dict["x_salesforce_ref"] = quote_data.get(
                                        "QuoteNumber"
                                    )
                                    quote_dict["note"] = quote_data.get("Description")
                                    quote_dict["validity_date"] = quote_data.get(
                                        "ExpirationDate"
                                    )
                                    quote_dict["x_salesforce_quote_name"] = (
                                        quote_data.get("Name")
                                    )

                                    # """ GET QUOTE LINES """
                                    quote_line_data = self.getSfQuoteLineData(
                                        quote_id=r.get("Id"),
                                        quote_dict=quote_data,
                                        is_cron=is_from_cron,
                                    )
                                    if quote_line_data:
                                        for quote_line in quote_line_data:
                                            sf_quotation_line_list.append(
                                                quote_line.get("Id")
                                            )
                                    # """ GET CUSTOMER """
                                    if (
                                        quote_data.get("OpportunityId")
                                        and not quote_data.get("ContactId")
                                        and not quote_data.get("AccountId")
                                        and not is_from_cron
                                    ):
                                        # READ OPPORTUNITY and get customer name
                                        # quote_cust_data = self.getSfQuoteCustomer(quote_data.get('OpportunityId'))
                                        # if quote_cust_data:
                                        #     quote_dict['partner_id'] = quote_cust_data
                                        raise UserError(
                                            _(
                                                "Please add Account Id for %s Opportunity in Salesforce",
                                                quote_data.get("OpportunityId"),
                                            )
                                        )

                                    if quote_data.get("OpportunityId"):
                                        lead_id = (
                                            self.env["crm.lead"]
                                            .sudo()
                                            .search(
                                                [
                                                    ("type", "=", "opportunity"),
                                                    (
                                                        "x_salesforce_id_oppo",
                                                        "=",
                                                        quote_data.get("OpportunityId"),
                                                    ),
                                                ]
                                            )
                                        )
                                        if lead_id:
                                            quote_dict["opportunity_id"] = lead_id.id

                                    if quote_data.get("ContactId"):
                                        # Check if contact ID exists or not, If yes then create that custom First
                                        ext_partner_id = self.env["res.partner"].search(
                                            [
                                                (
                                                    "x_salesforce_id",
                                                    "=",
                                                    quote_data.get("ContactId"),
                                                )
                                            ]
                                        )
                                        if ext_partner_id:
                                            quote_dict["partner_id"] = ext_partner_id.id
                                        else:
                                            partner_id = self.import_sf_cust(
                                                product_partner=quote_data.get(
                                                    "ContactId"
                                                )
                                            )
                                            if partner_id:
                                                quote_dict["partner_id"] = partner_id[0]

                                    if quote_data.get("Tax"):
                                        quote_dict["amount_tax"] = quote_data.get("Tax")
                                    else:
                                        quote_dict["amount_tax"] = None

                                    if quote_data.get("ExpirationDate"):
                                        quote_dict["validity_date"] = quote_data.get(
                                            "ExpirationDate"
                                        )

                                    if quote_data.get("AccountId"):
                                        ext_partner_id = self.env["res.partner"].search(
                                            [
                                                (
                                                    "x_salesforce_id",
                                                    "=",
                                                    quote_data.get("AccountId"),
                                                )
                                            ]
                                        )
                                        if ext_partner_id:
                                            quote_dict["partner_id"] = ext_partner_id.id
                                        else:
                                            # Check if contact ID exists or not, If yes then create that custom First
                                            partner_id = self.import_sf_cust(
                                                product_partner=str(
                                                    quote_data.get("AccountId")
                                                ),
                                                is_account=True,
                                            )
                                            if partner_id:
                                                quote_dict["partner_id"] = partner_id[0]

                                    if quote_dict:
                                        # Create Quotation
                                        # Check if quotation doesn't exist
                                        quote_exists = self.env["sale.order"].search(
                                            [
                                                (
                                                    "x_salesforce_id",
                                                    "=",
                                                    quote_data.get("Id"),
                                                )
                                            ]
                                        )
                                        if not quote_exists:
                                            if quote_data.get("CurrencyIsoCode"):
                                                currency_code = quote_data.get(
                                                    "CurrencyIsoCode"
                                                )
                                                pricelist_id = self.get_pricelist(
                                                    currency_code
                                                )
                                                if pricelist_id:
                                                    quote_dict["pricelist_id"] = (
                                                        pricelist_id.id
                                                    )
                                            quote_create = (
                                                self.env["sale.order"]
                                                .sudo()
                                                .create(quote_dict)
                                            )
                                            if quote_create:
                                                shipping_cost = quote_data.get(
                                                    "ShippingHandling"
                                                )
                                                if shipping_cost:
                                                    self.run_shipping_cost_process(
                                                        quote_create, shipping_cost
                                                    )
                                                else:
                                                    self.run_shipping_cost_process(
                                                        quote_create, 0
                                                    )
                                                self._process_attachments(
                                                    r.get("Id"), quote_create.id
                                                )
                                                quote_create.sudo().write(
                                                    {
                                                        "x_salesforce_id": quote_data.get(
                                                            "Id"
                                                        )
                                                    }
                                                )
                                                self.quote_lastmodifieddate = (
                                                    self.convert_sfdate_toodoo(
                                                        quote_data.get(
                                                            "LastModifiedDate"
                                                        )
                                                    )
                                                )
                                                _logger.info(
                                                    "Quotation is created in odoo %s",
                                                    quote_create.id,
                                                )

                                                # Attach Order id to sale order line
                                                order_line = {}

                                                if quote_line_data:
                                                    for soline in quote_line_data:
                                                        soline["product_uom"] = 1
                                                        soline["order_id"] = (
                                                            quote_create.id
                                                        )
                                                        # Check if quotation line dose not exists
                                                        quote_line_exists = self.env[
                                                            "sale.order.line"
                                                        ].search(
                                                            [
                                                                (
                                                                    "x_salesforce_id",
                                                                    "=",
                                                                    soline.get("Id"),
                                                                )
                                                            ]
                                                        )
                                                        if not quote_line_exists:
                                                            soline.update(
                                                                {
                                                                    "x_salesforce_id": soline.get(
                                                                        "Id"
                                                                    )
                                                                }
                                                            )
                                                            salesforce_sale_order_id = (
                                                                soline.get("Id")
                                                            )
                                                            soline.pop("Id")
                                                            quote_line_create = (
                                                                self.env[
                                                                    "sale.order.line"
                                                                ].create(soline)
                                                            )
                                                            if quote_line_create:
                                                                rec_quote_line_create = quote_line_create.sudo().write(
                                                                    {
                                                                        "x_salesforce_id": salesforce_sale_order_id
                                                                    }
                                                                )
                                                                quote_line_create._cr.commit()
                                        else:
                                            if (
                                                quote_exists
                                                and quote_exists.state == "draft"
                                            ):
                                                if quote_data.get("CurrencyIsoCode"):
                                                    currency_code = quote_data.get(
                                                        "CurrencyIsoCode"
                                                    )
                                                    pricelist_id = self.get_pricelist(
                                                        currency_code
                                                    )
                                                    if pricelist_id:
                                                        quote_dict["pricelist_id"] = (
                                                            pricelist_id.id
                                                        )
                                            rec_update_so = quote_exists.sudo().write(
                                                quote_dict
                                            )
                                            shipping_cost = quote_data.get(
                                                "ShippingHandling"
                                            )
                                            if shipping_cost:
                                                self.run_shipping_cost_process(
                                                    quote_exists, shipping_cost
                                                )
                                            else:
                                                self.run_shipping_cost_process(
                                                    quote_exists, 0
                                                )
                                            self._process_attachments(
                                                r.get("Id"), quote_exists.id
                                            )
                                            if rec_update_so:
                                                _logger.info(
                                                    "Quotation is updated in odoo %s",
                                                    quote_exists.id,
                                                )

                                            self.quote_lastmodifieddate = (
                                                self.convert_sfdate_toodoo(
                                                    quote_data.get("LastModifiedDate")
                                                )
                                            )
                                            # Attach Order id to sale order line
                                            order_line = {}
                                            if quote_line_data:
                                                for soline in quote_line_data:
                                                    soline["product_uom"] = 1
                                                    soline["order_id"] = quote_exists.id
                                                    # Check if quotation line dose not exists
                                                    quote_line_exists = self.env[
                                                        "sale.order.line"
                                                    ].search(
                                                        [
                                                            (
                                                                "x_salesforce_id",
                                                                "=",
                                                                soline.get("Id"),
                                                            )
                                                        ]
                                                    )
                                                    salesforce_sale_order_id = (
                                                        soline.get("Id")
                                                    )
                                                    soline.pop("Id")
                                                    if not quote_line_exists:
                                                        soline.update(
                                                            {
                                                                "x_salesforce_id": salesforce_sale_order_id
                                                            }
                                                        )

                                                        quote_line_create = (
                                                            self.env["sale.order.line"]
                                                            .sudo()
                                                            .create(soline)
                                                        )
                                                        if quote_line_create:
                                                            quote_line_write_rec = quote_line_create.sudo().write(
                                                                {
                                                                    "x_salesforce_id": salesforce_sale_order_id
                                                                }
                                                            )
                                                            quote_line_create._cr.commit()
                                                    else:
                                                        rec_soline_write = quote_line_exists.sudo().write(
                                                            soline
                                                        )
                                        odoo_sale_order_line = []
                                        sale_order_id = (
                                            self.env["sale.order"]
                                            .sudo()
                                            .search(
                                                [
                                                    (
                                                        "x_salesforce_id",
                                                        "=",
                                                        quote_data.get("Id"),
                                                    ),
                                                    ("state", "=", "draft"),
                                                ],
                                                limit=1,
                                            )
                                        )
                                        if sale_order_id:
                                            sale_order_line_ids = (
                                                self.env["sale.order.line"]
                                                .sudo()
                                                .search(
                                                    [
                                                        (
                                                            "order_id",
                                                            "=",
                                                            sale_order_id.id,
                                                        )
                                                    ]
                                                )
                                            )
                                            if sale_order_line_ids:
                                                for line_id in sale_order_line_ids:
                                                    if line_id.x_salesforce_id:
                                                        odoo_sale_order_line.append(
                                                            line_id.x_salesforce_id
                                                        )
                                                delete_order_line_list = []
                                                if (
                                                    len(odoo_sale_order_line) > 0
                                                    and len(sf_quotation_line_list) > 0
                                                ):
                                                    for odoo_id in odoo_sale_order_line:
                                                        if (
                                                            odoo_id
                                                            not in sf_quotation_line_list
                                                        ):
                                                            delete_order_line_list.append(
                                                                odoo_id
                                                            )
                                                if len(delete_order_line_list) > 0:
                                                    for (
                                                        line_id
                                                    ) in delete_order_line_list:
                                                        sale_order_line_id = (
                                                            self.env["sale.order.line"]
                                                            .sudo()
                                                            .search(
                                                                [
                                                                    (
                                                                        "x_salesforce_id",
                                                                        "=",
                                                                        line_id,
                                                                    )
                                                                ],
                                                                limit=1,
                                                            )
                                                        )
                                                        res_delete_rec = (
                                                            sale_order_line_id.unlink()
                                                        )
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "sale_quotation",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "sale_quotation",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
            elif data.status_code == 401:
                _logger.warning("Invalid Session")
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "sale_quotation",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import, may be Invalid Session.",
                                },
                            )
                        ]
                    }
                )
                self.refresh_salesforce_token_from_access_token()
            else:
                _logger.warning("Exception searching Sale Quotations %s ", data.text)
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "sale_quotation",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import:- Exception searching Sale Quotations.",
                                },
                            )
                        ]
                    }
                )

    def get_pricelist(self, currency_iso):
        pricelist = self.env["product.pricelist"].search(
            [("currency_id.name", "=", currency_iso)], limit=1
        )
        if pricelist:
            return pricelist
        else:
            return None

    def run_shipping_cost_process(self, quote_id, shipping_cost):
        line_exists = quote_id.order_line.filtered(
            lambda line: line.sf_shipping_cost_line
        )
        if line_exists and shipping_cost == 0:
            line_exists.unlink()
        elif shipping_cost != 0:
            shipping_product_id = self.env.ref(
                "oe_salesforce_connector.product_shipping_handling"
            )
            if shipping_product_id:
                if not line_exists:
                    quote_id.order_line = [
                        (
                            0,
                            0,
                            {
                                "product_id": shipping_product_id.id,  # ID of "Shipping and Handling" product
                                "name": "Shipping and Handling",
                                "price_unit": shipping_cost,  # Pass shipping cost from Salesforce
                                "product_uom_qty": 1,
                                "sf_shipping_cost_line": True,
                            },
                        )
                    ]
                else:
                    quote_id.order_line = [
                        (
                            1,
                            line_exists.id,
                            {
                                "product_id": shipping_product_id.id,  # ID of "Shipping and Handling" product
                                "name": "Shipping and Handling",
                                "price_unit": shipping_cost,  # Pass shipping cost from Salesforce
                                "product_uom_qty": 1,
                                "sf_shipping_cost_line": True,
                            },
                        )
                    ]

    def _process_attachments(self, salesforce_id, sale_order_id):
        attachments = self.get_sf_quote_attachments(salesforce_id)
        if attachments:
            for file_name, file_data, sf_doc_id in attachments:
                existing_attachment = self.env["ir.attachment"].search(
                    [("x_salesforce_document_id", "=", sf_doc_id)], limit=1
                )

                if not existing_attachment:
                    attachment_vals = {
                        "name": file_name,
                        "res_model": "sale.order",
                        "res_id": sale_order_id,
                        "datas": base64.b64encode(file_data).decode("utf-8"),
                        "type": "binary",
                        "x_salesforce_document_id": sf_doc_id,
                    }
                    self.env["ir.attachment"].sudo().create(attachment_vals)
                    _logger.info(
                        f"Attachment {file_name} added to Sale Order {sale_order_id}"
                    )

    def get_sf_quote_attachments(self, quote_id):
        """Fetch attachments related to a given Salesforce Quote."""
        headers = self.get_sf_headers()

        # Step 1: Get ContentDocumentId for the Quote
        query_url = f"/services/data/v40.0/query/?q=SELECT ContentDocumentId FROM ContentDocumentLink WHERE LinkedEntityId='{quote_id}'"
        response = requests.get(self.sf_url + query_url, headers=headers, timeout=180)

        if response.status_code in (200, 201):
            content_links = json.loads(response.text)
            attachment_list = []

            for record in content_links.get("records", []):
                content_doc_id = record.get("ContentDocumentId")

                # Step 2: Get Latest Version of the Attachment
                content_query = f"/services/data/v40.0/query/?q=SELECT Id, Title, VersionData FROM ContentVersion WHERE ContentDocumentId='{content_doc_id}' ORDER BY CreatedDate DESC LIMIT 1"
                content_response = requests.get(
                    self.sf_url + content_query, headers=headers, timeout=180
                )

                if content_response.status_code in (200, 201):
                    content_data = json.loads(content_response.text)

                    for content in content_data.get("records", []):
                        file_name = content.get("Title")
                        file_data_url = f"/services/data/v40.0/sobjects/ContentVersion/{content.get('Id')}/VersionData"

                        # Step 3: Download File Data
                        file_response = requests.get(
                            self.sf_url + file_data_url, headers=headers, timeout=180
                        )
                        if file_response.status_code in (200, 201):
                            file_data = file_response.content
                            attachment_list.append(
                                (file_name, file_data, content.get("Id"))
                            )
                        else:
                            _logger.warning(f"Failed to fetch file {file_name}")

            return attachment_list
        else:
            _logger.warning(f"Failed to fetch attachments for Quote {quote_id}")
            return []

    def get_sf_so_cust(self, so_id):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url + f"/services/data/v39.0/sobjects/order/{str(so_id)}",
                headers=headers,
                timeout=180,
            )

            if data.status_code == 200:
                if data.text:
                    recs = json.loads(str(data.text))
                    if recs:
                        cust_name = recs.get("Name")
                        # cust_exists = self.env['res.partner'].search([('display_name', '=', cust_name)], limit=1)
                        cust_exists = self.env["res.partner"].search(
                            [("x_salesforce_id", "=", recs.get("AccountId"))], limit=1
                        )
                        if cust_exists:
                            return cust_exists.id
                        else:
                            # Create Customer
                            if recs.get("AccountId"):
                                partner_id = None
                                ext_partner_id = None
                                # Check if contact Id exists or not, If yes then create that custom First
                                ext_partner_id = self.env["res.partner"].search(
                                    [("x_salesforce_id", "=", recs.get("AccountId"))]
                                )
                                if not ext_partner_id:
                                    partner_id = self.import_sf_cust(
                                        product_partner=str(recs.get("AccountId")),
                                        is_account=True,
                                    )
                                if partner_id:
                                    return partner_id[0]
                                elif ext_partner_id:
                                    return ext_partner_id.id
                                else:
                                    return False
                    else:
                        return False

    def get_sf_so_data(self, sf_id):
        sf_order_dict = {}
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url + f"/services/data/v40.0/sobjects/order/{str(sf_id)}",
                headers=headers,
                timeout=180,
            )

            if data.status_code == 200:
                if data.text:
                    recs = json.loads(str(data.text))
                    if recs:
                        billing = recs.get("BillingAddress") or {}
                        shipping = recs.get("ShippingAddress") or {}

                        billing_address = ", ".join(
                            filter(
                                None,
                                [
                                    billing.get("street", ""),
                                    billing.get("city", ""),
                                    billing.get("state", ""),
                                    billing.get("postalCode", ""),
                                    billing.get("country", ""),
                                ],
                            )
                        )

                        shipping_address = ", ".join(
                            filter(
                                None,
                                [
                                    shipping.get("street", ""),
                                    shipping.get("city", ""),
                                    shipping.get("state", ""),
                                    shipping.get("postalCode", ""),
                                    shipping.get("country", ""),
                                ],
                            )
                        )

                        sf_order_dict["x_order_billing_address"] = billing_address
                        sf_order_dict["x_order_shipping_address"] = shipping_address

                        sf_order_dict["x_salesforce_ref"] = recs.get("OrderNumber")
                        if recs.get("EffectiveDate"):
                            sf_order_dict["date_order"] = recs.get("EffectiveDate")
                        if recs.get("EndDate"):
                            sf_order_dict["validity_date"] = recs.get("EndDate")
                        if recs.get("Description"):
                            sf_order_dict["note"] = (
                                "Order No:"
                                + recs.get("OrderNumber")
                                + " "
                                + recs.get("Description")
                            )
                        # if recs.get('Tax'):
                        sf_order_dict["amount_tax"] = ""
                        if recs.get("ExpirationDate"):
                            sf_order_dict["validity_date"] = recs.get("ExpirationDate")
                        if recs.get("ContractId"):
                            contract_id = (
                                self.env["sf.contract"]
                                .sudo()
                                .search(
                                    [("x_salesforce_id", "=", recs.get("ContractId"))]
                                )
                            )
                            if contract_id:
                                sf_order_dict["contract_id"] = contract_id.id
                            else:
                                contract_dict = {}
                                contract_read = self.fetch_sf_contract_details(
                                    recs.get("ContractId")
                                )
                                # """ PREPARE DICT FOR INSERTING IN SF.CONTRACT """
                                if contract_read.get("AccountId"):
                                    result = self.sf_createOdooParentId(
                                        contract_read.get("AccountId")
                                    )
                                    if result:
                                        contract_dict["parent_id"] = result
                                if contract_read.get("ContractNumber"):
                                    contract_dict["name"] = contract_read.get(
                                        "ContractNumber"
                                    )
                                if contract_read.get("StartDate"):
                                    contract_dict["contract_start_date"] = (
                                        contract_read.get("StartDate")
                                    )
                                if contract_read.get("ContractTerm"):
                                    contract_dict["contacr_term_month"] = (
                                        contract_read.get("ContractTerm")
                                    )
                                if contract_read.get("Status"):
                                    if contract_read.get("Status") == "Draft":
                                        contract_dict["state"] = "draft"
                                    if contract_read.get("Status") == "Activated":
                                        contract_dict["state"] = "activated"
                                    if (
                                        contract_read.get("Status")
                                        == "In Approval Process"
                                    ):
                                        contract_dict["state"] = "approval"
                                if contract_dict:
                                    contract_id = self.create_sf_Contract(
                                        contract_dict, contract_read.get("Id")
                                    )
                                    if contract_id:
                                        sf_order_dict["contract_id"] = contract_id

            if sf_order_dict:
                return sf_order_dict
            else:
                return False

    def import_sf_so(self, is_from_cron=False):
        # try:
        if self.sf_access_token:
            headers = self.get_sf_headers()
            salesforce_sale_order_id = ""
            temp_odoo_date = self.order_lastmodifieddate
            sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

            endpoint = ""
            if self.import_limit:
                endpoint = f"/services/data/v39.0/query/?q=select Id from order where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
            else:
                endpoint = f"/services/data/v39.0/query/?q=select Id from order where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

            data = requests.request(
                "GET", self.sf_url + endpoint, headers=headers, timeout=180
            )

            if data.status_code in (200, 201):
                if data.text:
                    parsed_data = json.loads(str(data.text))
                    if parsed_data and parsed_data.get("records"):
                        for rec in parsed_data.get("records"):
                            so_line_data = ""
                            so_dict = {}
                            so_data = " "
                            sf_sale_order_line2 = []
                            odoo_sale_order_line = []

                            so_data = self.get_sf_so_data(rec.get("Id"))
                            # so_data['date_order'] = datetime.now()
                            so_cust_id = self.get_sf_so_cust(rec.get("Id"))
                            if so_cust_id:
                                so_data["partner_id"] = so_cust_id

                            if so_data:
                                #                                 Set order status:
                                if rec.get("Status") != "Draft":
                                    so_data["state"] = "sale"
                                # """ GET SO LINES """
                                so_line_data = self.getSfQuoteLineData(
                                    is_so=True,
                                    so_id=str(rec.get("Id")),
                                    quote_dict=so_data,
                                    is_cron=is_from_cron,
                                )
                                if so_line_data:
                                    for so_line_sf_id in so_line_data:
                                        sf_sale_order_line2.append(
                                            so_line_sf_id.get("Id")
                                        )
                                # Check if quotation dosent exists
                                so_exists = self.env["sale.order"].search(
                                    [("sale_order_salesforce_id", "=", rec.get("Id"))],
                                    limit=1,
                                )
                                if not so_exists:
                                    so_create = (
                                        self.env["sale.order"].sudo().create(so_data)
                                    )

                                    if rec.get("LastModifiedDate"):
                                        self.order_lastmodifieddate = (
                                            self.convert_sfdate_toodoo(
                                                rec.get("LastModifiedDate")
                                            )
                                        )
                                    if so_create:
                                        so_create.sudo().write(
                                            {"sale_order_salesforce_id": rec.get("Id")}
                                        )
                                        _logger.info(
                                            "Sale order created in odoo %s",
                                            so_create.id,
                                        )

                                        # Attach Order id to sale order line
                                        order_line = {}

                                        if so_line_data:
                                            for soline in so_line_data:
                                                soline["product_uom"] = 1
                                                soline["order_id"] = so_create.id
                                                soline["tax_id"] = None
                                                # Check if quotation line dosent exists
                                                so_line_exists = self.env[
                                                    "sale.order.line"
                                                ].search(
                                                    [
                                                        (
                                                            "sale_order_line_salesforce_id",
                                                            "=",
                                                            soline.get("Id"),
                                                        )
                                                    ],
                                                    limit=1,
                                                )
                                                salesforce_sale_order_id = soline.get(
                                                    "Id"
                                                )
                                                if not so_line_exists:
                                                    soline.pop("Id")
                                                    so_line_create = (
                                                        self.env["sale.order.line"]
                                                        .sudo()
                                                        .create(soline)
                                                    )
                                                    if so_line_create:
                                                        so_line_create.sudo().write(
                                                            {
                                                                "sale_order_line_salesforce_id": salesforce_sale_order_id
                                                            }
                                                        )
                                                        so_line_create._cr.commit()
                                else:
                                    rec_write_so = so_exists.sudo().write(so_data)
                                    if rec_write_so:
                                        _logger.info(
                                            "Sale order write in odoo %s", so_exists.id
                                        )

                                    if rec.get("LastModifiedDate"):
                                        self.order_lastmodifieddate = (
                                            self.convert_sfdate_toodoo(
                                                rec.get("LastModifiedDate")
                                            )
                                        )
                                    # Attach Order id to sale order line
                                    order_line = {}
                                    if so_line_data:
                                        for soline in so_line_data:
                                            soline["product_uom"] = 1
                                            soline["order_id"] = so_exists.id
                                            soline["tax_id"] = None

                                            # Check if quotation line dosent exists
                                            so_line_exists = self.env[
                                                "sale.order.line"
                                            ].search(
                                                [
                                                    (
                                                        "sale_order_line_salesforce_id",
                                                        "=",
                                                        soline.get("Id"),
                                                    )
                                                ],
                                                limit=1,
                                            )
                                            salesforce_sale_order_id = soline.get("Id")
                                            if not so_line_exists:
                                                soline.update(
                                                    {
                                                        "sale_order_line_salesforce_id": soline.get(
                                                            "Id"
                                                        )
                                                    }
                                                )
                                                soline.pop("Id")
                                                so_line_create = (
                                                    self.env["sale.order.line"]
                                                    .sudo()
                                                    .create(soline)
                                                )
                                                if so_line_create:
                                                    so_line_create.sudo().write(
                                                        {
                                                            "sale_order_line_salesforce_id": salesforce_sale_order_id
                                                        }
                                                    )
                                            else:
                                                soline.pop("Id")
                                                so_line_exists.sudo().write(soline)
                                sale_order_id = (
                                    self.env["sale.order"]
                                    .sudo()
                                    .search(
                                        [
                                            (
                                                "sale_order_salesforce_id",
                                                "=",
                                                rec.get("Id"),
                                            ),
                                            ("state", "=", "sale"),
                                        ],
                                        limit=1,
                                    )
                                )
                                if sale_order_id:
                                    sale_order_line_ids = (
                                        self.env["sale.order.line"]
                                        .sudo()
                                        .search([("order_id", "=", sale_order_id.id)])
                                    )
                                    if sale_order_line_ids:
                                        for line_id in sale_order_line_ids:
                                            if line_id.sale_order_line_salesforce_id:
                                                odoo_sale_order_line.append(
                                                    line_id.sale_order_line_salesforce_id
                                                )
                                delete_order_line_list = []
                                if (
                                    len(odoo_sale_order_line) > 0
                                    and len(sf_sale_order_line2) > 0
                                ):
                                    for odoo_id in odoo_sale_order_line:
                                        if odoo_id not in sf_sale_order_line2:
                                            delete_order_line_list.append(odoo_id)
                                if len(delete_order_line_list) > 0:
                                    for line_id in delete_order_line_list:
                                        sale_order_line_id = (
                                            self.env["sale.order.line"]
                                            .sudo()
                                            .search(
                                                [
                                                    (
                                                        "sale_order_line_salesforce_id",
                                                        "=",
                                                        line_id,
                                                    )
                                                ],
                                                limit=1,
                                            )
                                        )
                                        update_rec_so_line = sale_order_line_id.write(
                                            {"product_uom_qty": 0.0, "price_unit": 0.0}
                                        )
                        self.write(
                            {
                                "salesforce_instance_line_ids": [
                                    (
                                        0,
                                        0,
                                        {
                                            "type": "sale_order",
                                            "date_time": datetime.now(),
                                            "state": "success",
                                            "message": "Imported Successfully",
                                        },
                                    )
                                ]
                            }
                        )
                    else:
                        self.write(
                            {
                                "salesforce_instance_line_ids": [
                                    (
                                        0,
                                        0,
                                        {
                                            "type": "sale_order",
                                            "date_time": datetime.now(),
                                            "state": "nothing",
                                            "message": "Nothing to Import.",
                                        },
                                    )
                                ]
                            }
                        )
            elif data.status_code == 401:
                _logger.warning("Invalid Session")
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "sale_order",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import, may be Invalid Session.",
                                },
                            )
                        ]
                    }
                )
                self.refresh_salesforce_token_from_access_token(is_cron=is_from_cron)
            else:
                _logger.warning("Exception searching Sale Orders %s ", data.text)
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "sale_order",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import:- Exception searching Sale Orders.",
                                },
                            )
                        ]
                    }
                )

    def get_sf_customer_required_details(self, id_to_search, is_account=False):
        """This Function fetches customer or account data from salesforce"""
        headers = self.get_sf_headers()
        if is_account:
            partner_data = requests.request(
                "GET",
                self.sf_url
                + "/services/data/v40.0/sobjects/account/"
                + str(id_to_search),
                headers=headers,
                timeout=180,
            )
        else:
            partner_data = requests.request(
                "GET",
                self.sf_url
                + "/services/data/v40.0/sobjects/contact/"
                + str(id_to_search),
                headers=headers,
                timeout=180,
            )

        if partner_data.status_code == 200:
            if partner_data.text:
                partner_parsed_json = json.loads(str(partner_data.text))
                return partner_parsed_json
        elif partner_data.status_code == 401:
            _logger.warning("ACCESS TOKEN EXPIRED, GETTING NEW REFRESH TOKEN...")
            self.refresh_salesforce_token_from_access_token()
            return False
        else:
            _logger.warning(
                "Bad response from searching Accounts/customer from salesforce :: %s "
                % partner_data.text
            )
            return False

    def create_odoo_sf_contact_dictionary(self, sf_contact_info):
        partner_dict = {}
        if sf_contact_info.get("Title"):
            partner_dict["function"] = sf_contact_info.get("Title")
        if sf_contact_info.get("Phone"):
            partner_dict["phone"] = sf_contact_info.get("Phone")
        if sf_contact_info.get("Email"):
            partner_dict["email"] = sf_contact_info.get("Email")
        if sf_contact_info.get("Name"):
            partner_dict["name"] = sf_contact_info.get("Name")
        if sf_contact_info.get("AccountId"):
            partner_dict["company_type"] = "person"
            sf_cust_dict = {}
            sf_cust_dict["Id"] = sf_contact_info.get("AccountId")
            res_partner_srch = self.env["res.partner"].search(
                [
                    ("x_salesforce_id", "=", str(sf_contact_info.get("AccountId"))),
                    ("type", "=", "contact"),
                ],
                limit=1,
            )
            if res_partner_srch:
                partner_dict["parent_id"] = res_partner_srch.id
            else:
                sf_account_data = self.get_sf_customer_required_details(
                    sf_contact_info.get("AccountId"), is_account=True
                )
                company_dict = self.create_odoo_sf_company_dictionary(sf_account_data)
                company_dict.update({"is_company": True})
                company_rec_id = self.env["res.partner"].sudo().create(company_dict)
                company_rec_id._cr.commit()
                partner_dict["parent_id"] = company_rec_id.id

        if sf_contact_info.get("Id"):
            partner_dict["x_salesforce_id"] = sf_contact_info.get("Id")
        if sf_contact_info.get("Description"):
            partner_dict["comment"] = sf_contact_info.get("Description")
        if sf_contact_info.get("MobilePhone"):
            partner_dict["mobile"] = sf_contact_info.get("MobilePhone")
        if sf_contact_info.get("Salutation"):
            # """ If Title is present then first check in odoo if title exists or not
            # if exists attach Id of tile else partner_create_id new and attach its ID"""
            title_id = self.sf_attachCustomerTitle(sf_contact_info.get("Salutation"))
            partner_dict["title"] = title_id
        sf_parsed_date = fields.Datetime.to_string(
            duparse(sf_contact_info.get("LastModifiedDate"))
        )
        partner_dict["x_last_modified_on"] = sf_parsed_date
        country_id = False

        if sf_contact_info.get("MailingCountry", False):
            if sf_contact_info.get("MailingCountry") in [
                "usa",
                "USA",
                "us",
                "US",
                "United States of America",
                "united states of america",
                "united states",
                "United States",
            ]:
                country_id = self.env["res.country"].search(
                    [("code", "like", "US")], limit=1
                )
                partner_dict["country_id"] = country_id.id
            else:
                country_id = self.env["res.country"].search(
                    [
                        "|",
                        ("name", "=", sf_contact_info.get("MailingCountry")),
                        ("code", "=", sf_contact_info.get("MailingCountry")),
                    ],
                    limit=1,
                )
                if country_id:
                    partner_dict["country_id"] = country_id.id
                else:
                    country = sf_contact_info.get("MailingCountry")
                    code = country[:2] if country else ""
                    code_exist = self.env["res.country"].search([("code", "=", code)])
                    if not code_exist:
                        country_id = (
                            self.env["res.country"]
                            .sudo()
                            .create({"name": country, "code": code})
                        )
                        dict["country_id"] = code_exist.id
                    elif code_exist:
                        dict["country_id"] = code_exist.id
                    else:
                        country_id = (
                            self.env["res.country"]
                            .sudo()
                            .create({"name": country, "code": code})
                        )
                        partner_dict["country_id"] = country_id.id
                    # country_id = self.env['res.country'].sudo().create({'name': sf_contact_info.get('MailingCountry')})
                    # partner_dict['country_id'] = country_id.id
        if sf_contact_info.get("MailingState", False):
            sf_state = sf_contact_info.get("MailingState")
            if country_id:
                state_id = self.env["res.country.state"].search(
                    [
                        "|",
                        ("name", "=", sf_state),
                        ("code", "=", sf_state),
                        ("country_id", "=", country_id.id),
                    ],
                    limit=1,
                )
            else:
                state_id = self.env["res.country.state"].search(
                    ["|", ("name", "=", sf_state), ("code", "=", sf_state)], limit=1
                )
            if state_id:
                partner_dict["state_id"] = state_id.id
            elif sf_state and partner_dict.get("country_id", False):
                state_id = (
                    self.env["res.country.state"]
                    .sudo()
                    .create(
                        {
                            "name": sf_state,
                            "code": sf_state,
                            "country_id": partner_dict.get("country_id"),
                        }
                    )
                )
                partner_dict["state_id"] = state_id.id
        if sf_contact_info.get("MailingPostalCode", False):
            partner_dict["zip"] = sf_contact_info.get("MailingPostalCode")
        if sf_contact_info.get("MailingCity", False):
            partner_dict["city"] = sf_contact_info.get("MailingCity")
        if sf_contact_info.get("MailingStreet", False):
            partner_dict["street"] = sf_contact_info.get("MailingStreet")
        return partner_dict

    def create_odoo_sf_company_dictionary(self, sf_account_info):
        country = sf_account_info.get("BillingAddress") and sf_account_info.get(
            "BillingAddress"
        ).get("country", " ")
        partner_dict = {}
        partner_dict["company_type"] = "company"
        if sf_account_info.get("Phone"):
            partner_dict["phone"] = sf_account_info.get("Phone")
        if sf_account_info.get("Name"):
            partner_dict["name"] = sf_account_info.get("Name")
        if sf_account_info.get("Id"):
            partner_dict["x_salesforce_id"] = sf_account_info.get("Id")
        if sf_account_info.get("Description"):
            partner_dict["comment"] = sf_account_info.get("Description")
        if sf_account_info.get("MobilePhone"):
            partner_dict["mobile"] = sf_account_info.get("MobilePhone")
        # if sf_account_info.get('Fax'):
        #     partner_dict['fax'] = sf_account_info.get('Fax')
        if sf_account_info.get("Website"):
            partner_dict["website"] = sf_account_info.get("Website")
        country_id = False
        if country:
            if country in [
                "usa",
                "USA",
                "us",
                "US",
                "United States of America",
                "united states of america",
                "united states",
                "United States",
            ]:
                country_id = self.env["res.country"].search(
                    [("code", "like", "US")], limit=1
                )
                partner_dict["country_id"] = country_id.id
            else:
                country_id = self.env["res.country"].search(
                    ["|", ("name", "=", country), ("code", "=", country)], limit=1
                )
                if country_id:
                    partner_dict["country_id"] = country_id.id
                else:
                    code = country[:2]
                    code_exist = self.env["res.country"].search([("code", "=", code)])
                    if code_exist:
                        partner_dict["country_id"] = code_exist.id
                    else:
                        country_id = (
                            self.env["res.country"]
                            .sudo()
                            .create({"name": country, "code": code})
                        )
                        partner_dict["country_id"] = country_id.id
        sf_state = sf_account_info.get("BillingAddress") and sf_account_info.get(
            "BillingAddress"
        ).get("state")
        state_id = False
        if sf_state:
            if country_id:
                state_id = self.env["res.country.state"].search(
                    [
                        "|",
                        ("name", "=", sf_state),
                        ("code", "=", sf_state),
                        ("country_id", "=", country_id.id),
                    ],
                    limit=1,
                )
            else:
                state_id = self.env["res.country.state"].search(
                    ["|", ("name", "=", sf_state), ("code", "=", sf_state)], limit=1
                )
            if state_id:
                partner_dict["state_id"] = state_id.id
            elif partner_dict.get("country_id", False):
                state_id = (
                    self.env["res.country.state"]
                    .sudo()
                    .create(
                        {
                            "name": sf_state,
                            "code": sf_state,
                            "country_id": partner_dict.get("country_id"),
                        }
                    )
                )
                partner_dict["state_id"] = state_id.id
        if sf_account_info.get("BillingPostalCode"):
            partner_dict["zip"] = sf_account_info.get("BillingPostalCode")
        if sf_account_info.get("BillingCity"):
            partner_dict["city"] = sf_account_info.get("BillingCity")
        if sf_account_info.get("BillingAddress") and sf_account_info.get(
            "BillingAddress"
        ).get("street"):
            partner_dict["street"] = sf_account_info.get("BillingAddress").get("street")
        sf_modified_dt = self.convert_sfdate_toodoo(
            sf_account_info.get("LastModifiedDate")
        )
        partner_dict["x_last_modified_on"] = fields.Datetime.to_string(sf_modified_dt)
        return partner_dict

    def convert_sfdate_toodoo(self, sf_date):
        str_datetime = duparse(sf_date).strftime("%Y-%m-%d %H:%M:%S")
        odoo_datetime = datetime.strptime(str_datetime, "%Y-%m-%d %H:%M:%S")
        return odoo_datetime

    def create_sf_company(self, sf_account_data):
        # company_id = self.env.user.company_id
        # headers = company_id.get_sf_headers()
        res_partner_srch = self.env["res.partner"].search(
            [
                ("x_salesforce_id", "=", str(sf_account_data.get("Id"))),
                ("type", "=", "contact"),
            ],
            limit=1,
        )
        sf_modified_dt = self.convert_sfdate_toodoo(
            sf_account_data.get("LastModifiedDate")
        )
        sf_account_data = self.get_sf_customer_required_details(
            sf_account_data.get("Id"), is_account=True
        )  # get all data of an account from salesforce

        if res_partner_srch:
            if res_partner_srch.x_last_modified_on:
                if sf_modified_dt > res_partner_srch.x_last_modified_on:
                    company_dict = self.create_odoo_sf_company_dictionary(
                        sf_account_data
                    )
                    parent_record_written = res_partner_srch.sudo().write(company_dict)
                    return True
                else:
                    return True
            else:
                company_dict = self.create_odoo_sf_company_dictionary(sf_account_data)
                parent_record_written = res_partner_srch.sudo().write(company_dict)
                return True

        else:
            company_dict = self.create_odoo_sf_company_dictionary(sf_account_data)
            company_dict.update({"is_company": True})
            company_rec_id = self.env["res.partner"].sudo().create(company_dict)
            company_rec_id._cr.commit()
            return True
        return False

    def convert_odoodt_tosf(self, odoo_date):
        return (
            datetime.strptime(odoo_date, "%Y-%m-%d %H:%M:%S").strftime(
                "%Y-%m-%dT%H:%M:%S.000Z"
            )
            or ""
        )

    def import_sf_accounts(self, is_cron=False):
        if self.sf_access_token:
            headers = self.get_sf_headers()

            temp_odoo_date = self.account_lastmodifieddate
            sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

            query_url = ""
            if self.import_limit:
                query_url = f"""/services/data/v40.0/query/?q=select Id, LastModifiedDate from account where LastModifiedDate > {sf_modified_date} ORDER BY LastModifiedDate LIMIT {self.import_limit}"""
            else:
                query_url = f"""/services/data/v40.0/query/?q=select Id, LastModifiedDate from account where LastModifiedDate > {sf_modified_date} ORDER BY LastModifiedDate"""

            company_data = requests.request(
                "GET", self.sf_url + query_url, headers=headers, timeout=180
            )
            if company_data.status_code in (200, 201):
                acc_parsed_data = json.loads(str(company_data.text))
                _logger.info(
                    "Total Accounts in salesforce to import : %s ",
                    (str(acc_parsed_data.get("totalSize"))),
                )
                _logger.info(
                    "Actual Total Accounts in salesforce response : %s ",
                    (len(acc_parsed_data.get("records"))),
                )
                if acc_parsed_data.get("records"):
                    for i, account in enumerate(acc_parsed_data.get("records")):
                        _logger.info("current record: %s ", i)
                        try:
                            result = self.create_sf_company(account)
                            if result:
                                _logger.info("Account ID %s", account.get("Id"))
                                self.account_lastmodifieddate = (
                                    self.convert_sfdate_toodoo(
                                        account.get("LastModifiedDate")
                                    )
                                )
                        except Exception as e:
                            _logger.error(
                                "Oops Some error in  creating/updating record from SALESFORCE ACCOUNT %s",
                                e,
                            )
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "account",
                                        "date_time": datetime.now(),
                                        "state": "success",
                                        "message": "Imported Successfully",
                                    },
                                )
                            ]
                        }
                    )
                else:
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "account",
                                        "date_time": datetime.now(),
                                        "state": "nothing",
                                        "message": "Nothing to Import.",
                                    },
                                )
                            ]
                        }
                    )
            elif company_data.status_code == 401:
                _logger.warning("Invalid Session")
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "account",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import, may be Invalid Session.",
                                },
                            )
                        ]
                    }
                )
                self.refresh_salesforce_token_from_access_token(is_cron=is_cron)
            else:
                _logger.warning("Exception searching Accounts %s ", company_data.text)
                self.write(
                    {
                        "salesforce_instance_line_ids": [
                            (
                                0,
                                0,
                                {
                                    "type": "account",
                                    "date_time": datetime.now(),
                                    "state": "error",
                                    "message": "Enable to Import:- Exception searching Accounts.",
                                },
                            )
                        ]
                    }
                )

    def import_sf_acc(self, is_cron=False):
        try:
            # """ Method for importing Account """
            if self.sf_access_token:
                headers = self.get_sf_headers()

                ids_lst = []
                data = requests.request(
                    "GET",
                    self.sf_url
                    + "/services/data/v40.0/query/?q=select Id from account",
                    headers=headers,
                    timeout=180,
                )

                if data.status_code == 200:
                    if data.text:
                        parsed_data = json.loads(str(data.text))
                        ids_lst = []
                        # loop in array and grab
                        if parsed_data.get("records"):
                            for pdata in parsed_data.get("records"):
                                if pdata.get("Id"):
                                    ids_lst.append(pdata.get("Id"))
                if ids_lst:
                    for acc_id in ids_lst:
                        self.sf_createOdooParentId(str(acc_id))
        except Exception as e:
            if not is_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    def fetch_sf_lead_details(self, rec):
        """HIT SF FOR GETTING INDV LEAD DETAILS"""
        if self.sf_access_token:
            headers = self.get_sf_headers()
            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/Lead/" + str(rec),
                headers=headers,
                timeout=180,
            )
            if data.status_code == 200:
                if data.text:
                    leads_data = json.loads(str(data.text))
                    return leads_data
            else:
                return False

    def create_sf_Lead(self, lead_dict, sf_id):
        lead_obj = self.env["crm.lead"]
        headers = self.get_sf_headers()

        lead_exists = lead_obj.search([("x_salesforce_id", "=", sf_id)])
        if not lead_exists:
            if lead_dict:
                res = lead_obj.sudo().create(lead_dict)
                if res:
                    # """ Write x_salesforce_id """
                    res.sudo().write({"x_salesforce_id": sf_id})

                    return res.id
                else:
                    return False
            else:
                return False
        else:
            lead_exists.sudo().write(lead_dict)

    def import_sf_lead(self, is_from_cron=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()
                temp_odoo_date = self.lead_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

                endpoint = ""
                if self.import_limit:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Lead where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
                else:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Lead where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )

                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                lead_dict = {}
                                lead_read = self.fetch_sf_lead_details(rec)
                                # """ PREPARE DICT FOR INSERTING IN CRM.LEAD """
                                if lead_read.get("Name"):
                                    lead_dict["name"] = lead_read.get("Name")
                                    lead_dict["contact_name"] = lead_read.get("Name")
                                    lead_dict["type"] = "lead"

                                if lead_read.get("Salutation"):
                                    title_obj = self.env["res.partner.title"]
                                    title = title_obj.search(
                                        [("name", "=", lead_read.get("Salutation"))]
                                    )
                                    if title:
                                        lead_dict["title"] = title.id
                                    else:
                                        title = title_obj.sudo().create(
                                            {"name": lead_read.get("Salutation")}
                                        )
                                        lead_dict["title"] = title.id

                                if lead_read.get("Company"):
                                    lead_dict["partner_name"] = lead_read.get("Company")

                                if lead_read.get("Address"):
                                    lead_dict["street"] = lead_read.get("Address").get(
                                        "street", False
                                    )
                                    lead_dict["city"] = lead_read.get("Address").get(
                                        "city", False
                                    )
                                    lead_dict["zip"] = lead_read.get("Address").get(
                                        "postalCode", False
                                    )
                                    country = lead_read.get("Address").get(
                                        "country", False
                                    )
                                    country_id = False
                                    if country:
                                        if country in [
                                            "usa",
                                            "USA",
                                            "us",
                                            "US",
                                            "United States of America",
                                            "united states of america",
                                            "united states",
                                            "United States",
                                        ]:
                                            country_id = self.env["res.country"].search(
                                                [("code", "like", "US")], limit=1
                                            )
                                            lead_dict["country_id"] = country_id.id
                                        else:
                                            country_id = self.env["res.country"].search(
                                                [
                                                    "|",
                                                    ("name", "=", country),
                                                    ("code", "=", country),
                                                ],
                                                limit=1,
                                            )
                                            if country_id:
                                                lead_dict["country_id"] = country_id.id
                                            else:
                                                code = country[:2]
                                                code_exist = self.env[
                                                    "res.country"
                                                ].search([("code", "=", code)])
                                                if code_exist:
                                                    lead_dict["country_id"] = (
                                                        code_exist.id
                                                    )
                                                else:
                                                    country_id = (
                                                        self.env["res.country"]
                                                        .sudo()
                                                        .create(
                                                            {
                                                                "name": country,
                                                                "code": code,
                                                            }
                                                        )
                                                    )
                                                    lead_dict["country_id"] = (
                                                        country_id.id
                                                    )
                                        if country_id:
                                            state_id = self.env[
                                                "res.country.state"
                                            ].search(
                                                [
                                                    "|",
                                                    (
                                                        "name",
                                                        "=",
                                                        lead_read.get("Address").get(
                                                            "state"
                                                        ),
                                                    ),
                                                    (
                                                        "code",
                                                        "=",
                                                        lead_read.get("Address").get(
                                                            "state"
                                                        ),
                                                    ),
                                                ],
                                                limit=1,
                                            )
                                        else:
                                            state_id = self.env[
                                                "res.country.state"
                                            ].search(
                                                [
                                                    "|",
                                                    (
                                                        "name",
                                                        "=",
                                                        lead_read.get("Address").get(
                                                            "state"
                                                        ),
                                                    ),
                                                    (
                                                        "code",
                                                        "=",
                                                        lead_read.get("Address").get(
                                                            "state"
                                                        ),
                                                    ),
                                                ],
                                                limit=1,
                                            )
                                        if state_id:
                                            lead_dict["state_id"] = state_id.id
                                if lead_read.get("Phone"):
                                    lead_dict["phone"] = lead_read.get("Phone")
                                if lead_read.get("MobilePhone"):
                                    lead_dict["mobile"] = lead_read.get("MobilePhone")
                                if lead_read.get("Email"):
                                    lead_dict["email_from"] = lead_read.get("Email")
                                if lead_read.get("Website"):
                                    lead_dict["website"] = lead_read.get("Website")
                                if lead_read.get("Description"):
                                    lead_dict["description"] = lead_read.get(
                                        "Description"
                                    )

                                if lead_read.get("Status"):
                                    if (
                                        lead_read.get("Status")
                                        == "Open - Not Contacted"
                                    ):
                                        lead_dict["sf_status"] = "open"
                                    if lead_read.get("Status") == "Working - Contacted":
                                        lead_dict["sf_status"] = "working"
                                    if lead_read.get("Status") == "Closed - Converted":
                                        lead_dict["sf_status"] = "closed1"
                                    if (
                                        lead_read.get("Status")
                                        == "Closed - Not Converted"
                                    ):
                                        lead_dict["sf_status"] = "closed2"

                                if lead_dict:
                                    self.create_sf_Lead(lead_dict, lead_read.get("Id"))
                                    self.lead_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            lead_read.get("LastModifiedDate")
                                        )
                                    )

                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "lead",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "lead",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "lead",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token()
                else:
                    _logger.warning("Exception searching Leads %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "lead",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Leads.",
                                    },
                                )
                            ]
                        }
                    )
        except Exception as e:
            if not is_from_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    def fetch_sf_opportunity_details(self, rec):
        """HIT SF FOR GETTING INDV Opportunity DETAILS"""
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/Opportunity/" + str(rec),
                headers=headers,
                timeout=180,
            )

            if data.status_code == 200:
                if data.text:
                    opportunity_data = json.loads(str(data.text))
                    return opportunity_data
            else:
                return False

    def create_sf_Opportunity(self, opportunity_dict, sf_id):
        opportunity_obj = self.env["crm.lead"]
        opportunity_exists = opportunity_obj.search(
            [("x_salesforce_id_oppo", "=", sf_id)]
        )
        if not opportunity_exists:
            if opportunity_dict:
                res = opportunity_obj.sudo().create(opportunity_dict)
                if res:
                    # """ Write x_salesforce_id_oppo """
                    res.sudo().write({"x_salesforce_id_oppo": sf_id})
                    _logger.info("Opportunity created in odoo %s", res.id)
                    res._cr.commit()

                    return res.id
                else:
                    return False
            else:
                return False
        else:
            # """ Write Opportunity Data """

            opportunity_exists.sudo().write(opportunity_dict)
            _logger.info("Opportunity write in odoo %s", opportunity_exists.id)

            opportunity_exists._cr.commit()

    def import_sf_opportunity(self, is_from_cron=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()

                temp_odoo_date = self.opportunity_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

                endpoint = ""
                if self.import_limit:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Opportunity where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.export_limit}"
                else:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Opportunity where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )

                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                opportunity_dict = {}
                                opportunity_read = self.fetch_sf_opportunity_details(
                                    rec
                                )
                                # """ PREPARE DICT FOR INSERTING IN CRM.LEAD """
                                if opportunity_read.get("Name"):
                                    opportunity_dict["name"] = opportunity_read.get(
                                        "Name"
                                    )
                                    opportunity_dict["type"] = "opportunity"
                                if opportunity_read.get("Amount"):
                                    opportunity_dict["expected_revenue"] = (
                                        opportunity_read.get("Amount")
                                    )
                                if opportunity_read.get("Probability"):
                                    opportunity_dict["probability"] = (
                                        opportunity_read.get("Probability")
                                    )
                                if opportunity_read.get("AccountId"):
                                    result = self.sf_createOdooParentId(
                                        opportunity_read.get("AccountId")
                                    )
                                    if result:
                                        opportunity_dict["partner_id"] = result
                                if opportunity_read.get("Probability"):
                                    opportunity_dict["probability"] = (
                                        opportunity_read.get("Probability")
                                    )

                                if opportunity_read.get("CloseDate"):
                                    opportunity_dict["date_deadline"] = (
                                        opportunity_read.get("CloseDate")
                                    )

                                if opportunity_read.get("Description"):
                                    opportunity_dict["description"] = (
                                        opportunity_read.get("Description")
                                    )

                                if opportunity_read.get("StageName"):
                                    crm_stage = self.env["crm.stage"].search(
                                        [
                                            (
                                                "name",
                                                "=",
                                                opportunity_read.get("StageName"),
                                            )
                                        ],
                                        limit=1,
                                    )
                                    opportunity_dict["stage_id"] = crm_stage.id
                                    if (
                                        opportunity_read.get("StageName")
                                        == "Closed Won"
                                    ):
                                        crm_stage = self.env["crm.stage"].search(
                                            [("name", "=", "Won")]
                                        )
                                        opportunity_dict["stage_id"] = crm_stage.id
                                    if (
                                        opportunity_read.get("StageName")
                                        == "Value Proposition"
                                    ):
                                        crm_stage = self.env["crm.stage"].search(
                                            [("name", "=", "Proposition")]
                                        )
                                        opportunity_dict["stage_id"] = crm_stage.id
                                    if (
                                        opportunity_read.get("StageName")
                                        == "Qualification"
                                    ):
                                        crm_stage = self.env["crm.stage"].search(
                                            [("name", "=", "Qualified")]
                                        )
                                        opportunity_dict["stage_id"] = crm_stage.id

                                if opportunity_dict:
                                    self.create_sf_Opportunity(
                                        opportunity_dict, opportunity_read.get("Id")
                                    )
                                    self.opportunity_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            opportunity_read.get("LastModifiedDate")
                                        )
                                    )
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "opportunity",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "opportunity",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "opportunity",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token()
                else:
                    _logger.warning("Exception searching Opportunities %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "opportunity",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Opportunities.",
                                    },
                                )
                            ]
                        }
                    )

        except Exception as e:
            if not is_from_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    def fetch_sf_contract_details(self, rec):
        """HIT SF FOR GETTING INDV CONTRACT DETAILS"""
        if self.sf_access_token:
            headers = self.get_sf_headers()
            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/Contract/" + str(rec),
                headers=headers,
                timeout=180,
            )
            if data.status_code == 200:
                if data.text:
                    contracts_data = json.loads(str(data.text))
                    return contracts_data
            else:
                return False

    def create_sf_Contract(self, contract_dict, sf_id):
        contract_obj = self.env["sf.contract"]
        headers = self.get_sf_headers()

        contract_exists = contract_obj.search([("x_salesforce_id", "=", sf_id)])
        if not contract_exists:
            if contract_dict:
                chart_of_account = self.env["account.account"].search([])
                if not chart_of_account:
                    raise UserError(_("Please install Chart Of Account."))
                else:
                    res = contract_obj.sudo().create(contract_dict)
                    if res:
                        # """ Write x_salesforce_id """
                        res.sudo().write({"x_salesforce_id": sf_id})
                        _logger.info("Contract created in odoo %s", res.id)

                        return res.id
                    else:
                        return False
            else:
                return False
        else:
            # """ Write Contract Data """
            contract_rec_update = contract_exists.sudo().write(contract_dict)
            if contract_rec_update:
                _logger.info("Contract updated in odoo %s", contract_exists.id)
                return contract_exists.id

    def import_sf_contract(self, is_from_cron=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()
                temp_odoo_date = self.contract_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))
                endpoint = ""
                if self.import_limit:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Contract where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
                else:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Contract where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"
                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )
                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                contract_dict = {}
                                contract_read = self.fetch_sf_contract_details(rec)
                                # """ PREPARE DICT FOR INSERTING IN SF.CONTRACT """
                                if contract_read.get("AccountId"):
                                    result = self.sf_createOdooParentId(
                                        contract_read.get("AccountId")
                                    )
                                    if result:
                                        contract_dict["parent_id"] = result
                                if contract_read.get("ContractNumber"):
                                    contract_dict["name"] = contract_read.get(
                                        "ContractNumber"
                                    )
                                if contract_read.get("StartDate"):
                                    contract_dict["contract_start_date"] = (
                                        contract_read.get("StartDate")
                                    )
                                if contract_read.get("ContractTerm"):
                                    contract_dict["contacr_term_month"] = (
                                        contract_read.get("ContractTerm")
                                    )
                                if contract_read.get("Status"):
                                    if contract_read.get("Status") == "Draft":
                                        contract_dict["state"] = "draft"
                                    if contract_read.get("Status") == "Activated":
                                        contract_dict["state"] = "activated"
                                    if (
                                        contract_read.get("Status")
                                        == "In Approval Process"
                                    ):
                                        contract_dict["state"] = "approval"
                                if contract_dict:
                                    self.create_sf_Contract(
                                        contract_dict, contract_read.get("Id")
                                    )
                                    self.contract_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            contract_read.get("LastModifiedDate")
                                        )
                                    )
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "contract",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "contract",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contract",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token()
                else:
                    _logger.warning("Exception searching Contracts %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "contract",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Contracts.",
                                    },
                                )
                            ]
                        }
                    )
        except Exception as e:
            if not is_from_cron:
                raise UserError(_("Oops Some error Occurred1" + str(e)))
            else:
                _logger.error("Oops Some error Occurred2" + str(e))

    def fetch_sf_event_details(self, rec):
        """HIT SF FOR GETTING INDV EVENT DETAILS"""
        if self.sf_access_token:
            headers = self.get_sf_headers()

            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/Event/" + str(rec),
                headers=headers,
                timeout=180,
            )
            if data.status_code == 200:
                if data.text:
                    events_data = json.loads(str(data.text))
                    return events_data
            else:
                return False

    def create_sf_Event(self, event_dict, sf_id):
        event_obj = self.env["calendar.event"]
        headers = self.get_sf_headers()

        event_exists = event_obj.sudo().search([("x_salesforce_id", "=", sf_id)])
        if not event_exists:
            if event_dict:
                res = event_obj.sudo().create(event_dict)
                if res:
                    # """ Write x_salesforce_id """
                    res.sudo().write({"x_salesforce_id": sf_id})
                    _logger.info("Event created in salesforce %s", res.id)

                    return res.id
                else:
                    return False
            else:
                return False
        else:
            # """ Write Event Data """

            event_rec_update = event_exists.sudo().write(event_dict)
            if event_rec_update:
                _logger.info("Event updated in salesforce %s", event_exists.id)

    def import_sf_event(self, is_cron=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()
                temp_odoo_date = self.event_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))
                data = requests.request(
                    "GET",
                    self.sf_url
                    + f"/services/data/v40.0/query/?q=select Id from Event where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate",
                    headers=headers,
                    timeout=180,
                )
                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                event_dict = {}
                                event_read = self.fetch_sf_event_details(rec)
                                # """ PREPARE DICT FOR INSERTING IN CALENDAR.EVENT """
                                if event_read.get("Subject"):
                                    event_dict["name"] = event_read.get("Subject")
                                if event_read.get("Description"):
                                    event_dict["description"] = event_read.get(
                                        "Description"
                                    )
                                if event_read.get("Location"):
                                    event_dict["location"] = event_read.get("Location")

                                if event_read.get("StartDateTime"):
                                    result1 = datetime.strptime(
                                        event_read.get("StartDateTime")[0:19],
                                        "%Y-%m-%dT%H:%M:%S",
                                    )
                                    event_dict["start"] = result1
                                if event_read.get("EndDateTime"):
                                    result2 = datetime.strptime(
                                        event_read.get("EndDateTime")[0:19],
                                        "%Y-%m-%dT%H:%M:%S",
                                    )
                                    event_dict["stop"] = result2
                                if event_dict:
                                    self.create_sf_Event(
                                        event_dict, event_read.get("Id")
                                    )
                                    self.event_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            event_read.get("LastModifiedDate")
                                        )
                                    )
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "event",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "event",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "event",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token(is_cron=is_cron)
                else:
                    _logger.warning("Exception searching Events %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "event",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Events.",
                                    },
                                )
                            ]
                        }
                    )
        except Exception as e:
            if not is_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    def fetch_sf_activity_details(self, rec):
        """HIT SF FOR GETTING INDV ACTIVITY DETAILS"""
        if self.sf_access_token:
            headers = self.get_sf_headers()
            data = requests.request(
                "GET",
                self.sf_url + "/services/data/v40.0/sobjects/Task/" + str(rec),
                headers=headers,
                timeout=180,
            )
            if data.status_code == 200:
                if data.text:
                    activities_data = json.loads(str(data.text))
                    return activities_data
            else:
                return False

    def create_sf_Activity(self, activity_dict, sf_id):
        activity_obj = self.env["mail.activity"]
        headers = self.get_sf_headers()
        activity_exists = activity_obj.search([("x_salesforce_id", "=", sf_id)])
        if not activity_exists:
            if activity_dict:
                res = activity_obj.sudo().create(activity_dict)
                if res:
                    # """ Write x_salesforce_id """
                    res.sudo().write({"x_salesforce_id": sf_id})

                    return res.id
                else:
                    return False
            else:
                return False
        else:
            # """ Write Event Data """

            activity_exists.sudo().write(activity_dict)

    def import_sf_activity(self, is_from_cron=False):
        try:
            if self.sf_access_token:
                headers = self.get_sf_headers()

                temp_odoo_date = self.task_lastmodifieddate
                sf_modified_date = self.convert_odoodt_tosf(str(temp_odoo_date))

                endpoint = ""
                if self.import_limit:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Task where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate LIMIT {self.import_limit}"
                else:
                    endpoint = f"/services/data/v40.0/query/?q=select Id from Task where (LastModifiedDate > {sf_modified_date}) ORDER BY LastModifiedDate"

                data = requests.request(
                    "GET", self.sf_url + endpoint, headers=headers, timeout=180
                )

                if data.status_code in (200, 201):
                    if data:
                        recs = []
                        parsed_data = json.loads(str(data.text))
                        if parsed_data:
                            for p in parsed_data.get("records"):
                                recs.append(p.get("Id"))
                        if recs:
                            for rec in recs:
                                activity_dict = {}
                                activity_read = self.fetch_sf_activity_details(rec)
                                # """ PREPARE DICT FOR INSERTING IN MAIL.ACTIVITY """
                                if activity_read.get("WhoId"):
                                    result = self.sf_createOdooParentId_Activity(
                                        activity_read.get("WhoId"), search_for="contact"
                                    )
                                    if result:
                                        activity_dict["request_partner_id"] = result
                                        activity_dict["res_name"] = result
                                        activity_dict["res_id"] = result
                                    # res_partner = self.env['res.partner'].search([('x_salesforce_id', '=', activity_read.get('WhoId'))], limit=1)
                                    # activity_dict['request_partner_id'] = res_partner.id
                                    # activity_dict['res_name'] = res_partner.name
                                    # activity_dict['res_id'] = res_partner.id
                                    else:
                                        if not is_from_cron:
                                            raise UserError(
                                                _(
                                                    "WhoId Not found in the record please add it first for id "
                                                    + activity_read.get("Id")
                                                )
                                            )
                                        else:
                                            _logger.error(
                                                "WhoId Not found in the record please add it first for id "
                                                + activity_read.get("Id")
                                            )
                                else:
                                    if not is_from_cron:
                                        raise UserError(
                                            _(
                                                "WhoId Not found in the record please add it first for id "
                                                + activity_read.get("Id")
                                            )
                                        )
                                    else:
                                        _logger.error(
                                            "WhoId Not found in the record please add it first for id "
                                            + activity_read.get("Id")
                                        )

                                if activity_read.get("WhatId"):
                                    result = self.sf_createOdooParentId_Activity(
                                        activity_read.get("WhatId"),
                                        search_for="account",
                                    )
                                    if result:
                                        activity_dict["parent_id"] = result

                                    # res_partner = self.env['res.partner'].search([('x_salesforce_id', '=', activity_read.get('WhatId'))], limit=1)
                                    # activity_dict['parent_id'] = res_partner.id
                                    else:
                                        if not is_from_cron:
                                            raise UserError(
                                                _(
                                                    "WhatId Not found in the record please add it first for id1 "
                                                    + activity_read.get("Id")
                                                )
                                            )
                                        else:
                                            _logger.error(
                                                "WhatId Not found in the record please add it first for id1 "
                                                + activity_read.get("Id")
                                            )
                                else:
                                    if not is_from_cron:
                                        raise UserError(
                                            _(
                                                "WhatId Not found in the record please add it first for id2 "
                                                + activity_read.get("Id")
                                            )
                                        )
                                    else:
                                        _logger.error(
                                            "WhatId Not found in the record please add it first for id2 "
                                            + activity_read.get("Id")
                                        )

                                if activity_read.get("WhoId") and activity_read.get(
                                    "WhatId"
                                ):
                                    result = self.sf_createOdooParentId_Activity(
                                        activity_read.get("WhatId"),
                                        search_for="account",
                                    )
                                    if result:
                                        res_partner = self.env["res.partner"].search(
                                            [("id", "=", result)], limit=1
                                        )
                                        activity_dict["res_name"] = res_partner.name
                                        activity_dict["res_id"] = res_partner.id
                                    # res_partner = self.env['res.partner'].search(
                                    #     [('x_salesforce_id', '=', activity_read.get('WhatId'))], limit=1)
                                    # activity_dict['res_name'] = res_partner.name
                                    # activity_dict['res_id'] = res_partner.id
                                    else:
                                        if not is_from_cron:
                                            raise UserError(
                                                _(
                                                    "WhatId Not found in the record please add it first for id3 "
                                                    + activity_read.get("Id")
                                                )
                                            )
                                        else:
                                            _logger.error(
                                                "WhatId Not found in the record please add it first for id3 "
                                                + activity_read.get("Id")
                                            )
                                else:
                                    if not is_from_cron:
                                        raise UserError(
                                            _(
                                                "WhatId Not found in the record please add it first for id4 "
                                                + activity_read.get("Id")
                                            )
                                        )
                                    else:
                                        _logger.error(
                                            "WhatId Not found in the record please add it first for id4 "
                                            + activity_read.get("Id")
                                        )

                                if not activity_read.get(
                                    "WhoId"
                                ) and not activity_read.get("WhatID"):
                                    result = self.sf_createOdooParentId_Activity(
                                        activity_read.get("OwnerId"),
                                        search_for="account",
                                    )
                                    if result:
                                        res_partner = self.env["res.partner"].search(
                                            [("id", "=", result)], limit=1
                                        )
                                        activity_dict["res_name"] = res_partner.name
                                        activity_dict["res_id"] = res_partner.id
                                    # res_partner = self.env['res.partner'].search(
                                    #     [('x_salesforce_id', '=', activity_read.get('OwnerId'))], limit=1)
                                    # activity_dict['res_name'] = res_partner.name
                                    # activity_dict['res_id'] = res_partner.id
                                if activity_read.get("Status"):
                                    if activity_read.get("Status") == "Not Started":
                                        activity_dict["sf_status"] = "not_started"
                                    if activity_read.get("Status") == "In Progress":
                                        activity_dict["sf_status"] = "in_progress"
                                    if activity_read.get("Status") == "Completed":
                                        activity_dict["sf_status"] = "completed"
                                    if (
                                        activity_read.get("Status")
                                        == "Waiting for someone else"
                                    ):
                                        activity_dict["sf_status"] = "waiting"
                                    if activity_read.get("Status") == "Deferred":
                                        activity_dict["sf_status"] = "deferred"
                                    if activity_read.get("Status") == "Open":
                                        activity_dict["sf_status"] = "open"
                                if activity_read.get("Priority"):
                                    if activity_read.get("Priority") == "High":
                                        activity_dict["priority"] = "high"
                                    if activity_read.get("Priority") == "Normal":
                                        activity_dict["priority"] = "normal"
                                    if activity_read.get("Priority") == "Low":
                                        activity_dict["priority"] = "low"
                                if activity_read.get("Subject"):
                                    activity_dict["summary"] = activity_read.get(
                                        "Subject"
                                    )

                                activity_dict["user_id"] = self.env.uid
                                if activity_read.get("ActivityDate"):
                                    activity_dict["date_deadline"] = activity_read.get(
                                        "ActivityDate"
                                    )
                                model_id = self.env["ir.model"].search(
                                    [("model", "=", "res.partner")]
                                )
                                activity_dict["res_model_id"] = model_id.id
                                if activity_dict:
                                    self.create_sf_Activity(
                                        activity_dict, activity_read.get("Id")
                                    )
                                    self.task_lastmodifieddate = (
                                        self.convert_sfdate_toodoo(
                                            activity_read.get("LastModifiedDate")
                                        )
                                    )

                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "task",
                                                "date_time": datetime.now(),
                                                "state": "success",
                                                "message": "Imported Successfully",
                                            },
                                        )
                                    ]
                                }
                            )
                        else:
                            self.write(
                                {
                                    "salesforce_instance_line_ids": [
                                        (
                                            0,
                                            0,
                                            {
                                                "type": "task",
                                                "date_time": datetime.now(),
                                                "state": "nothing",
                                                "message": "Nothing to Import.",
                                            },
                                        )
                                    ]
                                }
                            )
                elif data.status_code == 401:
                    _logger.warning("Invalid Session")
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "task",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import, may be Invalid Session.",
                                    },
                                )
                            ]
                        }
                    )
                    self.refresh_salesforce_token_from_access_token()
                else:
                    _logger.warning("Exception searching Tasks %s ", data.text)
                    self.write(
                        {
                            "salesforce_instance_line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "type": "task",
                                        "date_time": datetime.now(),
                                        "state": "error",
                                        "message": "Enable to Import:- Exception searching Tasks.",
                                    },
                                )
                            ]
                        }
                    )
        except Exception as e:
            if not is_from_cron:
                raise UserError(_("Oops Some error Occurred" + str(e)))
            else:
                _logger.error("Oops Some error Occurred" + str(e))

    @api.model
    def _scheduler_import_sf_accounts(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_accounts(is_cron=True)

    @api.model
    def _scheduler_import_sf_contacts(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_contacts()

    @api.model
    def _scheduler_import_sf_products(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_products(is_from_cron=True)

    @api.model
    def _scheduler_import_sf_quotes(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_quote(is_from_cron=True)

    @api.model
    def _scheduler_import_sf_orders(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_so(is_from_cron=True)

    @api.model
    def _scheduler_import_sf_leads(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_lead(is_from_cron=True)

    @api.model
    def _scheduler_import_sf_opportunity(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_opportunity()

    @api.model
    def _scheduler_import_sf_contract(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_contract()

    @api.model
    def _scheduler_import_sf_event(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_event(is_cron=True)

    @api.model
    def _scheduler_import_sf_activity(self):
        sf_config = (
            self.env["salesforce.instance"]
            .sudo()
            .search([("is_default_instance", "=", True)], limit=1)
        )
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        sf_config.import_sf_activity(is_from_cron=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self.env.context.get("type") == "account":
            res["type"] = "account"

        return res


class SalesForceInstanceLine(models.Model):
    _name = "salesforce.instance.line"
    _order = "date_time desc"

    salesforce_instance_id = fields.Many2one("salesforce.instance", string="Salesforce")
    type = fields.Selection(
        [
            ("account", "Accounts"),
            ("contact", "Contacts"),
            ("product", "Products"),
            ("product_template", "Product Templates"),
            ("sale_quotation", "Sale Quotations"),
            ("sale_order", "Sale Orders"),
            ("lead", "Leads"),
            ("opportunity", "Opportunities"),
            ("contract", "Contracts"),
            ("event", "Events"),
            ("task", "Tasks"),
        ],
    )
    date_time = fields.Datetime(string="Date & Time")
    state = fields.Selection(
        [("success", "Success"), ("error", "Error"), ("nothing", "Nothing")],
    )
    message = fields.Text()
