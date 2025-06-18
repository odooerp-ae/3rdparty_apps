import json
import logging

import requests

from odoo import http

_logger = logging.getLogger(__name__)


class Custom_SalesForce_controller(http.Controller):
    # @api.model
    # def stringToBase64(s):
    #     return base64.b64encode(bytes(s)).decode('utf-8')

    @http.route("/get_auth_code_from_sf", type="http", auth="public", website=True)
    def get_auth_code_from_sf(self, **kwarg):
        if kwarg.get("code"):
            # """Get access Token and store in object"""
            # salesforce_id = http.request.env['res.users'].sudo().search([('id', '=', http.request.uid)], limit=1).company_id
            salesforce_id = (
                http.request.env["salesforce.instance"]
                .sudo()
                .search([("is_default_instance", "=", True)], limit=1)
            )
            if salesforce_id:
                salesforce_id.write({"sf_auth_code": kwarg.get("code")})

                client_id = salesforce_id.sf_client_id
                client_secret = salesforce_id.sf_client_secret
                if salesforce_id.sf_request_token_url:
                    redirect_uri = salesforce_id.sf_request_token_url
                else:
                    redirect_uri = None

                headers = {}
                headers["accept"] = "application/json"
                payload = {
                    "code": str(kwarg.get("code")),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                }
                access_token = requests.post(
                    salesforce_id.sf_access_token_url,
                    data=payload,
                    headers=headers,
                    timeout=180,
                )
                if access_token:
                    parsed_token_response = json.loads(access_token.text)
                    _logger.info(
                        f"PARSED TOKEN RESPONSE FROM CONTROLLER IS {parsed_token_response}"
                    )
                    if parsed_token_response:
                        data_dict = {}
                        data_dict["sf_access_token"] = parsed_token_response.get(
                            "access_token"
                        )
                        data_dict["sf_refresh_token"] = parsed_token_response.get(
                            "refresh_token"
                        )
                        data_dict["sf_url"] = parsed_token_response.get("instance_url")
                        salesforce_id.write(data_dict)
        return "You can Close this window now"
