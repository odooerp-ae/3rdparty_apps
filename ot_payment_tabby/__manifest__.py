# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

{
    'name': 'Tabby Payment Acquirer',
    'summary': 'Payment Acquirer: Tabby Implementation',
    'description': """Tabby Payment Acquirer""",
    'website':"https://octagotech.com",
    'author': 'Octagotech',
    'support': 'devansh.daftary@octagotech.com',
    'category': 'eCommerce',
    'version': '17.0.0.1.0',
    'depends': ['payment','website_sale','web'],

    'data': [
        'views/payment_provider_views.xml',
        'views/payment_tabby_templates.xml',
        'views/website_tabby_snippet.xml',
        'data/payment_provider_data.xml',
    ],
    
    'assets':{
        'web.assets_frontend':[
            'https://checkout.tabby.ai/tabby-promo.js',
            'ot_payment_tabby/static/src/js/website_sale.js'
        ]
    },
    'images': ['static/description/banner.png','static/description/icon.png'],
    'post_init_hook': 'post_init_hook',
    'uninstall_hook': 'uninstall_hook',
    'price': 175,
    'currency': 'USD',
    'application': True,
    'license': "OPL-1",
}
