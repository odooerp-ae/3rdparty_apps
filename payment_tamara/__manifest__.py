# -*- coding: utf-8 -*-
##########################################################################
# Author      : Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# Copyright(c): 2015-Present Webkul Software Pvt. Ltd.
# All Rights Reserved.
#
#
#
# This program is copyright property of the author mentioned above.
# You can`t redistribute it and/or modify it.
#
#
# You should have received a copy of the License along with this program.
# If not, see <https://store.webkul.com/license.html/>
##########################################################################

{
    "name": "Tamara Payment Connect",
    "summary": "Tamara Payment Connect",
    "category": "Accounting",
    "version": "16.0",
    "sequence": 1,
    "author": "Oakland Odooerp",
    "license": "Other proprietary",
    "website": "https://odooerp.ae/",
    "description": """Tamara Payment Connect""",
    "depends": ["payment", "product_detail_screen"],
    "data": [
        "views/payment_acquirer.xml",
        "views/payment_tamara_templates.xml",
        "data/tamara_payment_data.xml",
        "views/res_config_settings_views.xml",
        "views/template.xml",
    ],
    "assets": {
        "web.assets_frontend": ["/payment_tamara/static/src/js/product_widget.js"],
    },
    "images": ["static/description/Banner.gif"],
    "application": True,
    "installable": True,
    "pre_init_hook": "pre_init_check",
    "external_dependencies": {"python": ["jwt"]},
    # "post_init_hook":  "create_missing_journal_for_acquirers",
}
