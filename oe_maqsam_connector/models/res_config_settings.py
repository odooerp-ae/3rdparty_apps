from odoo import fields, models, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    maqsam_access_key = fields.Char(
        string="Maqsam Access Key",
        config_parameter='maqsam.api.access_key',
        help="The Access Key provided by Maqsam for API authentication."
    )
    maqsam_access_secret = fields.Char(
        string="Maqsam Access Secret",
        config_parameter='maqsam.api.access_secret',
        help="The Access Secret provided by Maqsam. Keep this confidential."
    )

    maqsam_base_api_url_v1 = fields.Char(
        string="Maqsam API Base URL (v1)",
        config_parameter='maqsam.api.base_url.v1',
        default='https://api.maqsam.com/v1',
        help="Base URL for Maqsam API v1 endpoints (e.g., /agents)."
    )
    maqsam_base_api_url_v2 = fields.Char(
        string="Maqsam API Base URL (v2)",
        config_parameter='maqsam.api.base_url.v2',
        default='https://api.maqsam.com/v2',
        help="Base URL for Maqsam API v2 endpoints (e.g., /calls, /token)."
    )
    maqsam_portal_base_url = fields.Char(
        string="Maqsam Portal Base URL",
        config_parameter='maqsam.portal.base_url',
        default='https://portal.maqsam.com',
        help="Base URL for Maqsam Portal (e.g., for dialer and autologin)."
    )