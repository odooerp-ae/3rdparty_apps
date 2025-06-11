import logging
from datetime import datetime

import requests

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MaqsamAgent(models.Model):
    _name = "api.agent"
    _inherit = ["maqsam.base.api"]
    _description = "Maqsam Agent"

    identifier = fields.Char(required=True, index=True, copy=False)
    name = fields.Char()
    email = fields.Char()
    active = fields.Boolean()
    groups = fields.Char()
    outgoing_enabled = fields.Boolean()
    incoming_enabled = fields.Boolean()
    whatsapp_enabled = fields.Boolean(string="WhatsApp Enabled")
    state = fields.Char()
    state_start_time = fields.Datetime()
    created_at = fields.Datetime()

    DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

    # _sql_constraints = [
    #     ('identifier_uniq', 'unique(identifier)', 'The Maqsam Agent Identifier must be unique!'),
    # ]

    @api.model
    def fetch_agents(self, *args, **kwargs):
        _logger.info("Fetching Maqsam agents...")

        # Get API credentials and URL from settings
        access_key, access_secret = self._get_maqsam_api_credentials()
        agents_api_url = f"{self._get_maqsam_api_url(version='v1')}/agents"

        try:
            response = requests.get(
                agents_api_url, auth=(access_key, access_secret), timeout=15
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.exception("Error while fetching agents from Maqsam API.")
            raise UserError(
                _("Failed to connect to Maqsam API for agents: %s") % str(e)
            )
        except Exception as e:
            _logger.exception(
                "An unexpected error occurred during agent fetch request."
            )
            raise UserError(
                _(f"An unexpected error occurred while fetching agents: {e}")
            )

        if response.status_code == 200:
            agents_data = response.json().get("message", [])

            if not agents_data:
                _logger.info("No agent data received from Maqsam API.")
                return

            existing_agents_map = {
                agent["identifier"]: agent["id"]
                for agent in self.search_read(
                    [
                        (
                            "identifier",
                            "in",
                            [
                                a.get("identifier")
                                for a in agents_data
                                if a.get("identifier")
                            ],
                        )
                    ],
                    ["identifier"],
                )
            }

            agents_to_create = []
            agents_to_update = []

            for agent_api_data in agents_data:
                identifier = agent_api_data.get("identifier")
                if not identifier:
                    _logger.warning(
                        "Maqsam agent data missing 'identifier'. Skipping record: %s",
                        agent_api_data,
                    )
                    continue

                state_info = agent_api_data.get("state", {})
                state_value = (
                    state_info.get("state")
                    if isinstance(state_info, dict)
                    else state_info
                )
                state_timestamp = (
                    state_info.get("timestamp")
                    if isinstance(state_info, dict)
                    else None
                )

                parsed_created_at = None
                if agent_api_data.get("createdAt"):
                    try:
                        parsed_created_at = datetime.strptime(
                            agent_api_data["createdAt"], self.DATE_FORMAT
                        )
                    except ValueError:
                        _logger.warning(
                            "Could not parse 'createdAt' ('%s') for agent %s. Skipping this field.",
                            agent_api_data.get("createdAt"),
                            identifier,
                        )

                parsed_state_start_time = None
                if state_timestamp:
                    try:
                        parsed_state_start_time = datetime.strptime(
                            state_timestamp, self.DATE_FORMAT
                        )
                    except ValueError:
                        _logger.warning(
                            "Could not parse 'state_start_time' ('%s') for agent %s. Skipping this field.",
                            state_timestamp,
                            identifier,
                        )

                agent_vals = {
                    "identifier": identifier,
                    "name": agent_api_data.get("name"),
                    "email": agent_api_data.get("email"),
                    "active": agent_api_data.get("active", False),
                    "groups": agent_api_data.get("groups", ""),
                    "outgoing_enabled": agent_api_data.get("outgoingEnabled", False),
                    "incoming_enabled": agent_api_data.get("incomingEnabled", False),
                    "whatsapp_enabled": agent_api_data.get("whatsappEnabled", False),
                    "state": state_value,
                    "state_start_time": parsed_state_start_time,
                    "created_at": parsed_created_at,
                }

                if identifier in existing_agents_map:
                    agent_vals["id"] = existing_agents_map[identifier]
                    agents_to_update.append(agent_vals)
                else:
                    agents_to_create.append(agent_vals)

            if agents_to_create:
                self.create(agents_to_create)
                _logger.info("Created %d new Maqsam agents.", len(agents_to_create))

            updated_count = 0
            for update_vals in agents_to_update:
                record_id = update_vals.pop("id")
                agent_rec = self.browse(record_id)
                if agent_rec:
                    agent_rec.write(update_vals)
                    updated_count += 1
            if updated_count > 0:
                _logger.info("Updated %d existing Maqsam agents.", updated_count)

        elif response.status_code == 401:
            raise UserError(
                _(
                    "Unauthorized access. Please check your Maqsam API credentials in Settings."
                )
            )
        else:
            error_message = response.json().get("message", response.text)
            _logger.error(
                "Failed to fetch agents. Status code: %s, Response: %s",
                response.status_code,
                response.text,
            )
            raise UserError(
                _("Failed to fetch agents from Maqsam. Error: %s") % error_message
            )
