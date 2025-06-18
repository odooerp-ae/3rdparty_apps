import json
import logging
import requests
from datetime import datetime
from odoo import fields, api, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class CRMOpportunity(models.Model):
    _inherit = 'crm.lead'

    x_salesforce_exported_oppo = fields.Boolean('Exported To Salesforce from opportunity', default=False, copy=False)
    x_salesforce_id_oppo = fields.Char('Salesforce Id from Opportunity', copy=False)
    x_is_updated_oppo = fields.Boolean('x_is_updated_from_opportunity', default=False, copy=False)
    sf_status_oppo = fields.Selection([('open', 'Open - Not Contacted'), ('working', 'Working - Contacted'),
                                       ('closed1', 'Closed - Converted'), ('closed2', 'Closed - Not Converted')])

    def sendOpportunityDataToSf(self, opportunity_dict, is_cron=False):
        if is_cron:
            sf_config = self.env['salesforce.instance'].sudo().search([('is_default_instance', '=', True)], limit=1)
        else:
            sf_config = self.env['salesforce.instance'].sudo().search([('company_id', '=', self.env.company.id)], limit=1)

        if not sf_config and not is_cron:
            raise ValidationError("There is no Salesforce instance")

        ''' GET ACCESS TOKEN '''
        endpoint = None
        sf_access_token = None
        realmId = None
        is_create = False
        res = None
        if sf_config.sf_access_token:
            sf_access_token = sf_config.sf_access_token

        if sf_access_token:
            headers = sf_config.get_sf_headers(type=True)

            endpoint = '/services/data/v40.0/sobjects/Opportunity'
            payload = json.dumps(opportunity_dict)
            if self.x_salesforce_id_oppo:
                ''' Try Updating it if already exported '''
                res = requests.request('PATCH', sf_config.sf_url + endpoint + '/' + self.x_salesforce_id_oppo, headers=headers, data=payload)
                if res.status_code in (200, 201, 204):
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'opportunity',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully:- Updated data'
                        })]
                    })
                    self.x_is_updated_oppo = True
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'opportunity',
                            'date_time': datetime.now(),
                            'state': 'error',
                            'message': 'Enable to Export the Updated data:- Something went Wrong.'
                        })]
                    })
            else:
                res = requests.request('POST', sf_config.sf_url + endpoint, headers=headers, data=payload)
                if res.status_code in (200, 201):
                    parsed_resp = json.loads(str(res.text))
                    self.x_salesforce_exported_oppo = True
                    self.x_salesforce_id_oppo = parsed_resp.get('id')
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'opportunity',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully'
                        })]
                    })
                    return parsed_resp.get('id')
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'opportunity',
                            'date_time': datetime.now(),
                            'state': 'error',
                            'message': 'Enable to Export Something went Wrong.'
                        })]
                    })
                    return False

    def exportOpportunity_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))

        if not self.date_deadline and not is_from_cron:
            raise UserError(_("Please add Expected Closing date"))


        ''' PREPARE DICT FOR SENDING TO SALESFORCE '''
        opportunity_dict = {}
        if self.name:
            opportunity_dict['Name'] = self.name
        if self.date_deadline:
            opportunity_dict['CloseDate'] = str(self.date_deadline)
        if self.stage_id:
            opportunity_dict['StageName'] = self.stage_id.name
        if self.partner_id and self.partner_id.x_salesforce_id:
            opportunity_dict['AccountId'] = str(self.partner_id.x_salesforce_id)
        elif self.partner_id and not self.partner_id.x_salesforce_id:
            partner_export = self.partner_id.exportPartner_to_sf()
            opportunity_dict['AccountId'] = str(self.partner_id.x_salesforce_id)
        if self.probability:
            opportunity_dict['Probability'] = self.probability
        if self.expected_revenue:
            opportunity_dict['Amount'] = self.expected_revenue
        if self.description:
            opportunity_dict['Description'] = self.description
        result = self.sendOpportunityDataToSf(opportunity_dict, is_cron=is_from_cron)
        if result:
            self.x_salesforce_exported_oppo = True

    @api.model
    def _scheduler_export_opportunity_to_sf(self):
        sf_config = self.env['salesforce.instance'].sudo().search([('is_default_instance', '=', True)], limit=1)
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            opportunities = self.search([('type', '=', 'opportunity')], limit=sf_config.export_limit)
        else:
            opportunities = self.search([('type', '=', 'opportunity')])
        for opportunity in opportunities:
            try:
                opportunity.exportOpportunity_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error('Oops Some error in  exporting Opportunity to SALESFORCE %s', e)
