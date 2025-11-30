# odoo_gohighlevel_connector/__manifest__.py
{
    "name": "Odoo – GoHighLevel Connector",
    "summary": "Bi-directional sync between Odoo 18 and GoHighLevel (Contacts, Deals, Tasks, Notes)",
    "version": "18.0.1.0.0",
    "author": "Waqas Mustafa",
    "website": "https://www.linkedin.com/in/waqas-mustafa-ba5701209/",
    "license": "LGPL-3",
    "category": "Productivity",
    "depends": [
        "base",
        "contacts",
        "crm",
        "project",   # for project.task used as Tasks
        "mail",      # for notes
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/config_views.xml",
        "views/task_views.xml",
        "data/cron.xml",
    ],
    "installable": True,
    "application": False,
}
