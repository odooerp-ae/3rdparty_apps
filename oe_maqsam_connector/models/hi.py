from odoo import models, fields, api
import logging
import requests
from requests.auth import HTTPBasicAuth

_logger = logging.getLogger(__name__)


class MaqsamDialerCall(models.Model):
    _name = 'call.dialer'
    _inherit = ['mail.thread']

    phone = fields.Char(string='Phone Number', required=True)
    caller = fields.Char(string='Name')

    def create_call_dialer(self):
        base_url = "https://portal.maqsam.com/phone/dialer#autodial="

        for call in self:
            if not call.phone:
                call.message_post(body='Phone number is required to initiate a call.')
                continue

            # Generate the autodial URL
            autodial_url = f"{base_url}{call.phone}"
            _logger.debug("Generated autodial URL: %s", autodial_url)

            # Create the action to open the URL in a new window or popup
            action = {
                'type': 'ir.actions.act_url',
                'url': autodial_url,
                'target': 'new',  # This opens the URL in a new tab/window
            }

            # Post a message to the chatter
            call.message_post(body=f'Initiated call to {call.phone}.')

            return action


class MaqsamCall(models.Model):
    _name = 'call.erp'
    _inherit = ['mail.thread']
    _description = 'Maqsam Call'

    agent_email = fields.Char(string='Agent Email', required=True)
    phone = fields.Char(string='Phone Number', required=True)
    caller = fields.Char(string='Caller Number')

    def create_call(self):
        url = "https://api.maqsam.com/v2/calls"
        access_key = "Jbe5DARcFNsF7DzetkML"  # Replace with your ACCESS KEY
        access_secret = "GYFB5KKipDXX0N5Cbt77"  # Replace with your ACCESS SECRET

        for call in self:
            if not call.phone:
                call.message_post(body='Phone number is required to initiate a call.')
                continue

            # Prepare data for the request
            data = {
                'email': call.agent_email,
                'phone': call.phone,
            }

            _logger.debug("Creating call with data: %s", data)  # Log the data being sent

            try:
                # POST request
                response = requests.post(url, data=data, auth=HTTPBasicAuth(access_key, access_secret))
                response.raise_for_status()

                _logger.debug("Response Status Code: %s", response.status_code)
                _logger.debug("Response Content: %s", response.content)

                if response.status_code == 200:
                    response_data = response.json()
                    if response_data.get('message') == 'success':
                        call.message_post(body='Call created successfully.')
                    else:
                        error_message = response_data.get('message', 'Unknown error')
                        call.message_post(body=f'Failed to create call: {error_message}')
                else:
                    # Log detailed error information
                    error_data = response.json()
                    error_message = error_data.get('message', 'Unknown error')
                    call.message_post(body=f'Failed to create call: {error_message}')
                    _logger.error("Failed to create call: %s", error_message)

            except requests.exceptions.RequestException as e:
                _logger.error("Error making API request: %s", e)
                if response is not None:
                    _logger.debug("Response Status Code: %s", response.status_code)
                    _logger.debug("Response Content: %s", response.content)
                call.message_post(body=f'Failed to create call: API request failed. Error: {e}')
