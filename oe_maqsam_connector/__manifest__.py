{
    "name": "Odoo-Maqsam Integration",
    "summary": "Integrates Odoo with Maqsam communication platform",
    "description": """
        This module provides integration functionalities between Odoo and Maqsam.
        Key Features:
        - Click-to-Call from Odoo contacts
        - Automatic logging of inbound and outbound calls.
        - Incoming call pop-ups with Odoo contact details.
    """,
    "author": "OdooERP.ae",
    "website": "https://odooerp.ae",
    "category": "Helpdesk",
    "version": "17.0.1.0.0",
    "depends": ["mail", "web"],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings.xml",
        "views/agent_api.xml",
        "views/views.xml",
        # 'static/src/js/call_erp.js',
    ],
    "assets": {
        "web.assets_backend": [
            "oe_maqsam_connector/static/src/js/systray_icon.js",
            "oe_maqsam_connector/static/src/xml/systray_icon.xml",
        ]
    },
    "installable": True,
    "application": True,
    "license": "AGPL-3",
}
