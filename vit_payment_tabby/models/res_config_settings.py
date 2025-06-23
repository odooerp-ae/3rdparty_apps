# -*- coding: utf-8 -*-

from odoo import models, fields, _


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    tabby_product_widget = fields.Boolean(
        string="Product Widget ",
        related="website_id.tabby_product_widget",
        readonly=False,
        default=True,
    )
    show_tabby_card = fields.Boolean(
        string="Show Tabby Card",
        related="website_id.show_tabby_card",
        readonly=False,
        default=True,
    )

    # tabby_data_number_of_installments = fields.Selection(
    #     [("2", 2), ("3", 3), ("4", 4), ("5", 5), ("6", 6), ("12", 12)],
    #     string="No of Installments",
    #     related="website_id.tabby_data_number_of_installments",
    #     readonly=False,
    # )

    tabby_data_installment_minimum_amount = fields.Float(
        string="Installment Minimum Amount",
        related='website_id.tabby_data_installment_minimum_amount',
        readonly=False,
    )

    tabby_data_installment_maximum_amount = fields.Float(
        string="Installment Maximum Amount",
        related='website_id.tabby_data_installment_maximum_amount',
        readonly=False,
    )

    tabby_data_installment_available_amount = fields.Float(
        string="Installment Available Amount",
        related='website_id.tabby_data_installment_available_amount',
        readonly=False,
    )
