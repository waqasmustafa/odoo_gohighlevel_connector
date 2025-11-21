# odoo_gohighlevel_connector/models/sync_mixin.py
from odoo import models, fields


class GHLSyncMixin(models.AbstractModel):
    _name = "ghl.sync.mixin"
    _description = "GoHighLevel Sync Mixin"
    _abstract = True

    ghl_id = fields.Char(
        string="GoHighLevel ID",
        index=True,
        copy=False,
        help="Record ID in GoHighLevel",
    )
    ghl_remote_updated_at = fields.Datetime(
        string="GHL Remote Updated At",
        copy=False,
        help="Last updatedAt from GoHighLevel applied to this record",
    )
    ghl_last_synced_at = fields.Datetime(
        string="GHL Last Synced At",
        copy=False,
        help="Last time this record was synced with GoHighLevel",
    )
    ghl_skip_sync = fields.Boolean(
        string="Skip GHL Sync",
        help="If enabled, this record will not be synced with GoHighLevel",
    )
