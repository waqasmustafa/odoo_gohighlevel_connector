# odoo_gohighlevel_connector/models/ghl_mapping.py
from odoo import api, fields, models

class GHLUserMapping(models.Model):
    _name = "ghl.user.mapping"
    _description = "GoHighLevel User Mapping"
    _rec_name = "odoo_user_id"

    odoo_user_id = fields.Many2one("res.users", string="Odoo User", required=False)
    ghl_user_id = fields.Char(string="GHL User ID", required=True, help="User ID from GoHighLevel")
    ghl_user_name = fields.Char(string="GHL User Name", help="Name from GoHighLevel for reference")
    ghl_user_email = fields.Char(string="GHL User Email", help="Email from GoHighLevel for reference")
    
    _sql_constraints = [
        ('odoo_user_uniq', 'unique(odoo_user_id)', 'Odoo User must be unique!'),
        ('ghl_user_uniq', 'unique(ghl_user_id)', 'GHL User ID must be unique!'),
    ]

    @api.model
    def fetch_users_from_ghl(self):
        """Fetch users from GHL and create mapping records."""
        backend = self.env["odoo.ghl.backend"]
        users = backend.get_users()
        
        created_count = 0
        for u in users:
            u_id = u.get("id")
            u_name = u.get("name") or u.get("firstName", "") + " " + u.get("lastName", "")
            u_email = u.get("email")
            
            # Check if mapping exists
            existing = self.search([("ghl_user_id", "=", u_id)], limit=1)
            
            if not existing:
                self.create({
                    "ghl_user_id": u_id,
                    "ghl_user_name": u_name.strip(),
                    "ghl_user_email": u_email,
                })
                created_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Fetched {created_count} new users from GoHighLevel.',
                'type': 'success',
                'sticky': False,
            }
        }

class GHLPipelineMapping(models.Model):
    _name = "ghl.pipeline.mapping"
    _description = "GoHighLevel Pipeline Mapping"
    _rec_name = "odoo_stage_id"

    odoo_stage_id = fields.Many2one("crm.stage", string="Odoo Stage", required=False)
    ghl_pipeline_id = fields.Char(string="GHL Pipeline ID", required=True)
    ghl_pipeline_name = fields.Char(string="GHL Pipeline Name")
    ghl_stage_id = fields.Char(string="GHL Stage ID", required=True)
    ghl_stage_name = fields.Char(string="GHL Stage Name")

    _sql_constraints = [
        ('odoo_stage_uniq', 'unique(odoo_stage_id)', 'Odoo Stage must be unique!'),
    ]

    @api.model
    def fetch_pipelines_from_ghl(self):
        """Fetch pipelines and stages from GHL and create mapping records."""
        backend = self.env["odoo.ghl.backend"]
        pipelines = backend.get_pipelines()
        
        created_count = 0
        for p in pipelines:
            p_id = p.get("id")
            p_name = p.get("name")
            for s in p.get("stages", []):
                s_id = s.get("id")
                s_name = s.get("name")
                
                # Check if mapping exists
                existing = self.search([
                    ("ghl_pipeline_id", "=", p_id),
                    ("ghl_stage_id", "=", s_id)
                ], limit=1)
                
                if not existing:
                    self.create({
                        "ghl_pipeline_id": p_id,
                        "ghl_pipeline_name": p_name,
                        "ghl_stage_id": s_id,
                        "ghl_stage_name": s_name,
                    })
                    created_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Fetched {created_count} new pipeline stages from GoHighLevel.',
                'type': 'success',
                'sticky': False,
            }
        }

class GHLSyncQueue(models.Model):
    _name = "ghl.sync.queue"
    _description = "GoHighLevel Sync Retry Queue"
    _order = "create_date desc"

    name = fields.Char(string="Record Name", required=True)
    model_name = fields.Char(string="Model", required=True)
    record_id = fields.Integer(string="Record ID", required=True)
    action = fields.Selection([
        ('push', 'Push to GHL'),
        ('pull', 'Pull from GHL')
    ], string="Action", required=True)
    error_message = fields.Text(string="Error Message")
    retry_count = fields.Integer(string="Retry Count", default=0)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('failed', 'Failed'),
        ('done', 'Done')
    ], string="State", default='draft')

    def action_retry(self):
        """Retry the sync operation"""
        backend = self.env["odoo.ghl.backend"]
        for rec in self:
            try:
                record = self.env[rec.model_name].browse(rec.record_id)
                if not record.exists():
                    rec.state = 'done' # Record deleted, skip
                    continue
                
                if rec.action == 'push':
                    if rec.model_name == 'res.partner':
                        backend.push_contact(record)
                    elif rec.model_name == 'crm.lead':
                        backend.push_opportunity(record)
                    elif rec.model_name == 'project.task':
                        backend.push_task(record)
                    elif rec.model_name == 'mail.message':
                        backend.push_note(record)
                
                rec.state = 'done'
            except Exception as e:
                rec.retry_count += 1
                rec.error_message = str(e)
                rec.state = 'failed'

    @api.model
    def cron_retry_failed_syncs(self):
        """Cron job to retry failed syncs"""
        records = self.search([('state', 'in', ['draft', 'failed']), ('retry_count', '<', 5)], limit=50)
        records.action_retry()
