import time
import netsvc
import openerp.exceptions
from openerp.exceptions import Warning
import decimal_precision as dp
import re
from tools.translate import _
from osv import fields, osv
from datetime import datetime, timedelta
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP, float_compare
import logging

class Purchase_Order_Line(osv.osv):
	_inherit = 'purchase.order.line'
	_columns = {
		'po_line_rev': fields.many2one('purchase.order.line', 'PO Line Revise'),
	}

Purchase_Order_Line()


class Purchase_Order(osv.osv):
	_inherit = 'purchase.order'

	_columns = {
		'rev_counter':fields.integer('Rev Counter'),
		'revise_histories': fields.one2many('purchase.order.revision', 'po_source', 'Purchase Order Revision'),
		'po_revision_id': fields.many2one('purchase.order.revision', 'Purchase Order Revision'),
	}

	_defaults ={
		'rev_counter':0,
	}


	def action_invoice_create(self, cr, uid, ids, context=None):
		po_revision=self.pool.get('purchase.order.revision')
		val = self.browse(cr, uid, ids, context={})[0]

		search_po_revision = po_revision.search(cr, uid, [('po_source', '=', ids)])
		if search_po_revision:
			state_revision=po_revision.browse(cr, uid, search_po_revision)[0]
			if state_revision.state != 'cancel':
				raise osv.except_osv(_('Warning!'),
				_('Purchase Order ' + val.name + ' Tidak Dapat Di Proses Karna Revisi'))

		res = super(Purchase_Order, self).action_invoice_create(cr, uid, ids, context=None)
		return res

	def wkf_confirm_order(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		res = super(Purchase_Order, self).wkf_confirm_order(cr, uid, ids, context=None)
		return True


	def proses_po_revision(self, cr, uid, ids, po_id_revision, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_picking=self.pool.get('stock.picking')
		stock_move=self.pool.get('stock.move')
		obj_po_revision=self.pool.get('purchase.order.revision')
		obj_po_line=self.pool.get('purchase.order.line')

		po_revision = obj_po_revision.browse(cr, uid, [po_id_revision])[0]
		po_id=po_revision.po_source.id

		new_picking = obj_picking.search(cr, uid, [('purchase_id', '=', ids),(('state', '=', 'assigned'))])
		n_picking = obj_picking.browse(cr, uid, new_picking)[0]
		if n_picking:
			search_picking = obj_picking.search(cr, uid, [('purchase_id', '=', po_id)])
			picking = obj_picking.browse(cr, uid, search_picking)
			for x in picking:
				if x.state == 'done':
					#  Update Stock Pickin Doc Ref 
					obj_picking.write(cr,uid,n_picking.id,{'cust_doc_ref':x.cust_doc_ref})

					partial_data = {}
					for line in x.move_lines:
						po_line = obj_po_line.search(cr, uid, [('po_line_rev', '=', line.purchase_line_id.id)])
						po_line_id=obj_po_line.browse(cr, uid, po_line)[0]

						mv = stock_move.search(cr, uid, [('purchase_line_id', '=', po_line_id.id)])
						move_id = stock_move.browse(cr, uid, mv)[0]

						partial_data['move%s' % (move_id.id)] = {
									'product_id': line.product_id.id,
									'product_qty': line.product_qty,
									'product_uom': line.product_uom.id,
									'prodlot_id': line.prodlot_id.id}

					picking_do = obj_picking.do_partial(cr,uid,[n_picking.id],partial_data,context={})
					id_done = picking_do.items()

					# Cancel Picking State Done Old
					self.cancel_picking_done(cr, uid, x.id)
				else:
					obj_picking.action_cancel(cr, uid, [x.id])
		return True

	def action_picking_create(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')
		obj_po_revision=self.pool.get('purchase.order.revision')
		
		res = super(Purchase_Order, self).action_picking_create(cr, uid, ids, context=None)

		if val.po_revision_id.id:
			self.proses_po_revision(cr, uid, ids, val.po_revision_id.id, context=None)

			# Cancel Purchase Order
			cancel_po = self.action_cancel(cr, uid, [val.po_revision_id.po_source.id], context=None)

			msg = _("Revision Version Confirmed @ " + val.name)
			obj_po.message_post(cr, uid, [val.po_revision_id.po_source.id], body=msg, context=context)

			if val.po_revision_id.po_source.state != 'cancel':
				self.cancel_purchase_order(cr, uid, [val.po_revision_id.po_source.id], context=None)

			# Done Purchase Order Revision
			obj_po_revision.write(cr,uid,val.po_revision_id.id,{'state':'done'})

		return res

	def cancel_purchase_order(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')
		obj_po_line=self.pool.get('purchase.order.line')
		po=obj_po.browse(cr, uid, ids)[0]
		for x in po.order_line:
			obj_po_line.write(cr,uid,x.id,{'state':'cancel'})

		obj_po.write(cr,uid,ids,{'state':'cancel'})
		return True

	def cancel_picking_done(self, cr, uid, ids, context=None):
		obj_picking=self.pool.get('stock.picking')
		stock_move=self.pool.get('stock.move')

		pick=obj_picking.browse(cr, uid, ids)
		for x in pick.move_lines:
			stock_move.write(cr,uid,x.id,{'state':'cancel'})

		obj_picking.write(cr,uid,ids,{'state':'cancel'})

		return True
		
Purchase_Order()


class Purchase_Order_Revision(osv.osv):
	_name = 'purchase.order.revision'

	_columns = {
		'rev_counter':fields.integer('Rev Counter', readonly=True, track_visibility='onchange'),
		'po_source': fields.many2one('purchase.order', 'Purchase Order', readonly=True, track_visibility='onchange'),
		'new_po': fields.many2one('purchase.order', 'New Version', readonly=True, track_visibility='onchange'),
		'reason':fields.text('Reason', readonly=True, track_visibility='onchange'),
		'state': fields.selection([
			('confirm', 'Confirmed'),
			('approved','Approved'),
			('to_revise','To Revise'),
			('done', 'Done'),
			('cancel', 'Cancel'),
		], 'Status', readonly=True, select=True, track_visibility='onchange'),
		'revise_w_new_no':fields.boolean(string='Revise New No', readonly=True, track_visibility='onchange'),
	}

	_inherit = ['mail.thread']

	_defaults = {
		'revise_w_new_no':False,
	}

	_rec_name = 'po_source'


	def po_revision_state_cancel(self, cr, uid, ids, context={}):
		res = self.write(cr,uid,ids,{'state':'cancel'},context=context)
		return res


	def po_revision_state_setconfirm(self, cr, uid, ids, context={}):
		res = self.write(cr,uid,ids,{'state':'confirm'},context=context)
		return res

	def po_revision_state_approve(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')

		msg = _("Purchase Order Revision Approved")
		obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)
		
		res = self.write(cr,uid,ids,{'state':'approved'},context=context)
		return res

	def po_revision_state_to_revise(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')

		msg = _("Approval to Revision Complete")
		obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)

		res = self.write(cr,uid,ids,{'state':'to_revise'},context=context)
		return res

	def po_revision_state_done(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')

		msg = _("Purchase Order Revision Done")
		obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)

		res = self.write(cr,uid,ids,{'state':'done'},context=context)
		return res

	def update_revise_w_new_no(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po=self.pool.get('purchase.order')

		msg = _("Purchase Order Revision Update New Po No")
		obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)

		res = self.write(cr,uid,ids,{'revise_w_new_no':True},context=context)
		return res

	def po_revise_cancel(self, cr, uid, ids, context={}):
		res = self.po_revision_state_cancel(cr, uid, ids, context=None)
		return res

	def check_group_purchase_manager(self, cr, uid, ids, context={}):
		#  Check User Groups Purchase Manager
		m  = self.pool.get('ir.model.data')
		id_group = m.get_object(cr, uid, 'purchase', 'group_purchase_manager').id
		user_group = self.pool.get('res.groups').browse(cr, uid, id_group)
		a = False
		for x in user_group.users:
			if x.id == uid:
				a = True

		if a == True:
			return True
		else:
			return False

	def check_group_purchase_chief(self, cr, uid, ids, context={}):
		#  Check User Groups Purchase Chief
		m  = self.pool.get('ir.model.data')
		id_group = m.get_object(cr, uid, 'sbm_po_revise', 'group_purchase_chief').id
		user_group = self.pool.get('res.groups').browse(cr, uid, id_group)
		a = False
		for x in user_group.users:
			print '============user chief=============',x.id
			if x.id == uid:
				a = True

		if a == True:
			return True
		else:
			return False


	def check_group_finance(self, cr, uid, ids, context={}):
		#  Jika dia Admin Invoice
		m  = self.pool.get('ir.model.data')
		id_group = m.get_object(cr, uid, 'base', 'module_category_accounting_and_finance').id
		user_group = self.pool.get('res.groups').browse(cr, uid, id_group)

		a = False
		for x in user_group.users:
			if x.id == uid:
				a = True

		if a == True:
			return True
		else:
			return False


	def po_revise_approve(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_invoice = self.pool.get('account.invoice')
		obj_po = self.pool.get('purchase.order')
		obj_bank_statment = self.pool.get('account.bank.statement')
		obj_bank_statment_line = self.pool.get('account.bank.statement.line')
		po_id = val.po_source.id
		
		#Cek Bank Statement 
		cek_po_bank = obj_bank_statment_line.search(cr, uid, [('po_id', '=', po_id)])
		data_bank_statment = obj_bank_statment_line.browse(cr, uid, cek_po_bank)

		#  Cek PO apakah sudah dibuatkan Invoice
		cr.execute("SELECT invoice_id FROM purchase_invoice_rel WHERE purchase_id = %s", [po_id])
		invoice = map(lambda x: x[0], cr.fetchall())

		if data_bank_statment == [] and invoice == []:
			self.po_revision_state_to_revise(cr, uid, ids, context={})
		else:
			self.po_revision_state_approve(cr, uid, ids, context={})
		
		if data_bank_statment:
			user_purchase_manager = self.check_group_purchase_manager(cr, uid, ids, context={})
			user_purchase_chief = self.check_group_purchase_chief(cr, uid, ids, context={})

			print '=======user_purchase_manager Bank Statement=========',user_purchase_manager
			print '========user_purchase_chief Bank Statement========',user_purchase_chief

			if user_purchase_manager == True or user_purchase_chief == True:
				user_finance = self.check_group_finance(cr, uid, ids, context={})

				if user_finance == False:
					raise osv.except_osv(('Warning..!!'), ('Akses Approve PO Revision Ada Pada Finance'))

			for n in data_bank_statment:
				self.update_revise_w_new_no(cr, uid, ids, context={})
					
				msg = _("Please Cancel Bank Statement " + str(n.statement_id.name) + " --> Waiting to Cancel Bank Statement " + str(n.statement_id.name))
				obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)

				# elif n.statement_id.state == 'draft':
				# 	# Jika Status Masih New / Draft, Maka harus langsung Cancel
				# 	obj_bank_statment.action_cancel(cr,uid,[n.statement_id.id])
		if invoice:
			user_purchase_manager = self.check_group_purchase_manager(cr, uid, ids, context={})
			user_purchase_chief = self.check_group_purchase_chief(cr, uid, ids, context={})

			print '=======user_purchase_manager Invoice=========',user_purchase_manager
			print '========user_purchase_chief Invoice========',user_purchase_chief

			if user_purchase_manager == True or user_purchase_chief == True:
				user_finance = self.check_group_finance(cr, uid, ids, context={})

				if user_finance == False:
					raise osv.except_osv(('Warning..!!'), ('Akses Approve PO Revision Ada Pada Finance'))	

			for x in obj_invoice.browse(cr, uid, invoice):
				if x.state == 'paid' or x.state == 'open':
					self.update_revise_w_new_no(cr, uid, ids, context={})

				msg = _("Waiting to Cancel Invoice " + str(x.kwitansi))
				obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)
				# elif x.state == 'draft':
				# 	# Jika Status Masih New / Draft, Maka harus langsung Cancel
				# 	obj_invoice.action_cancel(cr, uid, [x.id], context={})
		# return self.pool.get('warning').info(cr, uid, title='Export imformation', message="%s products Created, %s products Updated "%(str(prod_new),str(prod_update)))
		return True
			
	def po_revise_setconfirmed(self, cr, uid, ids, context=None):
		res = self.po_revision_state_setconfirm(cr, uid, ids, context=None)
		return res 


	def create_purchase_order(self, cr, uid, ids,fiscal_position_id=False, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_purchase = self.pool.get('purchase.order')
		obj_purchase_line = self.pool.get('purchase.order.line')
		obj_po_revision = self.pool.get('purchase.order.revision')
		account_fiscal_position = self.pool.get('account.fiscal.position')
		account_tax = self.pool.get('account.tax')

		po = obj_po_revision.browse(cr, uid, ids)[0]

		res = {};lines= []

		if val.revise_w_new_no == False:
			
			if po.po_source.name[-4:] == 'Rev'+str(val.rev_counter-1):
				seq = po.po_source.name[:-4] + 'Rev'+str(val.rev_counter)
			else:
				seq = po.po_source.name + '/Rev'+str(val.rev_counter)
		else:
			seq =int(time.time())

		po_id = obj_purchase.create(cr, uid, {
										'name':seq,
										'date_order': time.strftime("%Y-%m-%d"),
										'duedate':time.strftime("%Y-%m-%d"),
										'partner_id': po.po_source.partner_id.id,
										'jenis': po.po_source.jenis,
										'pricelist_id': po.po_source.pricelist_id.id,
										'location_id': 12,
										'origin':po.po_source.origin,
										'type_permintaan':po.po_source.type_permintaan,
										'term_of_payment':po.po_source.term_of_payment,
										'po_revision_id':val.id,
										'rev_counter':val.rev_counter
									   })
		noline=1
		for line in po.po_source.order_line:
			taxes = account_tax.browse(cr, uid, map(lambda line: line.id, line.product_id.supplier_taxes_id))
			fpos = fiscal_position_id and account_fiscal_position.browse(cr, uid, fiscal_position_id, context=context) or False
			taxes_ids = account_fiscal_position.map_tax(cr, uid, fpos, taxes)
			obj_purchase_line.create(cr, uid, {
										 'no':noline,
										 'date_planned': time.strftime("%Y-%m-%d"),
										 'order_id': po_id,
										 'product_id': line.product_id.id,
										 'variants':line.variants.id,
										 'name':line.name,
										 'part_number':line.part_number,
										 'line_pb_general_id': line.line_pb_general_id.id,
										 'product_qty': line.product_qty,
										 'product_uom': line.product_uom.id,
										 'price_unit': line.price_unit,
										 'discount_nominal':line.discount_nominal,
										 'discount':line.discount,
										 'note_line':'-',
										 'taxes_id': [(6,0,taxes_ids)],
										 'po_line_rev':line.id,
										 })
			noline=noline+1

		return po_id


	def create_po(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		obj_po = self.pool.get('purchase.order')
		obj_po_revision = self.pool.get('purchase.order.revision')
		po_id=self.create_purchase_order(cr, uid, ids, context=None)

		if val.new_po.id:
			raise osv.except_osv(('Warning..!!'), ('The New Purchase Order is Already in the Create..'))

		if po_id:
			obj_po_revision.write(cr,uid,ids,{'new_po':po_id})

			no_po = obj_po.browse(cr, uid, [po_id])[0]
			if val.revise_w_new_no == False:
				if val.po_source.name[-4:] == 'Rev'+str(val.rev_counter-1):
					name_seq = val.po_source.name[:-4] + 'Rev'+str(val.rev_counter)
				else:
					name_seq = val.po_source.name + '/Rev'+str(val.rev_counter)
					
				obj_po.write(cr,uid,po_id,{'name':name_seq})

			msg = _("Revision Version Created @ # " + no_po.name)
			obj_po.message_post(cr, uid, [val.po_source.id], body=msg, context=context)


		pool_data=self.pool.get("ir.model.data")
		action_model,action_id = pool_data.get_object_reference(cr, uid, 'purchase', "purchase_order_form")     
		action_pool = self.pool.get(action_model)
		res_id = action_model and action_id or False
		action = action_pool.read(cr, uid, action_id, context=context)
		action['name'] = 'purchase.order.form'
		action['view_type'] = 'form'
		action['view_mode'] = 'form'
		action['view_id'] = [res_id]
		action['res_model'] = 'purchase.order'
		action['type'] = 'ir.actions.act_window'
		action['target'] = 'current'
		action['res_id'] = po_id
		return action

Purchase_Order_Revision()

class ClassNamePOrevise(osv.osv):
	def action_po_to_revise(self,cr,uid,ids,context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		po_revision=self.pool.get('purchase.order.revision')

		search_po = po_revision.search(cr, uid, [('po_source', '=', val.id)])

		if search_po:
			state_po_revisi = po_revision.browse(cr, uid, search_po)[0]
			if state_po_revisi.state != 'cancel':
				raise osv.except_osv(('Warning..!!'), ('Purchase Order is Already in Revision..'))

		if context is None:
			context = {}
		
		dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'sbm_po_revise', 'wizard_po_revise_form')

		context.update({
			'active_model': self._name,
			'active_ids': ids,
			'active_id': len(ids) and ids[0] or False
		})
		return {
			'view_mode': 'form',
			'view_id': view_id,
			'view_type': 'form',
			'view_name':'wizard_po_revise_form',
			'res_model': 'wizard.po.revise',
			'type': 'ir.actions.act_window',
			'target': 'new',
			'context': context,
			'nodestroy': True,
		}

	_inherit = 'purchase.order'



class WizardPOrevise(osv.osv_memory):

	def default_get(self, cr, uid, fields, context=None):
		if context is None: context = {}
		po_ids = context.get('active_ids', [])
		active_model = context.get('active_model')
		res = super(WizardPOrevise, self).default_get(cr, uid, fields, context=context)
		if not po_ids or len(po_ids) != 1:
			return res
		po_id, = po_ids
		if po_id:
			res.update(po_source=po_id)
			po = self.pool.get('purchase.order').browse(cr, uid, po_id, context=context)		
		return res

	# def _set_message_unread(self, cr, uid, ids, context=None):
	# 	m  = self.pool.get('ir.model.data')
	# 	id_group = m.get_object(cr, uid, 'sbm_order_preparation', 'group_admin_ho').id
	# 	user_group = self.pool.get('res.groups').browse(cr, uid, id_group)
	# 	for x in user_group.users:
	# 		if x.id:
	# 			cr.execute('''
	# 				UPDATE mail_notification SET
	# 					read=false
	# 				WHERE
	# 					message_id IN (SELECT id from mail_message where res_id=any(%s) and model=%s) and
	# 					partner_id = %s
	# 			''', (ids, 'order.preparation', x.partner_id.id))
	# 	return True

	def _set_mail_notification(self, cr, uid, ids, partner_id, context=None):
		message = self.pool.get('mail.message')

		mail_message = message.search(cr, uid, [('res_id', '=',ids),('model', '=', 'purchase.order.revision')])
		mail_id = message.browse(cr, uid, mail_message)

		for x in mail_id:
			if x.parent_id.id == False:
				id_notif = self.pool.get('mail.notification').create(cr, uid, {
							'read': False,
							'message_id': x.id,
							'partner_id': partner_id,
						}, context=context)
		return True

	def _set_op_followers(self, cr, uid, ids, context=None):
		m  = self.pool.get('ir.model.data')
		id_group = m.get_object(cr, uid, 'account', 'group_account_manager').id
		user_group = self.pool.get('res.groups').browse(cr, uid, id_group)

		for x in user_group.users:
			# Create By Mail Notification Untuk finance Manager
			if x.partner_id.id:
				self._set_mail_notification(cr, uid, ids, x.partner_id.id, context=None)

		id_group_purchase_manager = m.get_object(cr, uid, 'purchase', 'group_purchase_manager').id
		user_group_purchase_manager = self.pool.get('res.groups').browse(cr, uid, id_group_purchase_manager)

		for y in user_group_purchase_manager.users:
			# Create By Mail Notification Untuk Purchase manager 
			if y.partner_id.id:
				self._set_mail_notification(cr, uid, ids, y.partner_id.id, context=None)


		# id_group_purchaseChief = m.get_object(cr, uid, 'sbm_po_revise', 'group_purchase_chief').id
		# user_group_purchaseChief = self.pool.get('res.groups').browse(cr, uid, id_group_purchaseChief)

		# for z in user_group_purchaseChief.users:
		# 	# Create By Mail Notification Untuk Purchase Cheif
		# 	if z.partner_id.id:
		# 		self._set_mail_notification(cr, uid, ids, z.partner_id.id, context=None)

		return True


	def request_po_revise(self,cr,uid,ids,context=None):
		data = self.browse(cr,uid,ids,context)[0]
		obj_po = self.pool.get('purchase.order')
		obj_po_revision = self.pool.get('purchase.order.revision')

		data_po=obj_po.browse(cr, uid, data.po_source.id)

		po = data.po_source.id
		counter =data_po.rev_counter+1

		# Update PO Rev Counter
		obj_po.write(cr,uid,po,{'rev_counter':counter})

		# Create Stock Picking 
		po_revision = obj_po_revision.create(cr, uid, {
					'rev_counter':counter,
					'po_source':po,
					'reason':data.reason,
					'state':'confirm'
					})

		msg = _("Ask for Revision with reason: " + data.reason + " Waiting Approval")
		obj_po.message_post(cr, uid, [po], body=msg, context=context)

		# Create Mail Message 
		self._set_op_followers(cr, uid, po_revision, context=None)

		pool_data=self.pool.get("ir.model.data")
		action_model,action_id = pool_data.get_object_reference(cr, uid, 'sbm_po_revise', "view_po_revise_form")     
		action_pool = self.pool.get(action_model)
		res_id = action_model and action_id or False
		action = action_pool.read(cr, uid, action_id, context=context)
		action['name'] = 'purchase.order.revision.form'
		action['view_type'] = 'form'
		action['view_mode'] = 'form'
		action['view_id'] = [res_id]
		action['res_model'] = 'purchase.order.revision'
		action['type'] = 'ir.actions.act_window'
		action['target'] = 'current'
		action['res_id'] = po_revision

		return action

	_name="wizard.po.revise"
	_description="Wizard PO revise"
	_columns = {
		'po_source':fields.many2one('purchase.order',string="Purchase Order",required=True),
		'reason':fields.text('Reason',required=True,help="Reason why item(s) want to be cancel"),
	}

	_rec_name="po_source"

WizardPOrevise()




class account_invoice(osv.osv):
	_inherit = "account.invoice"

	def action_cancel(self, cr, uid, ids, context=None):
		res =super(account_invoice,self).action_cancel(cr, uid, ids, context)
		val = self.browse(cr, uid, ids, context={})[0]
		obj_invoice = self.pool.get('account.invoice')
		obj_po = self.pool.get('purchase.order')
		obj_po_revision=self.pool.get('purchase.order.revision')
		obj_bank_statment = self.pool.get('account.bank.statement')
		obj_bank_statment_line = self.pool.get('account.bank.statement.line')

		# Cek ID PO
		cr.execute("SELECT purchase_id FROM purchase_invoice_rel WHERE invoice_id = %s", ids)
		po = map(lambda x: x[0], cr.fetchall())

		cek_po_rev = obj_po_revision.search(cr, uid, [('po_source', '=', po)])
		po_rev = obj_po_revision.browse(cr, uid, cek_po_rev)

		if po_rev:
			# Cek Keseluruhan Invoice apakah sudah di cancel
			cr.execute("SELECT invoice_id FROM purchase_invoice_rel WHERE purchase_id = %s", po)
			invoice = map(lambda x: x[0], cr.fetchall())


			status_invoice = True
			for x in obj_invoice.browse(cr, uid, invoice):
				if x.state != 'cancel':
					status_invoice= False

			cek_po_bank = obj_bank_statment_line.search(cr, uid, [('po_id', '=', po)])
			data_bank_statment = obj_bank_statment_line.browse(cr, uid, cek_po_bank)

			bank_state = True
			for y in data_bank_statment:
				if y.statement_id.state != 'cancel':
					bank_state = False

			if status_invoice == True and bank_state == True:
				self.update_po_revision(cr, uid, po, context={})

		return res

	def update_po_revision(self, cr, uid, ids, context=None):
		obj_po_revision=self.pool.get('purchase.order.revision')
		obj_po=self.pool.get('purchase.order')
		cek_po = obj_po_revision.search(cr, uid, [('po_source', '=', ids)])
		data_po = obj_po_revision.browse(cr, uid, cek_po)[0]
		if data_po.state == 'approved':

			msg = _("Approval to Revision Complete")
			obj_po.message_post(cr, uid, [data_po.po_source.id], body=msg, context=context)

			return obj_po_revision.write(cr,uid,data_po.id,{'state':'to_revise'},context=context)
		else:
			return False

account_invoice()


class account_bank_statement(osv.osv):
	_inherit = "account.bank.statement"


	def create(self, cr, uid, vals, context=None):
		po_revision=self.pool.get('purchase.order.revision')
		for lines in vals['line_ids']:
			if lines[2]:
				if lines[2]['po_id']:

					po = self.pool.get('purchase.order').browse(cr, uid, [lines[2]['po_id']])[0]

					search_po_revision = po_revision.search(cr, uid, [('po_source', '=', po.id)])
					if search_po_revision:
						state_revision=po_revision.browse(cr, uid, search_po_revision)[0]
						if state_revision.state != 'cancel':
							raise osv.except_osv(_('Warning!'),
							_('Purchase Order ' + po.name + ' Tidak Dapat Di Proses Karna Revisi'))

		return super(account_bank_statement, self).create(cr, uid, vals, context=context)

	def action_cancel(self, cr, uid, ids, context={}):
		val = self.browse(cr, uid, ids, context={})[0]
		self.write(cr,uid,ids,{'state':'cancel'},context=context)
		status_invoice =True
		status_bank=True
		for x in val.line_ids:
			if x.po_id:
				status_invoice = self.check_state_invoice(cr, uid, x.po_id, context={})
				status_bank=self.check_state_bank(cr, uid, x.po_id, context={})

				if status_invoice == True and status_bank == True:
					self.update_po_revision(cr, uid, x.po_id.id, context={})
		return True

	def check_state_bank(self, cr, uid, ids, context={}):
		obj_bank_statment=self.pool.get('account.bank.statement')
		obj_bank_statment_line=self.pool.get('account.bank.statement.line')

		cek_po = obj_bank_statment_line.search(cr, uid, [('po_id', '=', ids.id)])
		data_bank_line = obj_bank_statment_line.browse(cr, uid, cek_po)

		status =True
		for x in data_bank_line:
			if x.statement_id.state != 'cancel':
				status = False

		return status

	def check_state_invoice(self, cr, uid, ids, context={}):
		obj_po=self.pool.get('purchase.order')
		obj_invoice=self.pool.get('account.invoice')
		obj_po_revision=self.pool.get('purchase.order.revision')
		cr.execute("SELECT invoice_id FROM purchase_invoice_rel WHERE purchase_id = %s", [ids.id])
		invoice = map(lambda x: x[0], cr.fetchall())

		status =True
		for x in invoice:
			inv = obj_invoice.browse(cr, uid, x)
			if inv.state != 'cancel':
				status=False

		return status


	def update_po_revision(self, cr, uid, ids, context=None):
		obj_po_revision=self.pool.get('purchase.order.revision')
		obj_po=self.pool.get('purchase.order')

		cek_po = obj_po_revision.search(cr, uid, [('po_source', '=', ids)])
		data_po = obj_po_revision.browse(cr, uid, cek_po)[0]
		if data_po.state == 'approved':

			msg = _("Approval to Revision Complete")
			obj_po.message_post(cr, uid, [data_po.po_source.id], body=msg, context=context)
			return obj_po_revision.write(cr,uid,data_po.id,{'state':'to_revise'},context=context)
		else:
			return False

account_bank_statement()


class purchase_partial_invoice(osv.osv_memory):
	_inherit = "purchase.partial.invoice"


purchase_partial_invoice()


class merge_pickings(osv.osv_memory):
	_inherit = "merge.pickings"

	def check_is_po_revise(self, cr, uid, ids, picking_ids, context=None):
		pool_picking = self.pool.get('stock.picking')
		obj_po_revision=self.pool.get('purchase.order.revision')
		for x in picking_ids:
			pick =pool_picking.browse(cr,uid,x)
			if pick.type == 'in':
				search_po_revision = obj_po_revision.search(cr, uid, [('po_source', '=', pick.purchase_id.id)])
				if search_po_revision:
					state_revision=obj_po_revision.browse(cr, uid, search_po_revision)[0]
					if state_revision.state != 'cancel':
						raise osv.except_osv(_('Warning!'),
						_('Picking '+ pick.name +' dari PO ' + pick.purchase_id.name[:6] + ' Tidak Dapat Di Buat Invoice Karna Proses Revisi'))

		return True


	def merge_orders(self, cr, uid, ids, context={}):
		data = self.browse(cr, uid, ids, context=context)[0]
		picking_ids = [x.id for x in data['picking_ids']]
		self.check_is_po_revise(cr, uid, ids, picking_ids)

		res = super(merge_pickings, self).merge_orders(cr, uid, ids, context=None)
		return res

merge_pickings()


class purchase_partial_invoice(osv.osv_memory):
	_inherit = "purchase.partial.invoice"
	
	def default_get(self, cr, uid, fields, context=None):
		po_revision=self.pool.get('purchase.order.revision')

		res = super(purchase_partial_invoice,self).default_get(cr, uid, fields, context=context)
		active_id = context.get('active_id',False)
		
		search_po_revision = po_revision.search(cr, uid, [('po_source', '=', active_id)])
		if search_po_revision:
			state_po = po_revision.browse(cr, uid, search_po_revision)[0]
			if state_po.state <> 'cancel':
				raise osv.except_osv(_('Warning!'),
				_('Purchase Order Tidak Dapat Di Buat Invoice Karna Proses Revisi'))

		return res

purchase_partial_invoice()