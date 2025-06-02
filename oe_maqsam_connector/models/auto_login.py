import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class MaqsamAutoLogin(models.Model):
    _name = 'auto.login'
    _inherit = ['maqsam.base.api']
    _description = 'Maqsam Auto Login'
    _rec_name = 'user_email'

    user_email = fields.Char(string='User Email', required=True)
    auth_token = fields.Char(string='Auth Token', readonly=True)

    def get_auth_token(self):
        self.ensure_one()

        # Get API credentials and URL from settings
        access_key, access_secret = self._get_maqsam_api_credentials()
        token_url = f"{self._get_maqsam_api_url(version='v2')}/token"

        headers = {'Content-Type': 'application/x-www-form-urlencoded'}
        payload = {'UserEmail': self.user_email}

        try:
            response = requests.post(
                token_url,
                headers=headers,
                auth=(access_key, access_secret),
                data=payload,
                timeout=10
            )
            response.raise_for_status()

            result = response.json().get('result', {})
            token = result.get('token')
            if not token:
                _logger.error("Maqsam API returned no token for user %s. Response: %s", self.user_email, response.text)
                raise UserError(_("Failed to retrieve authentication token: Token not found in Maqsam API response."))
            
            self.auth_token = token
            _logger.info("Auth token successfully retrieved for %s", self.user_email)

        except requests.exceptions.RequestException as e:
            _logger.exception("Failed to retrieve Maqsam auth token for user %s", self.user_email)
            error_msg = response.json().get('message', str(e)) if response and hasattr(response, 'json') else str(e)
            raise UserError(_(f"Failed to get auth token from Maqsam: {error_msg}"))
        except Exception as e:
            _logger.exception("An unexpected error occurred in get_auth_token")
            raise UserError(_(f"An unexpected error occurred: {e}"))

    def auto_login(self):
        self.ensure_one()
        portal_base_url = self._get_maqsam_portal_url()
        
        if not self.auth_token:
            try:
                self.get_auth_token()
            except UserError as e:
                raise
            except Exception as e:
                _logger.exception("Failed to get auth token before auto-login.")
                raise UserError(_(f"Failed to get authentication token for auto-login: {e}"))


        if not self.auth_token:
            raise UserError(_("No authentication token available to perform auto-login."))

        login_url = f"{portal_base_url}/autologin?auth_token={self.auth_token}"
        _logger.info("Generated login URL for %s: %s", self.user_email, login_url)

        return {
            'type': 'ir.actions.act_url',
            'url': login_url,
            'target': 'new',
        }