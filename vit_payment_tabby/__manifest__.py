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
    "version": "16.0.1.0.0",
    "depends": ["payment", "website_sale_delivery", "product_detail_screen"],
    "data": [
        "views/payment_acquirer.xml",
        "views/payment_tabby_templates.xml",
        "data/tabby_payment_data.xml",
        "views/template.xml",
        "views/res_config_settings_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "/vit_payment_tabby/static/src/js/lib/tabby-card.js",
            "/vit_payment_tabby/static/src/js/lib/tabby-promo.js",
            "/vit_payment_tabby/static/src/js/lib/custom.js",
        ],
    },
    'images': ['static/description/banner.png'],
    "application": True,
    "installable": True,
    'auto_install': False,
    "sequence": -100,
}
