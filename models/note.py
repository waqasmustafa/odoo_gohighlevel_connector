# odoo_gohighlevel_connector/models/note.py
from odoo import api, models

# odoo_gohighlevel_connector/models/note.py
from odoo import api, models


class MailMessage(models.Model):
    _inherit = ["mail.message", "ghl.sync.mixin"]
    _name = "mail.message"

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("ghl_sync_running"):
            return super().create(vals_list)
        messages = super().create(vals_list)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        if (
            cfg["sync_notes"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for msg in messages:
                if msg.message_type == "comment" and not msg.ghl_skip_sync:
                    backend.push_note(msg)
        return messages

    def write(self, vals):
        if self.env.context.get("ghl_sync_running"):
            return super().write(vals)
        res = super().write(vals)
        backend = self.env["odoo.ghl.backend"]
        cfg = backend._get_config()
        
        # Define fields that should trigger a sync
        synced_fields = {
            "body", "ghl_skip_sync"
        }
        
        # Check if any synced field is in vals
        if not any(field in vals for field in synced_fields):
            return res

        if (
            cfg["sync_notes"]
            and cfg["sync_direction"] in ("odoo_to_ghl", "both")
            and cfg["sync_on"] == "create_update"
        ):
            for msg in self:
                if msg.message_type == "comment" and not msg.ghl_skip_sync:
                    backend.push_note(msg)
        return res
