{
	"name": "SBM STOCK SPLIT",
	"version": "1.0",
	"depends": ["base","mrp","sale","product","stock","sbm_delivery_note","sbm_work_order","sbm_order_preparation"],
	"author": "PT.SUPRABAKTI MANDIRI",
	"category": "STOCK SPLIT",
	"description": """Modul ini digunakan untuk Menggolah Stock Split PT.Suprabakti Mandiri""",
	"init_xml": [],
	'update_xml': ["stock_split_view.xml","search.xml","setting.xml"],
	'demo_xml': [],
	'installable': True,
	'active': False,
	'certificate': '',
	'js':['static/src/js/stock_split.js'],
}