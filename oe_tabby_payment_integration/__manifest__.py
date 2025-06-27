# -*- coding: utf-8 -*-
{
    "name": "Tabby Payment Gateway",
    "summary": "Tabby Payment Gateway",
    "description": "Pay Securely with Tabby convenience in Odoo!",
    'author': 'Odooerp',  
    'company': 'Odooerp',
    'website': 'https://odooerp.ae/',    
    'license': 'LGPL-3',
    "category": "Accounting",
    "version": "18.0",
    "depends": ["payment", "website_sale"],
    "data": [
        "views/payment_acquirer.xml",
        "views/payment_tabby_templates.xml",
        "data/tabby_payment_data.xml",
        "views/template.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "/oe_tabby_payment_integration/static/src/js/lib/tabby-card.js",
            "/oe_tabby_payment_integration/static/src/js/lib/tabby-promo.js",
            "/oe_tabby_payment_integration/static/src/js/lib/custom.js",
        ],
    },
    'images': ['static/description/banner.png'],
    "application": True,
    "installable": True,
    'auto_install': False,
    "sequence": -100,
}
