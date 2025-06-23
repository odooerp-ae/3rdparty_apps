# -*- coding: utf-8 -*-
##############################################################################
# Copyright (c) 2016-Present Webkul Software Pvt. Ltd. (<https://webkul.com/>)
# See LICENSE file for full copyright and licensing details.
# License URL : <https://store.webkul.com/license.html/>
##############################################################################

from . import controllers
from . import models
# from odoo.addons.payment.models.payment_acquirer import create_missing_journal_for_acquirers


def pre_init_check(cr):
    from odoo.service import common
    from odoo.exceptions import Warning

    version_info = common.exp_version()
    server_series = version_info.get("server_serie")
    if server_series != "16.0":
        raise Warning("Module support Odoo series 16.0 found {}".format(server_series))
    return True
