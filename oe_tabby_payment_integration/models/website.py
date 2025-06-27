# -*- coding: utf-8 -*-

from odoo import api, models, fields
import logging

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = "website"

    tabby_product_widget = fields.Boolean(
        string="Product Widget ",
    )

    tabby_data_number_of_installments = fields.Selection(
        [("2", "2"), ("3", "3"), ("4", "4"), ("5", "5"), ("6", "6"), ("12", "12")],
        string="No of Installments",
    )

    tabby_data_installment_minimum_amount = fields.Float(
        string="Installment Minimum Amount",
    )
    tabby_data_installment_maximum_amount = fields.Float(
        string="Installment Maximum Amount",
    )
    tabby_data_installment_available_amount = fields.Float(
        string="Installment Available Amount",
    )
