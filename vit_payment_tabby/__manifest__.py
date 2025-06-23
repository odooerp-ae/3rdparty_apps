# -*- coding: utf-8 -*-

{
    "name": "Tabby Payment Gateway",
    "summary": "Tabby Payment Gateway",
    "description": "Pay Securely with Tabby convenience in Odoo!",
    'author': 'VarietyIT',
    'maintainer': 'VarietyIT',
    'company': 'VarietyIT',
    'website': 'https://varietyit.com',
    'price': 199,
    'currency': 'USD',
    'license': 'LGPL-3',
    "category": "Accounting",
    "version": "0.2",
    "depends": ["base", "payment", "website_sale"],
    "data": [
        "views/payment_tabby_templates.xml",
        "views/inherit_payment_checkout_widget.xml",
        "data/tabby_payment_data.xml",
        "views/payment_provider.xml",
        "views/template.xml",
        "views/res_config_settings_views.xml",
    ],
    'assets': {
        'web.assets_frontend': [
            'vit_payment_tabby/static/src/js/website_sale.js',
        ]
    },
    'images': ['static/description/banner.png'],
    "application": True,
    "installable": True,
    'auto_install': False,
    "sequence": -100,
}
