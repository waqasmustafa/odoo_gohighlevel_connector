# odoo_gohighlevel_connector/models/config_settings.py
from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Basic API config
    ghl_api_token = fields.Char(
        string="GoHighLevel API Key",
        help="Private Integration (PIT) access token from GoHighLevel.",
    )
    ghl_location_id = fields.Char(
        string="GoHighLevel Location ID",
        help="GoHighLevel sub-account / locationId.",
    )

    # Behavior
    ghl_sync_on = fields.Selection(
        [
            ("create_update", "On Create/Update"),
            ("manual_only", "Manual / Cron Only"),
        ],
        string="Sync On",
        default="create_update",
    )
    ghl_sync_direction = fields.Selection(
        [
            ("odoo_to_ghl", "ODOO → GHL"),
            ("ghl_to_odoo", "GHL → ODOO"),
            ("both", "Bi-directional"),
        ],
        string="Sync Direction",
        default="both",
    )

    # Models to sync
    ghl_sync_contacts = fields.Boolean(string="Sync Contacts", default=True)
    ghl_sync_opportunities = fields.Boolean(string="Sync Opportunities/Deals", default=True)
    ghl_sync_tasks = fields.Boolean(string="Sync Tasks", default=False)
    ghl_sync_notes = fields.Boolean(string="Sync Notes", default=False)

    # Cron interval
    ghl_poll_interval_minutes = fields.Integer(
        string="Polling Interval (minutes)",
        default=10,
        help="How often cron should poll GoHighLevel for changes (GHL → Odoo).",
    )

    # Timestamps (read-only in UI)
    ghl_last_contact_pull = fields.Datetime(string="Last Contacts Pull", readonly=True)
    ghl_last_opportunity_pull = fields.Datetime(string="Last Opportunities Pull", readonly=True)
    ghl_last_task_pull = fields.Datetime(string="Last Tasks Pull", readonly=True)
    ghl_last_note_pull = fields.Datetime(string="Last Notes Pull", readonly=True)

    # ---------------------------------------------------------------
    # Load from ir.config_parameter
    # ---------------------------------------------------------------
    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env["ir.config_parameter"].sudo()

        res.update(
            ghl_api_token=ICP.get_param("odoo_ghl.api_token", default=""),
            ghl_location_id=ICP.get_param("odoo_ghl.location_id", default=""),
            ghl_sync_on=ICP.get_param("odoo_ghl.sync_on", default="create_update"),
            ghl_sync_direction=ICP.get_param("odoo_ghl.sync_direction", default="both"),
            ghl_sync_contacts=ICP.get_param("odoo_ghl.sync_contacts", default="True") == "True",
            ghl_sync_opportunities=ICP.get_param("odoo_ghl.sync_opportunities", default="True")
            == "True",
            ghl_sync_tasks=ICP.get_param("odoo_ghl.sync_tasks", default="False") == "True",
            ghl_sync_notes=ICP.get_param("odoo_ghl.sync_notes", default="False") == "True",
            ghl_poll_interval_minutes=int(
                ICP.get_param("odoo_ghl.poll_interval_minutes", default="10")
            ),
            ghl_last_contact_pull=ICP.get_param("odoo_ghl.last_contact_pull") or False,
            ghl_last_opportunity_pull=ICP.get_param("odoo_ghl.last_opportunity_pull")
            or False,
            ghl_last_task_pull=ICP.get_param("odoo_ghl.last_task_pull") or False,
            ghl_last_note_pull=ICP.get_param("odoo_ghl.last_note_pull") or False,
        )
        return res

    # ---------------------------------------------------------------
    # Save into ir.config_parameter
    # ---------------------------------------------------------------
    def set_values(self):
        super().set_values()
        ICP = self.env["ir.config_parameter"].sudo()

        ICP.set_param("odoo_ghl.api_token", self.ghl_api_token or "")
        ICP.set_param("odoo_ghl.location_id", self.ghl_location_id or "")
        ICP.set_param("odoo_ghl.sync_on", self.ghl_sync_on or "create_update")
        ICP.set_param("odoo_ghl.sync_direction", self.ghl_sync_direction or "both")
        ICP.set_param("odoo_ghl.sync_contacts", "True" if self.ghl_sync_contacts else "False")
        ICP.set_param(
            "odoo_ghl.sync_opportunities",
            "True" if self.ghl_sync_opportunities else "False",
        )
        ICP.set_param("odoo_ghl.sync_tasks", "True" if self.ghl_sync_tasks else "False")
        ICP.set_param("odoo_ghl.sync_notes", "True" if self.ghl_sync_notes else "False")
        ICP.set_param(
            "odoo_ghl.poll_interval_minutes",
            str(self.ghl_poll_interval_minutes or 10),
        )

    # small helpers so backend can update timestamps
    @api.model
    def _set_last_pull(self, contact=None, opportunity=None, task=None, note=None):
        ICP = self.env["ir.config_parameter"].sudo()
        if contact is not None:
            ICP.set_param("odoo_ghl.last_contact_pull", contact or "")
        if opportunity is not None:
            ICP.set_param("odoo_ghl.last_opportunity_pull", opportunity or "")
        if task is not None:
            ICP.set_param("odoo_ghl.last_task_pull", task or "")
        if note is not None:
            ICP.set_param("odoo_ghl.last_note_pull", note or "")
    @api.model
    def _reset_last_pull(self):
        self._set_last_pull(contact="", opportunity="", task="", note="")

    def action_ghl_manual_sync(self):
        """Trigger manual sync from Settings view."""
        self.env["odoo.ghl.backend"].manual_sync_now()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Sync Started",
                "message": "Manual sync has been triggered in the background.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_ghl_test_connection(self):
        """Test API connection from Settings."""
        self.ensure_one()
        self.env["odoo.ghl.backend"].test_api_connection(self.ghl_api_token, self.ghl_location_id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Connection Successful",
                "message": "Successfully connected to GoHighLevel API (200 OK).",
                "type": "success",
                "sticky": False,
            },
        }

    def action_fetch_pipelines(self):
        """Button action to fetch pipelines from GHL."""
        return self.env["ghl.pipeline.mapping"].fetch_pipelines_from_ghl()
