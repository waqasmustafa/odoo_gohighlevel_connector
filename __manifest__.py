# odoo_gohighlevel_connector/__manifest__.py
{
    'name': 'Odoo – GoHighLevel Connector',
    
    'summary': 'Bi-directional sync between Odoo and GoHighLevel - Contacts, Opportunities, Tasks & Notes',
    
    'description': '''
        Seamlessly integrate Odoo with GoHighLevel for complete CRM synchronization. Keep your contacts, opportunities, tasks, and notes in perfect sync across both platforms.
        
        Features:
        • Bi-directional contact synchronization with full field mapping
        • Opportunity/Deal sync with pipeline and stage mapping
        • Task synchronization with contact linking
        • Notes/Comments sync for contacts and opportunities
        • Automated sync via configurable cron jobs (every 5-60 minutes)
        • Manual "Sync Now" button for instant synchronization
        • Smart pagination - handles unlimited contacts and opportunities
        • Duplicate prevention with multiple safety layers
        • Incremental sync - only syncs changed records for efficiency
        • User mapping between Odoo and GoHighLevel
        • Pipeline and stage mapping for opportunities
        • Tag synchronization for contacts
        • Failed sync queue with automatic retry mechanism
        • Comprehensive logging and error handling
        • Test connection feature to verify API credentials
        • Nightly reconciliation for data consistency
        
        Perfect for businesses using both Odoo and GoHighLevel who want to maintain a single source of truth across platforms.
        
        Configuration:
        • Simple setup through Odoo Settings
        • API token and location ID configuration
        • Flexible sync direction (Odoo → GHL, GHL → Odoo, or Bi-directional)
        • Choose which entities to sync (Contacts, Opportunities, Tasks, Notes)
        • Configurable polling interval
        
        Technical Highlights:
        • Uses GoHighLevel API v2 (2021-07-28)
        • Efficient nextPageUrl pagination
        • Context-based loop prevention
        • Real-time updates without page refresh
        • Clean, maintainable code architecture
    ''',
    
    'author': 'Waqas Mustafa',
    'website': 'https://www.linkedin.com/in/waqas-mustafa-ba5701209/',
    'support': 'mustafawaqas0@gmail.com',
    
    'price': 90.99,
    'currency': 'USD',
    
    'version': '18.0.1.0.0',
    'license': 'LGPL-3',
    'category': 'Sales/CRM',
    
    'depends': [
        'base',
        'contacts',
        'crm',
        'project',
        'mail',
    ],
    
    'data': [
        'security/ir.model.access.csv',
        'views/config_views.xml',
        'views/task_views.xml',
        'data/cron.xml',
    ],
    
    'images': [
        'static/description/banner.png',
        'static/description/icon.png',
    ],
    
    'installable': True,
    'application': False,
    'auto_install': False,
}
