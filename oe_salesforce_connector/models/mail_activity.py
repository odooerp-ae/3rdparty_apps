import json
import logging
import requests
from datetime import datetime
from odoo import fields, api, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    x_salesforce_exported = fields.Boolean('Exported To Salesforce', default=False, copy=False)
    x_salesforce_id = fields.Char('Salesforce Id', copy=False)
    x_is_updated = fields.Boolean('x_is_updated', default=False, copy=False)
    sf_status = fields.Selection([('not_started', 'Not Started'), ('open', 'Open'), ('in_progress', 'In Progress'),
                                  ('completed', 'Completed'), ('waiting', 'Waiting for someone else'), ('deferred', 'Deferred')])
    priority = fields.Selection([('high', 'High'), ('normal', 'Normal'), ('low', 'Low')])
    parent_id = fields.Many2one('res.partner', 'Company', domain="[('is_company', '=', True)]")

    def sendDataToSf(self, activity_dict, is_cron=False):
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

            endpoint = '/services/data/v40.0/sobjects/Task'

            payload = json.dumps(activity_dict)
            if self.x_salesforce_id:
                ''' Try Updating it if already exported '''
                res = requests.request('PATCH', sf_config.sf_url + endpoint + '/' + self.x_salesforce_id, headers=headers, data=payload)
                if res.status_code in (200, 201, 204):
                    self.x_is_updated = True
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'task',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully:- Updated data'
                        })]
                    })
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'task',
                            'date_time': datetime.now(),
                            'state': 'error',
                            'message': 'Enable to Export the Updated data:- Something went Wrong.'
                        })]
                    })
                    return False

            else:
                res = requests.request('POST', sf_config.sf_url + endpoint, headers=headers, data=payload)
                if res.status_code in (200, 201):
                    parsed_resp = json.loads(str(res.text))
                    self.x_salesforce_exported = True
                    self.x_salesforce_id = parsed_resp.get('id')
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'task',
                            'date_time': datetime.now(),
                            'state': 'success',
                            'message': 'Exported Successfully'
                        })]
                    })
                    return parsed_resp.get('id')
                else:
                    sf_config.write({
                        'salesforce_instance_line_ids': [(0, 0, {
                            'type': 'task',
                            'date_time': datetime.now(),
                            'state': 'error',
                            'message': 'Enable to Export Something went Wrong.'
                        })]
                    })
                    return False

    def exportActivity_to_sf(self, is_from_cron=False):
        if len(self) > 1 and not is_from_cron:
            raise UserError(_("Please Select 1 record to Export"))

        ''' PREPARE DICT FOR SENDING TO SALESFORCE '''
        activity_dict = {}
        if self.request_partner_id:
            activity_dict['WhoId'] = self.request_partner_id.x_salesforce_id
        if self.parent_id:
            activity_dict['WhatId'] = self.parent_id.x_salesforce_id
        if self.summary:
            activity_dict['Subject'] = self.summary
        if self.sf_status:
            activity_dict['Status'] = dict(self._fields['sf_status'].selection).get(self.sf_status)
        if self.sf_status:
            activity_dict['Priority'] = dict(self._fields['priority'].selection).get(self.priority)
        if self.date_deadline:
            activity_dict['ActivityDate'] = str(self.date_deadline)
        result = self.sendDataToSf(activity_dict, is_cron=is_from_cron)
        if result:
            self.x_salesforce_exported = True

    @api.model
    def _scheduler_export_activity_to_sf(self):
        sf_config = self.env['salesforce.instance'].sudo().search([('is_default_instance', '=', True)], limit=1)
        if not sf_config:
            _logger.error("There is no default Salesforce instance")
            return False

        if sf_config.export_limit:
            activities = self.search([], limit=sf_config.export_limit)
        else:
            activities = self.search([])

        for activity in activities:
            try:
                activity.exportActivity_to_sf(is_from_cron=True)
            except Exception as e:
                _logger.error('Oops Some error in  exporting Activity to SALESFORCE %s', e)
