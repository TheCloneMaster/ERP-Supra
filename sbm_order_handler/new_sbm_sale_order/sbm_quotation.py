from datetime import datetime
from stock import stock
import math
import time
import webbrowser
import netsvc
import openerp.exceptions
from osv import osv, fields
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
import logging

_logger = logging.getLogger(__name__)

class inherit_stock_picking_out(osv.osv):
	_inherit = "stock.picking.out"
	_columns = {
			'invoice_id': fields.many2one('account.invoice','Invoice')
		}

class res_partner_extention(osv.osv):

	_inherit = 'res.partner'
	def name_get(self, cr, uid, ids, context=None):
		if context is None:
			context = {}
		if isinstance(ids, (int, long)):
			ids = [ids]
		res = []
		results = super(res_partner_extention,self).name_get(cr, uid, ids, context)
		tmp = 0
		for index, result in results:
			record_partner = self.browse(cr,uid,index,context=context) #siapin data object
			# print index,"<<<<<<<",result
			# print record_partner
			tmp = index
			if record_partner.city:
				city=" "+record_partner.city
			else:
				city=""
			if record_partner.state_id:
				state_id=" "+record_partner.state_id.name
			else:
				state_id=""

			if context.get('address_attention') or context.get('search_default_filter_confirm'):
				# kalo ada konteks attention
				# print context,"attention"
				res_name = "%s"%(record_partner.name)
				# print res_name,"ase"
				res.append((index,res_name))
				# print "--------------------------------------------------------",res_name

			elif context.get('address_delivery'):
				# print context,"delivery address"
				res_name = "%s"%(record_partner.name)+city+state_id+"\n"+ self._display_address(cr, uid, record_partner, without_company=True, context=context)
				res_name = res_name.replace('\n\n','\n')
				res_name = res_name.replace('\n\n','\n')
				
				res.append((index,res_name))
			elif context.get('address_invoice'):
				# print context,"delivery address"
				res_name = "%s"%(record_partner.name)+city+state_id
				res.append((index,res_name))
			else:
				# print "--------------------------------------------------------ELSEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEE",context
				res.append((index,result))

		return res


class Sale_order(osv.osv):	
	_name ='sale.order'
	_inherit =['sale.order','mail.thread']


	# def _count_total(self,cr,uid,ids,fields_name,args,context={}):
	# 	res={}
	# 	order_line = self.browser(cr,uid,ids,context=context)
	# 	print order_line,"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~"
	# 	# for line in order_line:
	# 	# 	print line ,"oaooooo+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
	# 	# 	res[line.id] = {
	# 	# 	"base_total":2323,
	# 	# 	}
		
	# 	return res
	
	# def name_get(self,cr,uid,ids,context=None):
	# 	test=self.pool.get('res.partner')
	# 	# coba = test.name_get(cr, uid,ids, context)
	# 	print super(Sale_order, test).name_get() , "testtttss"
	# 	return super(Sale_order, test).name_get(cr, uid,ids, context=context)
	def copy_pure_quotation(self,cr,uid,ids,context=None):
		# print "CALLEDDD",ids;
		rec = self.browse(cr,uid,ids,context)[0]
		isi_line = []
		
		
		for line in rec.order_line:
			isi_tax = []
			tax_ids = []
			change_prouct = self.pool.get('sale.order.line').onchange_product_quotation(cr, uid, [line.id], line.product_id.id, line.product_uom_qty, line.product_uom)['value'];
			for taxid in line.tax_id:
				tax_ids.append(taxid.id)

			
			isi_material=[]
			for material in line.material_lines:
				isi_material.append((0,0,
					{
					'product_id':material.product_id.id,
					'desc':material.desc,
					'qty':material.qty,
					'uom':material.uom.id,
					'picking_location':material.picking_location.id
					}))
			if len(isi_material)==0:
				
				isi_material = change_prouct['material_lines']

				_logger.error((change_prouct,"............>>>>",isi_material))


			isi_line.append((0,0,
				{
				'product_id':line.product_id.id,
				'name':line.name,
				'product_uom_qty':line.product_uom_qty,
				# 'price_unit':line.price_unit,
				# 'discount':line.discount,
				# 'base_total':line.base_total,
				# 'price_subtotal':line.price_subtotal,
				'tax_id':[(6,0,tax_ids)],
				# 'amount_tax':line.amount_tax,
				'material_lines':isi_material,
				'product_uom':line.product_uom.id
				}))

			# print isi_line,"ini isiiiiiiiiiiiiiiiiiiiiiiiiiii lineeeeeeeeeeeeeeeeee"
		prepareNewSO = {
			'origin':rec.origin,
			'order_policy':rec.order_policy,
			'client_order_ref':rec.client_order_ref,
			'partner_id':rec.partner_id.id,
			'date_order':rec.date_order,
			'note':rec.note,
			'user_id':rec.user_id.id,
			'payment_term':rec.payment_term.id,
			'company_id':rec.company_id.id,
			# 'amount_tax':rec.amount_tax,
			'state':'draft',
			# 'amount_untaxed':rec.amount_untaxed,
			'partner_shipping_id':rec.partner_shipping_id.id,
			'picking_policy':rec.picking_policy,
			'incoterm':rec.incoterm.id,
			'carrier_id':rec.carrier_id.id,
			'worktype':rec.worktype,
			'week':rec.week,
			'attention':rec.attention.id,
			'internal_notes':rec.internal_notes,
			'project_id':rec.project_id.id,
			'pricelist_id':rec.pricelist_id.id,
			'partner_invoice_id':rec.partner_invoice_id.id,
			'group_id':rec.group_id.id,
			'order_line':isi_line

		}

		ListScope1 = []
		ListScope2 = []
		ListTerms = []

		for sSupra in rec.scope_work_supra:
			ListScope1.append(sSupra.id)
		for sCust in rec.scope_work_customer:
			ListScope2.append(sCust.id)
		for sTerm in rec.term_condition:
			ListTerms.append(sTerm.id)

		prepareNewSO['scope_work_supra'] = [(6,0,ListScope1)]
		prepareNewSO['scope_work_customer'] = [(6,0,ListScope2)]
		prepareNewSO['term_condition'] = [(6,0,ListTerms)]

		newOrderId = self.create(cr,uid,prepareNewSO,context)

		# set old order reference id
		self._set_repeat_so_id(cr,uid,newOrderId,rec.id,context=context)

		
		dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'sbm_order_handler', 'quotation_form_view')
		return {
			'view_mode': 'form',
			'view_id': view_id,
			'view_type': 'form',
			'view_name':'quotation.form',
			'res_model': 'sale.order',
			'type': 'ir.actions.act_window',
			'target': 'current',
			'res_id':newOrderId,
			'domain': "[('id','=',"+str(newOrderId)+")]",
		}

	# To set repeat_so_id field
	def _set_repeat_so_id(self,cr,uid,ids,old_so_id,context={}):
		return self.write(cr,uid,ids,{'repeat_so_id':old_so_id},context)

	def _check_before_save(self,cr,uid,order_line):
		# print order_line, "<.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.><.>"
		for material in order_line:
			print material,"<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<"
			material_lines = material[2]['material_lines']
		if order_line and material_lines:
			res = True
		else:
			res = False
		return res

	def create(self, cr, uid,vals, context=None):
		res =None
		if(self._check_before_save(cr,uid,vals.get('order_line'))):
			sequence_no_quotation = self.pool.get('ir.sequence').get(cr, uid, 'quotation.sequence.type')
			vals['quotation_no'] = sequence_no_quotation
			res = super(Sale_order, self).create(cr, uid, vals, context=context)
		else:
			raise osv.except_osv(_('Warning'),_('Order Line dan Material Line tidak boleh kosong'))
		return res


	def _count_total(self, cr, uid, ids, name, args, context={}):
		res = {}
		sale_order = self.browse(cr,uid,ids,context=context)
		# print sale_order
		total_base_total=0
		for i in sale_order:
			for r in i.order_line:
				print r.id,"-----",r.base_total
				total_base_total += r.base_total
			res[i.id] = {"base_total":total_base_total,}
		print total_base_total
		return res

	def _count_tax(self,cr,uid,ids,fields_name,args,context={}):
		res={}
		return res

	def _inv_base_total(self,cr,uid,ids,fields_name,args,context={}):
		res={}
		return res
	def _get_so_line_by_so(self,cr,uid,ids,context={}):
		res = {}
		for line in self.pool.get('sale.order.line').browse(cr,uid,ids,context=context):
			res[line.order_id.id]=True
		return res.keys()
	def _get_total_discount(self, cr, uid, ids, name, args, context={}):
		res = {}
		sale_order = self.browse(cr,uid,ids,context=context)
		print sale_order
		total_discount_nominal=0
		for i in sale_order:
			for r in i.order_line:
				print r.id,"-----",r.discount_nominal
				total_discount_nominal += r.discount_nominal
			res[i.id] = {"total_amount_discount":total_discount_nominal,}
		print total_discount_nominal
		return res

	def _get_years(self,cr,uid,ids,name,args,context={}):
		res={}
		sale_order = self.browse(cr,uid,ids,context=context)
		# print sale_order,"aaaaaaaaaaa"
		for i in sale_order:
			name = i.quotation_no[3:5]
			print name,"ini namanya"
			res[i.id]={'is_year':'20'+name}	

		
		return res

	def _get_month(self,cr,uid,ids,name,args,context={}):
		res={}
		sale_order = self.browse(cr,uid,ids,context=context)
		# print sale_order,"aaaaaaaaaaa"
		for i in sale_order:
			name = i.quotation_no[6:8]
			# print name,"ini namanya"
			
			res[i.id]={'month':name}	

		
		return res

	def _search_month(self, cr, uid, obj, name, args, context):
		
		for i in args:
			filter_no=str(i[2])
			if len(filter_no)==1:
				filter_no="0"+str(i[2])
		res = [('name','like','%/%/'+filter_no+"/%")]
	
		return res

	def _search_years(self, cr, uid,obj, name, args, context={}):
		for i in args:
			print i[2]
			filter_no = str(i[2])
			if len(filter_no)>2:
				filter_no=filter_no[-2:]
		res = [('name','ilike','%/'+str(filter_no))]
		return res

		

	_columns = {
		'quotation_no':fields.char(string='Quotation#',required=True),
		'base_total':fields.function(
			_count_total,
			string='Base Total',
			type="float",
			store={
				'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 20),
				'sale.order.line': (_get_so_line_by_so, ['price_unit','product_uom_qty'], 20),
			},
			multi="line_total"
		),
		'doc_year':fields.function(_get_years,fnct_search=_search_years,string='Doc Years',store=False),
		'doc_month':fields.function(_get_month,fnct_search=_search_month,string='Doc Month',store=False),
		'quotation_state':fields.selection([('draft','Draft'),('confirmed','Confirmed'),('win','Win'),('lost','Lost'),('cancel','Cancel')],string="Quotation State",track_visibility="onchange"),
		'cancel_stage':fields.selection([('internal user fault','Internal User Fault'),('external user fault','External User Fault'),('lose','Lose')]),
		'cancel_message':fields.text(string="Cancel Message"),
		'revised_histories':fields.one2many('sale.order.revision.history','sale_order_id'),
		'total_amount_discount':fields.function(
			_get_total_discount, 
			string="total Discount",
			type="float",
			store={
				'sale.order': (lambda self, cr, uid, ids, c={}: ids, ['order_line'], 20),
				'sale.order.line': (_get_so_line_by_so, ['discount','discount_nominal'], 20),
			},
			multi="line"

			),
		'repeat_so_id': fields.many2one('sale.order', 'Old Order Ref', ondelete="RESTRICT", onupdate="CASCADE", track_visibility="onchange"),
	}
	# _sql_constraints = [
	# 	('quotation_no_unique', 'unique(quotation_no)', 'The quotation_no must be unique !')
	# 	]
	_defaults={
		'quotation_no':"/",
		'quotation_state':'draft',
		# 'partner_id': lambda self, cr, uid, context: context.get('partner_id', False) and self.pool.get('res.partner').address_get(cr, uid, [context['partner_id']], ['invoice'])['invoice'],
			}
	_track={
		'partner_id':{},
		'payment_term':{},
		'partner_shipping_id':{},
		'attention':{},
		'partner_invoice_id':{},
		'pricelist_id':{},
		'date_order':{},
		'user_id':{},
		'group_id':{},
		'amount_untaxed':{}
	}

	def print_rfq(self,cr,uid,ids,context={}):
		res={}
		sale_order = self.browse(cr,uid,ids,context=context)[0]
		id_report = self.pool.get('ir.actions.report.xml').search(cr, uid, [('report_name','=','quotation.webkit')])
		datas = {
				 'model': 'sale.order',
				 'ids': ids,
				 'form': self.read(cr, uid, ids[0], context=context),
		}
		# self.pool.get('ir.actions.report.xml').write(cr,uid,id_report,{'name':sale_order.name})
		return {
			'type': 'ir.actions.report.xml', 
			'report_name': 'quotation.webkit',
			'name': sale_order.quotation_no,
			'datas': datas,
			'nodestroy': True
		}
		
	def print_rfq_web(self,cr,uid,ids,context={}):
		searchConf = self.pool.get('ir.config_parameter').search(cr, uid, [('key', '=', 'base.print')], context=context)
		browseConf = self.pool.get('ir.config_parameter').browse(cr,uid,searchConf,context=context)[0]
		urlTo = str(browseConf.value)+"print-sale-order/rfq&id="+str(ids[0])
		
		return {
			'type'  : 'ir.actions.client',
			# 'target': 'new',
			'tag'   : 'print.out.op',
			'params': {
				# 'id'  : ids[0],
				'redir' : urlTo,
				'uid':uid
			},
		}

	def print_so_web(self,cr,uid,ids,context={}):
		searchConf = self.pool.get('ir.config_parameter').search(cr, uid, [('key', '=', 'base.print')], context=context)
		browseConf = self.pool.get('ir.config_parameter').browse(cr,uid,searchConf,context=context)[0]
		urlTo = str(browseConf.value)+"print-sale-order/sale_order&id="+str(ids[0])
		
		return {
			'type'  : 'ir.actions.client',
			# 'target': 'new',
			'tag'   : 'print.out.op',
			'params': {
				# 'id'  : ids[0],
			'redir' : urlTo,
			'uid':uid
			},
		}
	def print_so(self,cr,uid,ids,context={}):
		res={}
		sale_order = self.browse(cr,uid,ids,context=context)[0]
		id_report = self.pool.get('ir.actions.report.xml').search(cr, uid, [('report_name','=','quotation.webkit')])
		datas = {
				 'model': 'sale.order',
				 'ids': ids,
				 'form': self.read(cr, uid, ids[0], context=context),
		}
		# self.pool.get('ir.actions.report.xml').write(cr,uid,id_report,{'name':sale_order.name})
		return {
			'type': 'ir.actions.report.xml', 
			'report_name':'sale.order.webkit',
			'name': sale_order.name,
			'datas': datas,
			'nodestroy': True
		}


	def confirm_quotation(self,cr,uid,ids,context={}):
		res = False
		quotation_obj = self.pool.get("sale.order")
		data_sekarang = self.browse(cr,uid,ids,context=context)[0]

		if data_sekarang.order_line	==[]:
			quotation_obj.write(cr,uid,ids,{'quotation_state':'draft'},context=context)
			raise osv.except_osv(_('Warning'),_('Order Cant be confirmed, Order Line is Empty, Please Check Order Lines'))
		else:
			for line in data_sekarang.order_line:
				if line.material_lines==[]:
					quotation_obj.write(cr,uid,ids,{'quotation_state':'draft'},context=context)
					raise osv.except_osv(_('Warning'),_('Order Cant be confirmed, Sale Order Material is Empty, Please Reload'))
		if data_sekarang.quotation_state == 'draft':
			# sequence_no_quotation = self.pool.get('ir.sequence').get(cr, uid, 'quotation.sequence.type')
			if quotation_obj.write(cr,uid,ids,{'quotation_state':'confirmed'},context=context):
				res = True
		else:
			raise osv.except_osv(_('Warning'),_('Order Cant be confirmed, Only Draft Qotation State can be confirmed!'))

		return res

	def loadBomLine(self,cr,uid,bom_line,product_uom_qty,product_uom,seq_id,is_loaded_from_change=True):
		res = {}
		print bom_line, 
		print bom_line.product_id.id, "iddd" 
		res = {
				'product_id':bom_line.product_id.id,
				'uom':bom_line.product_uom.id,
				'qty':product_uom_qty*bom_line.product_qty,
				'picking_location':seq_id,
				'is_loaded_from_change':is_loaded_from_change,
		}
		return res

	def generate_wo(self,cr,uid,ids,context={}):
		action = False
		val = self.browse(cr, uid, ids, context={})[0]
		ops = self.browse(cr, uid, ids, context=context)
		obj_wo = self.pool.get('sbm.work.order')
		
		new_wo_ids = []
		for so in ops:
			prep_wo = {}
			evt_prepare_change = obj_wo.sale_order_change(cr, uid, ids, val.id)

			prep_wo = evt_prepare_change['value']
			prep_wo['sale_order_id']=so.id
			prep_wo['source_type']='sale_order'

			id_wo = obj_wo.create(cr, uid, prep_wo, context=context)

		pool_data=self.pool.get("ir.model.data")
		action_model,action_id = pool_data.get_object_reference(cr, uid, 'sbm_order_handler', "sbm_work_order_form")     
		action_pool = self.pool.get(action_model)
		res_id = action_model and action_id or False
		action = action_pool.read(cr, uid, action_id, context=context)
		action['name'] = 'sbm.work.order.form'
		action['view_type'] = 'form'
		action['view_mode'] = 'form'
		action['view_id'] = [res_id]
		action['res_model'] = 'sbm.work.order'
		action['type'] = 'ir.actions.act_window'
		action['target'] = 'current'
		action['res_id'] = id_wo
		return action


	def generate_material(self,cr,uid,ids,context={}):
		res={}
		vals = {}
		if type(ids) != list:
			ids = [ids]
		
		sale_orders = self.browse(cr,uid,ids,context)
		print sale_orders,"------------------------------------------->>>>>>>>>>>>>>>>>>"
		for sale_order in sale_orders:
			if sale_order.quotation_state ==False and sale_order.state != 'draft' and sale_order.state != 'cancel':
				# automatic set quotation state into win
				self.write(cr,uid,ids,{'quotation_state':'win'})

			for material in sale_order.order_line:

				if material.material_lines ==[]:
					product=self.pool.get('product.product').browse(cr,uid,material.product_id.id,context)
					this_material = self.pool.get('sale.order.line')

					seq_id = self.pool.get('stock.location').search(cr, uid, [('name','=','HO')])

					if len(seq_id):
						seq_id = seq_id[0]
					# if product has bill of materials
					if product.bom_ids:
						bom_line_set = self.pool.get('mrp.bom').browse(cr,uid,product.bom_ids[0].id)

						vals= {
						'material_lines':[(0,0,self.loadBomLine(cr,uid,bom_line,material.product_uom_qty,material.product_uom,seq_id)) for bom_line in bom_line_set.bom_lines],
						
						}
					else:
						vals={
						'material_lines': [
								(0,0,{
									'product_id':material.product_id.id,
									'desc': material.name,
									'qty':material.product_uom_qty,
									'uom':material.product_uom.id,
									'picking_location':seq_id,
									'is_loaded_from_change':True
									} )
							],
						
						}
					# print material.product_uom.id,"<<<<<<<<<<<"
					this_material.write(cr,uid,material.id,vals,context)
				else:
					raise osv.except_osv(_('Warning'),_('Material Item sudah ada !!!'))
			


		

		return res

	def cancel_quotation(self,cr,uid,ids,context={}):
		res = False
		quotation_obj = self.pool.get("sale.order")
		data_sekarang = self.browse(cr,uid,ids,context=context)[0]

		if data_sekarang.quotation_state == 'draft':
			if quotation_obj.write(cr,uid,ids,{'quotation_state':'cancel'},context=context):
				res = True
		else:
			raise osv.except_osv(_('Warning'),_('Order Cant be Cancel'))

		return res

	def cek_so(self,cr,uid,ids,context={}):
		res =False
		sale_order = self.browse(cr,uid,ids,context=context)[0]
		invoice_in_picking=False
		invoice_in_invoice=False
		amount_total = 0
		#cek invoice di picking_ids 
		if sale_order.picking_ids:
			#menghitung total amount di invoice
			for hitung in sale_order.picking_ids:
				if hitung.invoice_id.amount_total and hitung.invoice_id.state=='paid':
					amount_total+=hitung.invoice_id.amount_total

			for picking in sale_order.picking_ids:
				#kondisi di mana state = paid maka invoice_in_picking = True dan cek amount_total di invoice sama dengan amount_total di sale order
				if picking.invoice_id.state=='paid' and amount_total>=sale_order.amount_total:
					invoice_in_picking =True
					
		#cek invoice di invoice_ids 
		if sale_order.invoice_ids:
			for invoice in sale_order.invoice_ids:
				#kondisi di mana state = paid maka invoice_in_invoice = true
				if invoice.state == 'paid':
					invoice_in_invoice =True
		# cek invoice_in_picking atau invoice_in_invoice 
		if invoice_in_picking or invoice_in_invoice:
			cek_data = False
			#cek isi material line apakah ada
			if sale_order.order_line[0].material_lines:

				for material_so in sale_order.order_line[0].material_lines:
					#cek apakah quantity sama shipped_qty atau type productnya = service
					if material_so.qty == material_so.shipped_qty or material_so.product_id.type=="service":
						cek_data=True
						
					# for material_so in sale_order.order_line[0].material_lines:
					# 	if material_so.op_lines:
					# 		dn_line_material_id = self.pool.get("delivery.note.line.material").search(cr,uid,[('op_line_id',"=",material_so.op_lines[0].id)])
					# 		dn_line_material = self.pool.get("delivery.note.line.material").browse(cr,uid,dn_line_material_id)
					# 		if dn_line_material:
					# 			cek_data=True
					# 		else:
					# 			cek_data=False
					# 			break
					# if cek_data:
					# 	if self.pool.get('sale.order').write(cr,uid,ids,{'state':'done'},context=context):
					# 		res = True
					else:
						cek_data=False
						break
				#cek data untuk di eksekusi
				if cek_data:
					if self.pool.get('sale.order').write(cr,uid,ids,{'state':'done'},context=context):
						res = True
				else:
					raise osv.except_osv(_('Warning'),_('Material line belum semuanya terkirim'))

			else:
				raise osv.except_osv(_('Warning'),_('Belum ada material'))

				
		else:
			raise osv.except_osv(_('Warning'),_('invoice belum selesai'))

		return  res

# <record model='ir.actions.act_window' id="wizard_lost_quotation_form">
# 			<field name="name">wizard.lost.quotation.form</field>
# 			<field name="type">ir.actions.act_window</field>
# 			<field name="res_model">wizard.lost.quotation</field>
# 			<field name="view_type">form</field>
# 			<field name="view_mode">form</field>
# 			<field name="view_id" ref="lost_quotation_wizard"/>
# 			<field name="target">new</field>
# 		</record>


	# def wizard_lost_quotation_form(self,cr,uid,ids,context={}):
	# 	dir={
	# 		"name":"wizard.lost.quotation.form",
	# 		"type":"ir.actions.act_window",
	# 		"res_model":"wizard.lost.quotation",
	# 		"view_type":"form",
	# 		"view_mode":"form",
	# 		"view_id ref=lost_quotation_wizard",
	# 		"target":"new"


	# 	}

	# 	return dir

class sale_order_material_line(osv.osv):


	_name = 'sale.order.material.line'
	_description = 'Sale order material line'

	# def _state(self,cr,uid,ids,name,args,context={}):
	# 	name1=self.browse(cr,uid,ids)
	# 	res={}
	# 	a=1
	# 	for i in name1:
	# 		so_line =self.pool.get('sale.order.line').browse(cr,uid,i.sale_order_line_id)
	# 		so_=self.pool.get('sale.order').browse(cr,uid,so_line.order_id)
	# 		res[i.id]=so.state
	# 	return res



	_columns = {
		'sale_order_line_id':fields.many2one('sale.order.line',string="Sale Order Line", onupdate="CASCADE", ondelete="CASCADE"),
		'product_id':fields.many2one('product.product',string="Product", required=True, domain=[('sale_ok','=','True'),('categ_id.name','!=','LOCAL')], active=True),
		'desc':fields.text(string="Description"),
		'qty':fields.float(string="Qty",required=True),
		'uom':fields.many2one("product.uom",required=True,string="uom"),
		'picking_location':fields.many2one('stock.location',required=True),
		'is_loaded_from_change':fields.boolean('Load From Change ?'),
		'sale_order_id': fields.related('sale_order_line_id','order_id', type='many2one', relation='sale.order'),
		'status': fields.related('sale_order_line_id','state', type='char', relation='sale.order'),
		# 'status':fields.function(_state,string="State",type="string",store=False),



		# 'op_lines':fields.one2many('order.preparation.line','sale_line_material_id'),
		# 'shipped_qty':fields.function(_count_shipped_qty,type="float",store=False)}
			# # {
			# # 	'sale.order.line': (lambda self, cr, uid, ids, c={}: ids, ['price_unit','product_uom_qty'], 1),

			# # }
			# ,
			# string="Base Total",
			# multi="line_total"),
		# }
				}
	_defaults = {
		'is_loaded_from_change':False
	}

	def _get_ho_location(self,cr,uid,ids,context={}):
		objname, location_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'stock', 'stock_location_stock')
		if not location_id:
			raise osv.except_osv(_('Error'),_('Please Define Default Stock Location'))
		return location_id
	_defaults={
		
		'picking_location':_get_ho_location,
		'qty':1

	}
	def onchange_product_material(self,cr,uid,ids,product_id):
		res={}
		if product_id:
			product= self.pool.get('product.product').browse(cr,uid,product_id,{})
			res["value"]={
			"uom":product.uom_id.id
			}

		print res 
		return res

	def onchange_product_uom(self,cr,uid,ids,product_id,uom,context={}):
		res ={}
		if product_id:
				
			product = self.pool.get("product.product").browse(cr,uid,product_id,context=context)
		
			kategori_uom_product = product.uom_id.category_id.id
			
			# print Kategori_uom	,"<<<<<<<<<<<<<<<<<<<<<<<<"
			if uom:
				product_uom_browse = self.pool.get("product.uom").browse(cr,uid,uom,context=context)
				Kategori_uom =product_uom_browse.category_id.id
				if Kategori_uom != kategori_uom_product :
					if uom != product.uos_id.id:
						res["value"]={"uom":product.uom_id.id}
						res['warning']={'title':"Error",'message':'Kategori Uom Harus sama'}

		
				# return res
				# raise osv.except_osv(_('Warning'),_('Kategori Uom Harus sama'))

		return res
	


class sale_order_line(osv.osv):	
	_inherit ='sale.order.line'
	def _count_base_total(self,product_uom_qty,price_unit):
		
		return product_uom_qty*price_unit
	def _count_discount_nominal(self,base_total,discount):
		return base_total * discount/100.0
	def _count_price_subtotal(self,base_total,discount_n):
		return base_total-discount_n
	"""
	@tax_ids harus diisi sama list yang isinya integer id tax cth: [1,2,3,4,5]
	"""
	def _count_amount_tax(self,cr,uid,subtotal,tax_ids):
		list_tax = tax_ids
		amount_tax_total=0
				
		for i in list_tax:
			tax_bro = self.pool.get("account.tax").browse(cr,uid,i)
		
			amount_tax= subtotal* tax_bro.amount
			amount_tax_total+=amount_tax
		
		return amount_tax_total

	def _count_amount_line(self, cr, uid, ids, name, args, context={}):
		# print "PANGGIL _count_amount_line ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
		res = {}
		order_lines = self.browse(cr,uid,ids,context=context)
		
		for line in order_lines:
			
			base_total	= self._count_base_total(line.product_uom_qty,line.price_unit)
			discount_n = self._count_discount_nominal(base_total,line.discount)
			subtotal_ = self._count_price_subtotal(base_total,discount_n)
			list_tax_id	= []
			for t in line.tax_id:
				
				list_tax_id.append(t.id)
			taxes_total= self._count_amount_tax(cr,uid,subtotal_,list_tax_id)
			
			res[line.id] = {"base_total":base_total,
							"discount_nominal":discount_n,
							"price_subtotal":subtotal_,
							"amount_tax":taxes_total}

						

		return res
	_columns = {
		'base_total':fields.function(
			_count_amount_line,
			type="float",
			store={
				'sale.order.line': (lambda self, cr, uid, ids, c={}: ids, ['price_unit','product_uom_qty'], 1),

			},
			string="Base Total",
			multi="line_total"
		),
		'amount_tax':fields.function(
			_count_amount_line,
			type="float",
			store={
				'sale.order.line': (lambda self, cr, uid, ids, c={}: ids, ['base_total','tax_id'], 1),
			},
			string="Tax Amount",
			multi="line_total"
			),		
		'material_lines':fields.one2many('sale.order.material.line','sale_order_line_id'),
		'name':fields.text(string='Description',required=False)	
	}




	
	def onchange_price_unit(self,cr,uid,ids,product_uom_qty,price_unit,discount,discount_nominal,tax_id):
		res={
			'base_total':0.0,
			'discount_nominal':0.0,
			'price_subtotal':0.0,
			'amount_tax':0.0
		}
		
		if product_uom_qty and price_unit:
			base_total	= self._count_base_total(product_uom_qty,price_unit)
			discount_n = self._count_discount_nominal(base_total,discount)
			subtotal_ = self._count_price_subtotal(base_total,discount_n)
			taxes_total = self._count_amount_tax(cr,uid,subtotal_,tax_id[0][2])
			res["value"]={
				"base_total":base_total,
				"discount_nominal":discount_n,
				"price_subtotal":subtotal_,
				"amount_tax":taxes_total
			}
		return res

	def onchange_diskon(self,cr,uid,ids,product_uom_qty,price_unit,discount,discount_nominal,tax_id):
		res={
			'base_total':0.0,
			'discount_nominal':0.0,
			'price_subtotal':0.0,
			'amount_tax':0.0
			}
		if product_uom_qty and price_unit:
			base_total	= self._count_base_total(product_uom_qty,price_unit)
			discount_n = discount_nominal
			subtotal_ = self._count_price_subtotal(base_total,discount_n)
			
			taxes_total = self._count_amount_tax(cr,uid,subtotal_,tax_id[0][2])
			# taxes_total = self._count_amount_tax(subtotal_,tax_id)
			res["value"]={
						"base_total":base_total,
						"price_subtotal":subtotal_,
						"amount_tax":taxes_total
						}
		return res

	def loadBomLine(self,cr,uid,bom_line,product_uom_qty,product_uom,seq_id,is_loaded_from_change=True):
		res = {}
		print bom_line, 
		print bom_line.product_id.id, "iddd" 
		res = {
				'product_id':bom_line.product_id.id,
				'uom':bom_line.product_uom.id,
				'qty':product_uom_qty*bom_line.product_qty,
				'picking_location':seq_id,
				'is_loaded_from_change':is_loaded_from_change,
		}
		return res

	def loadBomLineqty(self,cr,uid,product_id,product_uom_qty,product_uom,seq_id,base_total,discount_n,subtotal_,taxes_total):
		res = {}
		res = {
				'product_id':product_id.product_id.id,
				'uom':product_id.product_uom.id,
				'qty':product_uom_qty*product_id.product_qty,
				'picking_location':seq_id,
				"base_total":base_total,
				"price_subtotal":subtotal_,
				"amount_tax":taxes_total
				}
		return res

	def onchange_product_quotation(self,cr,uid,ids,product_id,product_uom_qty,product_uom):
		res={}

		order_lines = self.pool.get('sale.order.line').browse(cr,uid,ids)
		old_material_ids = []
		for line in order_lines:
			for material in line.material_lines:
				old_material_ids.append(material.id)

		print old_material_ids,">>>>>>>>>>>>>>>>>>>>>>>>>>>"

		if product_id:
			seq_id = self.pool.get('sale.order.material.line')._get_ho_location(cr,uid,ids,context={})

			product= self.pool.get('product.product').browse(cr,uid,product_id,{})
			

			if product.bom_ids:
				bom_line_set = self.pool.get('mrp.bom').browse(cr,uid,product.bom_ids[0].id)

				res['value'] = {
					'material_lines':[(0,0,self.loadBomLine(cr,uid,bom_line,product_uom_qty,product_uom,seq_id)) for bom_line in bom_line_set.bom_lines],
					"product_uom":product.uom_id.id,
					# "tax_id":[(0,0,)]
				}

				if old_material_ids:
					mtr_lines = res['value']['material_lines']

					for old_mtr in old_material_ids:
						print "-------------------->>>>>>>>>>>>>>",mtr_lines
						lr = (2,old_mtr)
						mtr_lines.append(lr)
						print "-------------------->>>>>>>>>>>>>><<<<<<<<<<<<<<<<<",mtr_lines
					res['value']['material_lines'] = mtr_lines

			else:

				res['value'] = {
					'material_lines': [
						(0,0,{'product_id':product_id,'qty':product_uom_qty,'uom':product.uom_id.id,'picking_location':seq_id,'is_loaded_from_change':True}),
					],
					"product_uom":product.uom_id.id
				}

			if old_material_ids:
				mtr_lines = res['value']['material_lines']

				for old_mtr in old_material_ids:
					print "-------------------->>>>>>>>>>>>>>",mtr_lines
					lr = (2,old_mtr)
					mtr_lines.append(lr)
					print "-------------------->>>>>>>>>>>>>><<<<<<<<<<<<<<<<<",mtr_lines
				res['value']['material_lines'] = mtr_lines
			if product.description_sale:
				res['value']['name']=product.description_sale
			else:
				res['value']['name']=False
			if product.supplier_taxes_id:
				tax =[]
				for i in product.supplier_taxes_id:
					print i.id
					tax.append(i.id)
				print tax,"++++++++++++++++++++++++++++++++++"
				res['value']['tax_id']=tax
			else:
				res['value']['tax_id']=False


	
		print res 
		return res

	

	def onchange_product_uom(self,cr,uid,ids,product_id,product_uom,context={}):
		res ={}
		if product_id:
				
			product = self.pool.get("product.product").browse(cr,uid,product_id,context=context)
			print "LLLLLLLLLLLLLl"
			kategori_uom_product = product.uom_id.category_id.id
			
			# print Kategori_uom	,"<<<<<<<<<<<<<<<<<<<<<<<<"
			if product_uom:
				product_uom_browse = self.pool.get("product.uom").browse(cr,uid,product_uom,context=context)
				Kategori_uom =product_uom_browse.category_id.id
				if Kategori_uom != kategori_uom_product :
					if product_uom != product.uos_id.id:
						res["value"]={"product_uom":product.uom_id.id}
						res['warning']={'title':"Error",'message':'Kategori Uom Harus sama'}

		
				# return res
				# raise osv.except_osv(_('Warning'),_('Kategori Uom Harus sama'))

		return res
	
	def onchange_product_quotation_qty(self,cr,uid,ids,product_id,product_uom_qty,product_uom,price_unit,discount,tax_id,material_lines_object,context={}):
		res={}
		print material_lines_object,"cek------------------------------>"
		if product_uom_qty == False or product_uom_qty<1:
			res["warning"]={'title':"Error",'message':'Quantity tidak boleh kosong'}
			res['value'] = {
								
								"product_uom_qty":1
							}
		else:

			if product_id:
				base_total	= self._count_base_total(product_uom_qty,price_unit)
				discount_n = self._count_discount_nominal(base_total,discount)
				subtotal_ = self._count_price_subtotal(base_total,discount_n)
				taxes_total = self._count_amount_tax(cr,uid,subtotal_,tax_id[0][2])
				seq_id = self.pool.get('stock.location').search(cr, uid, [('name','=','HO')])
				if len(seq_id):
					seq_id = seq_id[0]
				
				product = self.pool.get('product.product').browse(cr,uid,product_id,{})
				
			
				all_values_without_bom =[]
				print "ini tidak ada bom"
				change_applied = True
				for material in material_lines_object:
					old_material = self.pool.get("sale.order.material.line").browse(cr,uid,material[1],context=context)
					# if material[0]==0 and material[2]['product_id']==product_id and masih_bisa==True:
					# 	all_values_without_bom.append((0,0,{'desc':material[2].get('desc',False),'product_id':material[2]['product_id'],"qty":product_uom_qty,'uom':material[2]["uom"],"picking_location":seq_id}))
					# 	print "record baru tapi"
					# 	masih_bisa = False
					# elif material[0]==0:
					# 	print "record baru"
					# 	all_values_without_bom.append((0,0,{'desc':material[2].get('desc',False),'product_id':material[2]['product_id'],"qty":material[2]["qty"],'uom':material[2]["uom"],"picking_location":seq_id}))
					# elif material[0]==1 and masih_bisa==True:
					# 	masih_bisa = False		
					# 	print "update tapi"
					# 	all_values_without_bom.append((1,material[1],{'desc':material[2].get('desc',old_material.desc),'product_id':product_id,'qty':product_uom_qty,'uom':product.uom_id.id,'picking_location':seq_id}))
					# elif material[0]==1:
					# 	all_values_without_bom.append((1,material[1],{'product_id':material[2]['product_id'],'qty':material[2]['qty'],'uom':material[2]['uom'],'picking_location':seq_id}))
					# 	print "update record"
					# elif material[0]==2:
					# 	print "hapus record"
					# 	all_values_without_bom.append((2,material[1]))
					# elif material[0]==4 and masih_bisa==True:
					# 	all_values_without_bom.append((1,material[1],{'product_id':product_id,'qty':product_uom_qty,'uom':product.uom_id.id,'picking_location':seq_id}))
					# 	print "menambahkan data dari yang sudah ada"
					# 	masih_bisa = False
					if material[0]==0:
						# new record
						print "New Record"
						update_values = {
							'desc':material[2].get('desc',False),
							'product_id':material[2]['product_id'],
							"qty":product_uom_qty,
							'uom':material[2]["uom"],
							"picking_location":seq_id,
							'is_loaded_from_change':False
						}
						if material[2].get('is_loaded_from_change',False):
							
							update_values['qty'] = product_uom_qty
							update_values['is_loaded_from_change'] = True
						else:
							update_values['qty'] = material[2].get('qty',0.0)

						all_values_without_bom.append((0,0,update_values))
					elif material[0]==1:
						# update record
						print "Update Record"
						
						updated_val = {
							'qty':material[2].get('qty',old_material.qty),
							'is_loaded_from_change':False,
							'product_id':material[2].get('product_id',old_material.product_id.id),
							'desc':material[2].get('desc',old_material.desc),
							'uom':material[2].get('uom',old_material.uom.id),
							'picking_location':seq_id



						}

						if old_material.is_loaded_from_change:
							updated_val['qty'] = product_uom_qty
							all_values_without_bom.append((1,material[1],updated_val))
							updated_val['is_loaded_from_change'] = True
						else:
							all_values_without_bom.append((1,material[1],updated_val))


						# if old_material.product_id.id == product_id:
						# 	if change_applied:
						# 		updated_val['qty'] = product_uom_qty
								
						# 		all_values_without_bom.append((1,material[1],updated_val))
						# 		change_applied = False
						# 	else:
						# 		all_values_without_bom.append((1,material[1],updated_val))
						# else:
						# 	all_values_without_bom.append((1,material[1],updated_val))


					elif material[0]==2:
						all_values_without_bom.append((2,material[1]))
						# delete
						print "Delete Record"
					elif material[0]==4:
						# existing data tinggal add
						print "Exist Record"
						print "Change applied--->",change_applied,">>>>",old_material.is_loaded_from_change
						update_values = {
							'desc':old_material.desc,
							'product_id':old_material.product_id.id,
							"qty":product_uom_qty,
							'uom':old_material.uom.id,
							"picking_location":seq_id,
							'is_loaded_from_change':False
						}
						if old_material.is_loaded_from_change:
							all_values_without_bom.append((1,material[1],update_values))
							update_values['is_loaded_from_change'] = True
						else:
							all_values_without_bom.append((4,material[1],False))

						# if old_material.product_id.id == product_id:
						# 	# jika product sama
							
						# 	if change_applied:
						# 		all_values_without_bom.append((1,material[1],{'qty':product_uom_qty}))
						# 		change_applied = False
								
						# 	else:
						# 		all_values_without_bom.append((4,material[1],False))
						# else:

						# 	all_values_without_bom.append((4,material[1],False))



							



						
					res['value']={
					"material_lines":all_values_without_bom,
					"base_total":base_total,
					"price_subtotal":subtotal_,
					"amount_tax":taxes_total
					}

		return res




class account_invoice_line(osv.osv):
	_inherit='account.invoice.line'
	_columns={
		'sale_order_lines': fields.many2many('sale.order.line', 'sale_order_line_invoice_rel', 'invoice_id', 'order_line_id', 'Order Lines', readonly=True),
	}

class sale_order_invoice(osv.osv):	
	_name ='sale.order'
	_inherit =['sale.order','mail.thread']
	# def action_invoice_create(self, cr, uid, ids, grouped=False, states=None, date_invoice = False, context=None):
	# 	res1={}
	# 	idInvoice = super(Sale_order,self).action_invoice_create(cr,uid,ids,grouped,states,date_invoice,context=context)
	# 	acount_invoice= self.pool.get('account.invoice').browse(cr,uid,idInvoice)
	# 	sale_order=self.browse(cr,uid,ids)[0]

	# 	index_order_line =1 
	# 	for order_line in sale_order.order_line:
	# 		index_invoice=1
		
	# 		for invoice_line in acount_invoice.invoice_line:
	# 			material_invoice =[]
	# 			for material in order_line.material_lines:
	# 				material_invoice.append("["+material.product_id.default_code+"]"+material.product_id.name)
	# 			material = "\n".join(material_invoice)

	# 			if index_order_line == index_invoice:
	# 				# print "///////////>>>>>>>>>>>>>>??????????//",material,"<<<<<<<<<??????////////////////"
	# 				write_invoice_line = self.pool.get('account.invoice.line').write(cr,uid,invoice_line.id,{'name':invoice_line.name+'\nConsist Of\n'+material})
	# 				index_invoice+=1
	# 			index_invoice+=1

	# 		index_order_line+=1
	# 	return res1

	def action_invoice_create(self, cr, uid, ids, grouped=False, states=None, date_invoice = False, context=None):
		res1={}
		idInvoice = super(sale_order_invoice,self).action_invoice_create(cr,uid,ids,grouped,states,date_invoice,context=context)
		account_invoice= self.pool.get('account.invoice').browse(cr,uid,idInvoice)
		# sale_order=self.browse(cr,uid,ids)[0]
		for inv_line in account_invoice.invoice_line:
			material_invoice =[]
			for order_line in inv_line.sale_order_lines:
				for material in order_line.material_lines:
					if material.desc:
						description = '\n'+material.desc
					else:
						description	=""
					material_invoice.append(
						"["
						+material.product_id.default_code
						+"]"
						+material.product_id.name
						+" ("
						+str(float(material.qty))
						+" "
						+material.uom.name
						+")"
						+description)
				if material_invoice:
					material ='\nConsist Of\n'+"\n".join(material_invoice)
				else:
					material =""
				write_invoice_line = self.pool.get('account.invoice.line').write(cr,uid,inv_line.id,{'name':inv_line.name+material})
		
				
		return idInvoice

class WizardCreatePbSo(osv.osv_memory):
	_inherit='wizard.create.pb'
	
	def default_get(self, cr, uid, fields, context=None):
		if context is None: context = {}
		so_ids = context.get('active_ids', [])
		active_model = context.get('active_model')
		# res = super(WizardCreatePbSo, self).default_get(cr, uid, fields, context=context)
		res = {}
		if not so_ids or len(so_ids) != 1:
			return res
		so_id, = so_ids
		if so_id:
			res.update(so_id=so_id)
			so = self.pool.get('sale.order').browse(cr, uid, so_id, context=context)
			linesData = []

			for l in so.order_line:
				for m in l.material_lines:
					mat = self._load_so_line(cr, uid, m)
					linesData.append(mat)
		
			res['lines'] = linesData
		return res


	def _load_so_line(self, cr, uid,line):
		print line,">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

		res = {
		'so_line_id': line.sale_order_line_id.id,
		'so_material_line_id': line.id,
		'product_id'		: line.product_id.id,
		'description'		: line.desc,
		'uom'				: line.uom.id,
		'qty'				: line.qty,
			}
		return res	
		# res = super(WizardCreatePbSo,self)._load_so_line(cr, uid,line)
		
		# print "aaaaaaaaaaaaaaaaaaaassssssssssssssssssssssssssssspppppppppppppppp"

class WizardCreatePbLineSo(osv.osv_memory):
	_inherit="wizard.create.pb.line"
	_columns={
		
		'so_material_line_id':fields.many2one('sale.order.material.line','Item Line',required=True),
	}
class detail_pb(osv.osv):
	_inherit="detail.pb"
	_columns={
		
		'sale_order_material_line_id':fields.many2one('sale.order.material.line','Item Line',required=True),
	}
		