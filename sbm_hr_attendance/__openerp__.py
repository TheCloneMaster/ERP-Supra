{
    "name": "Suprabakti Mandiri Attendance Module",
    "version": "1.0",
    "depends": [
        "hr",
    ],
    "author": "IT Dev Team @ Suprabakti Mandiri",
    "category": "Human Resource",
    "description": """
        This module is a fresh module for Suprabakti Mandiri Attendance system needs
        This module already integerated with Fingerprint Device with ZK Web Service
        Developt by x100c machine
    """,
    "init_xml": [], 
    # 'demo':True,
    # 'data':[
    #     'data/religion.xml'
    # ],
    'update_xml': [
        # "rules.xml",
        # "actions.xml",
        "views.xml",
        'importlog.xml'
        # "menus.xml",
    ],
    'demo_xml': [],
    'installable': True,
    'active': False,
    'js': ['static/src/js/resource.js','static/src/js/openprint.js'],
    'qweb': ['static/src/xml/resource.xml'], 
    # 'js':['static/src/js/account_invoice.js'],
}