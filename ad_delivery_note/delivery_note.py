from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
import time
import openerp.exceptions
from lxml import etree
from openerp import pooler
from openerp.osv import fields, osv
from openerp.tools.translate import _
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT, DATETIME_FORMATS_MAP, float_compare
import openerp.addons.decimal_precision as dp
from openerp import netsvc
from openerp.tools.float_utils import float_compare

import logging
_logger = logging.getLogger(__name__)

class sale_order(osv.osv):
	_inherit = "sale.order"
	_columns = {
		'internal_notes': fields.text('Internal Notes'),
	}

	def manual_invoice(self, cr, uid, ids, context=None):
		""" create invoices for the given sales orders (ids), and open the form
			view of one of the newly created invoices
		"""
		mod_obj = self.pool.get('ir.model.data')
		wf_service = netsvc.LocalService("workflow")

		# create invoices through the sales orders' workflow
		inv_ids0 = set(inv.id for sale in self.browse(cr, uid, ids, context) for inv in sale.invoice_ids)
		for id in ids:
			wf_service.trg_validate(uid, 'sale.order', id, 'manual_invoice', cr)
		inv_ids1 = set(inv.id for sale in self.browse(cr, uid, ids, context) for inv in sale.invoice_ids)
		
		
		# determine newly created invoices
		new_inv_ids = list(inv_ids1 - inv_ids0)

		if not new_inv_ids:
			new_inv_ids = [self.action_invoice_create(cr, uid, ids, context)]
			
		res = mod_obj.get_object_reference(cr, uid, 'account', 'invoice_form')
		res_id = res and res[1] or False,

		return {
			'name': _('Customer Invoices'),
			'view_type': 'form',
			'view_mode': 'form',
			'view_id': [res_id],
			'res_model': 'account.invoice',
			'context': "{'type':'out_invoice'}",
			'type': 'ir.actions.act_window',
			'nodestroy': True,
			'target': 'current',
			'res_id': new_inv_ids and new_inv_ids[0] or False,
		}
		
sale_order()


class stock_picking(osv.osv):
	def print_im_out(self,cr,uid,ids,context=None):
		searchConf = self.pool.get('ir.config_parameter').search(cr, uid, [('key', '=', 'base.print')], context=context)
		browseConf = self.pool.get('ir.config_parameter').browse(cr,uid,searchConf,context=context)[0]
		urlTo = str(browseConf.value)+"moves/print&id="+str(ids[0])+"&uid="+str(uid)
		
		
		return {
			'type'	: 'ir.actions.client',
			'target': 'new',
			'tag'	: 'print.int.move',
			'params': {
				# 'id'	: ids[0],
				'redir'	: urlTo,
				'uid':uid
			},
		}
	def _checkSetProduct(self, cr, uid, ids, field_name, arg, context):
		res = {}
		for id in ids:
			res[id]= 0;
		return res
	_name = 'stock.picking'
	_inherit = ["stock.picking","mail.thread"]
	_columns = {
		'note_id': fields.many2one('delivery.note','Delivery Note', select=True),
		'note': fields.text('Notes', states={'done':[('readonly', False)]}),
		# 'move_set_datas': fields.one2many('move.set.data', '', 'Note Lines', readonly=True, states={'draft': [('readonly', False)]}),
		'move_set_datas':fields.one2many('move.set.data','picking_id',string="Move Set"),
		'isset_set':fields.function(_checkSetProduct,store=True,method=True,string="Is Has Set",type="boolean"),
		'state': fields.selection([
			('draft', 'Draft'),
			('warehouse','Check Warehouse'),
			('settodraft','Set To Draft'),
			('cancel', 'Cancelled'),
			('auto', 'Waiting Another Operation'),
			('confirmed', 'Waiting Availability'),
			('assigned', 'Ready to Transfer'),
			('done', 'Transferred'),
			], 'Status', readonly=True, select=True, track_visibility='onchange', help="""
			* Draft: not confirmed yet and will not be scheduled until confirmed\n
			* Waiting Another Operation: waiting for another move to proceed before it becomes automatically available (e.g. in Make-To-Order flows)\n
			* Waiting Availability: still waiting for the availability of products\n
			* Ready to Transfer: products reserved, simply waiting for confirmation.\n
			* Transferred: has been processed, can't be modified or cancelled anymore\n
			* Cancelled: has been cancelled, can't be confirmed anymore"""
		),
	}
	_defaults={
		'isset_set':False,
	}
	def splitMoveLineSet(self,cr,uid,vals,context=None):
		getMoves  = vals.get('move_lines')
		getMoves2 = []
		moveSet = []
		move_set_data_obj = self.pool.get('move.set.data')
		# print "<BEFOREEEE",getMoves
		for move in getMoves :
			# print move,"<<<<<<<<<<<<<<<<<<<<<<<<<\\n"
			moveData = move[2]
			pQty = moveData['product_qty']
			
			# print moveData['product_id']
			product = self.pool.get('product.product').browse(cr,uid,moveData['product_id'])
			# print product
			isHasBOM = False
			if product.bom_ids:
				isHasBOM = True
				
				move_set_id = move_set_data_obj.create(cr,uid,{
					'product_id':int(moveData['product_id']),
					'product_qty':float(moveData['product_qty']),
					'product_uom':int(moveData['product_uom']),
					'location_id':int(moveData['location_id']),
					'location_dest_id':int(moveData['location_dest_id']),
					'type':moveData['type'],
					'no':float(moveData['no']),
					'desc':moveData['desc'],
					'picking_id':moveData['picking_id'] or False,

				})
				
				moveSet.append(move_set_id)
				for component in product.bom_ids[0].bom_lines:
					res = [0,False]
					bla = {}
					
					bla['product_id']       = component.product_id.id
					bla['product_qty']      = component.product_qty * pQty
					bla['product_uom']      = component.product_uom.id
					bla['location_id']      = moveData['location_id']
					bla['location_dest_id'] = moveData['location_dest_id']
					bla['type']             = moveData['type']
					bla['no']               = moveData['no']
					bla['name']             = "["+component.product.default_code+"] "+component.product_id.name
					bla['desc']             = "["+component.product.default_code+"] "+component.product_id.name
					bla['set_id']           = move_set_id
					bla['partner_id']		= moveData['partner_id']
					bla['product_uos']		= component.product_uom.id
					bla['product_uos_qty']	= component.product_qty * pQty
					
					res.append(bla)
					
					getMoves2.append(res)
				# getMoves.remove(move)
				# getMoves.remove()
				
			else:
				getMoves2.append(move)
		

		vals['move_lines'] = getMoves2

		# return False
		stock_p_id = super(stock_picking, self).create(cr, uid, vals, context)
		
		if stock_p_id:
			for move_set_line in moveSet:
				self.pool.get('move.set.data').write(cr,uid,move_set_line,{'picking_id':stock_p_id})
				
		return stock_p_id
		self.cleanSetProductMove(cr,uid,stock_p_id,context)
		

	def cleanSetProductMove(self,cr,uid,ids,context=None):
		pickings = self.browse(cr,uid,ids,context)
		setsIds = []
		moveObj = self.pool.get('stock.move')
		# print "CALLING CLENA SET PRODUCT MOVE"
		print ids
		for picking in pickings:
			# print pickings,"=============<"

			for move in picking.move_lines:
				# print move,"======================>"
				pSet = False
				pQty = move.product_qty
				# print "move aaaaa ",move
				if move.product_id.bom_ids:
					pSet = True
					# add move to move_set_data
					moveSetData = {
						'origin_move_id':move.id,
						'product_id':move.product_id.id,
						'product_qty':move.product_qty,
						'product_uom':move.product_uom.id,
						'type':move.type,
						'no':move.no,
						'desc':move.desc or move.name or False,
						'location_id':move.location_id.id,
						'location_dest_id':move.location_dest_id.id,
						'picking_id':move.picking_id.id,
						
					}
					
					move_set_id = self.pool.get('move.set.data').create(cr,uid,moveSetData)
					# add move id to list for delete in last
					setsIds.append(move.id)

					# create new move objects from bom component
					if move.product_id.bom_ids[0].bom_lines :
						# print "HAS BOMMMMMM"
						for component in move.product_id.bom_ids[0].bom_lines :
							bla = {}
							bla['product_id']       = component.product_id.id
							bla['product_qty']      = component.product_qty * pQty
							bla['product_uom']      = component.product_uom.id
							bla['location_id']      = move.location_id.id
							bla['location_dest_id'] = move.location_dest_id.id
							bla['type']             = move.type
							bla['no']               = move.no
							bla['name']				= "["+component.product_id.default_code+"] "+component.product_id.name
							bla['desc']             = "["+component.product_id.default_code+"] "+component.product_id.name
							bla['set_id']           = move_set_id
							bla['picking_id']		= picking.id
							bla['sale_line_id']		= move.sale_line_id.id
							bla['purchase_line_id']	= move.purchase_line_id.id or False
							bla['partner_id']		= move.partner_id.id
							bla['product_uos_qty']	= component.product_qty * pQty
							bla['product_uos']		= component.product_uom.id

							moveNew = self.pool.get('stock.move').create(cr,uid,bla,context)
							# print moveNew,"<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<,"
					else:
						raise osv.except_osv(_('Error!'), _('Please Define Bill Of Material Data First For ',move.product_id.name))
			# delete move where product is has BOM
			
			self.pool.get('stock.move').unlink(cr,uid,setsIds,context)



	def create(self, cr, uid, vals, context=None):

		getMoves  = vals.get('move_lines')
		# print "GET MOVESSSSSS======================",getMoves
		if getMoves:
			getMoves2 = []
			moveSet = []
			move_set_data_obj = self.pool.get('move.set.data')
			# print "<BEFOREEEE",getMoves,"MOVEEEE:"
			for move in getMoves :
				# print move,"<<<<<<<<<<<<<<<<<<<<<<<<<\\n"
				moveData = move[2]
				pQty = moveData['product_qty']
				
				# print moveData['product_id']
				product = self.pool.get('product.product').browse(cr,uid,moveData['product_id'])
				# print product
				isHasBOM = False
				if product.bom_ids:
					isHasBOM = True
					newMoveSet = {}
					newMoveSet = {
						'product_id':int(moveData['product_id']),
						'product_qty':float(moveData['product_qty']),
						'product_uom':int(moveData['product_uom']),
						'location_id':int(moveData['location_id']),
						'location_dest_id':int(moveData['location_dest_id']),
						'type':moveData['type'],
						'no':float(moveData['no']),
						'desc':moveData['desc'] or moveData['name'] or False,
					}
					if 'picking_id' in moveData:
						newMoveSet['picking_id'] = moveData['picking_id'] or False

					move_set_id = move_set_data_obj.create(cr,uid,newMoveSet)
					print move_set_id,'-------------------'
					moveSet.append(move_set_id)
					for component in product.bom_ids[0].bom_lines:
						res = [0,False]
						bla = {}
						# print component.product_id.name
						bla['product_id']       = component.product_id.id
						bla['product_qty']      = component.product_qty * pQty
						bla['product_uom']      = component.product_uom.id
						bla['location_id']      = moveData['location_id']
						bla['location_dest_id'] = moveData['location_dest_id']
						bla['type']             = moveData['type']
						bla['no']               = moveData['no']
						bla['name']             = "["+component.product_id.default_code+"] "+component.product_id.name
						bla['desc']             = component.product_id.name
						bla['set_id']           = move_set_id
						if 'purchase_line_id' in moveData:
							bla['purchase_line_id']	= moveData['purchase_line_id']
						bla['product_uos']		= component.product_uom.id
						bla['product_uos_qty']	= component.product_qty * pQty
						# print bla
						# print '=========================='
						res.append(bla)
						# print '==========================',res
						getMoves2.append(res)
					# getMoves.remove(move)
					# getMoves.remove()
					
				else:
					getMoves2.append(move)
			# print getMoves

			vals['move_lines'] = getMoves2

			# return False
			stock_p_id = super(stock_picking, self).create(cr, uid, vals, context)
			# print moveSet
			if stock_p_id:
				for move_set_line in moveSet:
					self.pool.get('move.set.data').write(cr,uid,move_set_line,{'picking_id':stock_p_id})
					# print stock_p_id,'=============='
			return stock_p_id
			# return False
			# raise osv.except_osv(_('No Customer Defined!'), _('Tes'))
		else:
			# IF NOT FROM MOVES
			# print "THISSSSSSS"
			stock_p_id =  super(stock_picking,self).create(cr,uid,vals,context)
			# print "STOCK P ID",stock_p_id
			return stock_p_id
			# return False
		# return super(stock_picking,self).create(cr,uid,vals,context)


	def draft_force_warehouse(self,cr,uid,ids,context=None):
		val = self.browse(cr, uid, ids)[0]
		
		for x in val.move_lines:
			product =self.pool.get('product.product').browse(cr, uid, x.product_id.id)
			product = x.product_id
			# pQty = x.product_qty

			isHasBOM = False
			# if product is SET / HAS A BOM MATERIALS
			if product.bom_ids:
				# print "<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< ADA BOM ",product.id
				isHasBOM = True
				line_bom = x.id
				# bom = product.bom_ids[0].bom_lines
				# LOOP EACH BOM
				# for component in product.bom_ids[0].bom_lines :
					# print ".....",component.product_id.name," ",component.product_qty," ",component.product_uom.name

			# CHECK PRODUCT AVAILABILITY
			print '>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>',product.default_code
			if product.not_stock == False:
				mm = ' ' + product.default_code + ' '
				stock = ' ' + str(product.qty_available) + ' '
				msg = 'Stock Product' + mm + 'Tidak Mencukupi.!\n'+ ' On Hand Qty '+ stock 

				# UNCOMMENT THIS FOR LIVE
				if x.product_qty > product.qty_available:
					raise openerp.exceptions.Warning(msg)
					return False
				# END UNCOMMENT FOR LIVE
		return self.write(cr,uid,ids,{'state':'warehouse'})
		# return False
	def draft_force_assign(self,cr,uid,ids,context=None):
		return self.write(cr,uid,ids,{'state':'confirmed'})

	def setdraft(self,cr,uid,ids,context=None):
		return self.write(cr,uid,ids,{'state':'draft'})



	def do_partial(self, cr, uid, ids, partial_datas, context=None):
		""" Makes partial picking and moves done.
		@param partial_datas : Dictionary containing details of partial picking
						  like partner_id, partner_id, delivery_date,
						  delivery moves with product_id, product_qty, uom
		@return: Dictionary of values
		"""

		print partial_datas
		
		if context is None:
			context = {}
		else:
			# chandra function for return picking
			active_id=context.get('active_id',ids)
			print "(((((((((((",active_id
			cekpicking = self.pool.get('stock.picking').browse(cr, uid, active_id, context=context)

			# update Delivery Note State Refunded
			active_picking = False
			if isinstance(cekpicking, list):
				x = cekpicking[0].name
				active_picking = cekpicking[0]
			else:
				x = cekpicking.name
				active_picking = cekpicking

			name_seq=x[-6:]

			# Cek apakah Note ID ada dan Picking Name Return atau tidak
			if active_picking.note_id.id:
				self.pool.get('delivery.note').write(cr, uid, active_picking.note_id.id, {'state':'refunded'}, context=context)
				
			# chandra function for return picking
			context = dict(context)
		res = {}
		move_obj = self.pool.get('stock.move')
		product_obj = self.pool.get('product.product')
		currency_obj = self.pool.get('res.currency')
		uom_obj = self.pool.get('product.uom')
		sequence_obj = self.pool.get('ir.sequence')
		wf_service = netsvc.LocalService("workflow")
		for pick in self.browse(cr, uid, ids, context=context):
			new_picking = None
			complete, too_many, too_few = [], [], []
			move_product_qty, prodlot_ids, product_avail, partial_qty, product_uoms = {}, {}, {}, {}, {}
			for move in pick.move_lines:
				if move.state in ('done', 'cancel'):
					continue
				partial_data = partial_datas.get('move%s'%(move.id), {})
				product_qty = partial_data.get('product_qty',0.0)
				pp = self.pool.get('product.product').browse(cr,uid,partial_data.get('product_id'),context=context)
				# raise osv.except_osv(_('Error'),_("AAAAA"+"|".join(partial_data)))
				if not pp:
					pp = move.product_id
				if not pp.active:
					raise osv.except_osv(_('Error'),_('Product '+pp.default_code+ " is not active in system.\r\nPlease activate it first."))
				# if(product_qty==0.0):
					# raise osv.except_osv(_("ERROR!"),_("Product Qty tidak boleh = 0"))
					# continue

				move_product_qty[move.id] = product_qty
				product_uom = partial_data.get('product_uom',False)
				product_price = partial_data.get('product_price',0.0)
				product_currency = partial_data.get('product_currency',False)
				prodlot_id = partial_data.get('prodlot_id')
				prodlot_ids[move.id] = prodlot_id
				product_uoms[move.id] = product_uom

				#_logger.error("Product Uom %s", product_uom)
				partial_qty[move.id] = uom_obj._compute_qty(cr, uid, product_uoms[move.id], product_qty, move.product_uom.id)

				#_logger.error("Checkk============================> %s", partial_qty)
				
				if move.product_qty == partial_qty[move.id]:
					complete.append(move)
				elif move.product_qty > partial_qty[move.id]:
					too_few.append(move)
				else:
					too_many.append(move)


				#_logger.error('Too Few %s',too_few)
				#_logger.error('Too Many %s',too_many)
				#_logger.error('Too complete %s',complete)
				# if(product_qty==0.0):
				# 	raise osv.except_osv(_("ERROR!"),_("Product Qty tidak boleh = 0"))
				# Average price computation
				if (pick.type == 'in') and (move.product_id.cost_method == 'average'):
					product = product_obj.browse(cr, uid, move.product_id.id)
					move_currency_id = move.company_id.currency_id.id
					context['currency_id'] = move_currency_id
					qty = uom_obj._compute_qty(cr, uid, product_uom, product_qty, product.uom_id.id)

					if product.id not in product_avail:
						# keep track of stock on hand including processed lines not yet marked as done
						product_avail[product.id] = product.qty_available

					if qty > 0:
						new_price = currency_obj.compute(cr, uid, product_currency,
								move_currency_id, product_price, round=False)
						new_price = uom_obj._compute_price(cr, uid, product_uom, new_price,
								product.uom_id.id)
						if product_avail[product.id] <= 0:
							product_avail[product.id] = 0
							new_std_price = new_price
						else:
							# Get the standard price
							amount_unit = product.price_get('standard_price', context=context)[product.id]
							new_std_price = ((amount_unit * product_avail[product.id])\
								+ (new_price * qty))/(product_avail[product.id] + qty)
						# Write the field according to price type field
						product_obj.write(cr, uid, [product.id], {'standard_price': new_std_price})

						# Record the values that were chosen in the wizard, so they can be
						# used for inventory valuation if real-time valuation is enabled.
						move_obj.write(cr, uid, [move.id],
								{'price_unit': product_price,
								 'price_currency_id': product_currency})

						product_avail[product.id] += qty



			for move in too_few:
				product_qty = move_product_qty[move.id]
				if not new_picking:
					new_picking_name = pick.name
					self.write(cr, uid, [pick.id], 
							   {'name': sequence_obj.get(cr, uid,
											'stock.picking.%s'%(pick.type)),
							   })
					new_picking = self.copy(cr, uid, pick.id,
							{
								'name': new_picking_name,
								'move_lines' : [],
								'state':'draft',
							})
					print 'NEW PICKINg', new_picking
				if product_qty != 0:
					defaults = {
							'product_qty' : product_qty,
							'product_uos_qty': product_qty, #TODO: put correct uos_qty
							'picking_id' : new_picking,
							'state': 'assigned',
							'move_dest_id': move.move_dest_id.id or False,
							'price_unit': move.price_unit,
							'product_uom': product_uoms[move.id]
					}
					prodlot_id = prodlot_ids[move.id]
					if prodlot_id:
						defaults.update(prodlot_id=prodlot_id)
					print "NEW MOVE OBJ COPY",defaults
					move_obj.copy(cr, uid, move.id, defaults)
				
				move_obj.write(cr, uid, [move.id],
						{
							'product_qty': move.product_qty - partial_qty[move.id],
							'product_uos_qty': move.product_qty - partial_qty[move.id], #TODO: put correct uos_qty
							'prodlot_id': False,
							'tracking_id': False,
						})
			

			if new_picking:
				move_obj.write(cr, uid, [c.id for c in complete], {'picking_id': new_picking})
				# print "======================="
			for move in complete:
				defaults = {'product_uom': product_uoms[move.id], 'product_qty': move_product_qty[move.id],'move_dest_id':move.move_dest_id.id or False}
				if prodlot_ids.get(move.id):
					defaults.update({'prodlot_id': prodlot_ids[move.id]})
				move_obj.write(cr, uid, [move.id], defaults)
			for move in too_many:
				product_qty = move_product_qty[move.id]
				defaults = {
					'product_qty' : product_qty,
					'product_uos_qty': product_qty, #TODO: put correct uos_qty
					'product_uom': product_uoms[move.id],
					'move_dest_id': move.move_dest_id.id or False,
				}
				prodlot_id = prodlot_ids.get(move.id)
				if prodlot_ids.get(move.id):
					defaults.update(prodlot_id=prodlot_id)
				if new_picking:
					defaults.update(picking_id=new_picking)
				move_obj.write(cr, uid, [move.id], defaults)


			# raise osv.except_osv(_("TEST"),_("TEST"))

			# At first we confirm the new picking (if necessary)
			# new_picking indicates that shipment is partial
			if new_picking:
				wf_service.trg_validate(uid, 'stock.picking', new_picking, 'button_confirm', cr)
				# Then we finish the good picking
				self.write(cr, uid, [pick.id], {'backorder_id': new_picking}) # write new partial object set backorder_id = new_picking
				self.action_move(cr, uid, [new_picking], context=context)
				wf_service.trg_validate(uid, 'stock.picking', new_picking, 'button_done', cr)
				wf_service.trg_write(uid, 'stock.picking', pick.id, cr)
				delivered_pack_id = new_picking
				back_order_name = self.browse(cr, uid, delivered_pack_id, context=context).name
				self.message_post(cr, uid, new_picking, body=_("Back order <em>%s</em> has been <b>created</b>.") % (back_order_name), context=context)
			else:
				self.action_move(cr, uid, [pick.id], context=context)
				wf_service.trg_validate(uid, 'stock.picking', pick.id, 'button_done', cr)
				self.write(cr, uid, [pick.id], {'state': 'done'})
				delivered_pack_id = pick.id

			delivered_pack = self.browse(cr, uid, delivered_pack_id, context=context)
			res[pick.id] = {'delivered_picking': delivered_pack.id or False}
			
			# raise osv.except_osv(_('Error'),_('ERROR'))
		# #_logger.error("RESSSSSSSSS do_partial() = > %s",res)

		return res



stock_picking()

class PurchaseOrder(osv.osv):
	_inherit = "purchase.order"
	# def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, context=None):
 #        return {
 #            'name': order_line.name or '',
 #            'product_id': order_line.product_id.id,
 #            'product_qty': order_line.product_qty,
 #            'product_uos_qty': order_line.product_qty,
 #            'product_uom': order_line.product_uom.id,
 #            'product_uos': order_line.product_uom.id,
 #            'date': self.date_to_datetime(cr, uid, order.date_order, context),
 #            'date_expected': self.date_to_datetime(cr, uid, order_line.date_planned, context),
 #            'location_id': order.partner_id.property_stock_supplier.id,
 #            'location_dest_id': order.location_id.id,
 #            'picking_id': picking_id,
 #            'partner_id': order.dest_address_id.id or order.partner_id.id,
 #            'move_dest_id': order_line.move_dest_id.id,
 #            'state': 'draft',
 #            'type':'in',
 #            'purchase_line_id': order_line.id,
 #            'company_id': order.company_id.id,
 #            'price_unit': order_line.price_unit
 #        }
	def _create_pickings(self, cr, uid, order, order_lines, picking_id=False, context=None):
		"""Creates pickings and appropriate stock moves for given order lines, then
		confirms the moves, makes them available, and confirms the picking.

		If ``picking_id`` is provided, the stock moves will be added to it, otherwise
		a standard outgoing picking will be created to wrap the stock moves, as returned
		by :meth:`~._prepare_order_picking`.

		Modules that wish to customize the procurements or partition the stock moves over
		multiple stock pickings may override this method and call ``super()`` with
		different subsets of ``order_lines`` and/or preset ``picking_id`` values.

		:param browse_record order: purchase order to which the order lines belong
		:param list(browse_record) order_lines: purchase order line records for which picking
												and moves should be created.
		:param int picking_id: optional ID of a stock picking to which the created stock moves
							   will be added. A new picking will be created if omitted.
		:return: list of IDs of pickings used/created for the given order lines (usually just one)
		"""
		if not picking_id:
			picking_id = self.pool.get('stock.picking').create(cr, uid, self._prepare_order_picking(cr, uid, order, context=context))
		todo_moves = []
		stock_move = self.pool.get('stock.move')
		wf_service = netsvc.LocalService("workflow")
		for order_line in order_lines:
			if not order_line.product_id:
				continue
			if order_line.product_id.type in ('product', 'consu'):
				if order_line.product_id.bom_ids:
					if order_line.product_id.bom_ids[0].bom_lines:
						for bom in order_line.product_id.bom_ids[0].bom_lines:
							moveBom = {
								'name': bom.product_id.name_template or order_line.name or '',
								'product_id': bom.product_id.id,
								'product_qty': order_line.product_qty,
								'product_uos_qty': order_line.product_qty*bom.product_qty,
								'product_uom': bom.product_uom.id,
								'product_uos': bom.product_uom.id,
								'date': self.date_to_datetime(cr, uid, order.date_order, context),
								'date_expected': self.date_to_datetime(cr, uid, order_line.date_planned, context),
								'location_id': order.partner_id.property_stock_supplier.id,
								'location_dest_id': order.location_id.id,
								'picking_id': picking_id,
								'partner_id': order.dest_address_id.id or order.partner_id.id,
								'move_dest_id': order_line.move_dest_id.id,
								'state': 'draft',
								'type':'in',
								'purchase_line_id': order_line.id,
								'company_id': order.company_id.id,
								'price_unit': order_line.price_unit
							}
							move = stock_move.create(cr,uid,moveBom)
							todo_moves.append(move)

				else:
					move = stock_move.create(cr, uid, self._prepare_order_line_move(cr, uid, order, order_line, picking_id, context=context))
					if order_line.move_dest_id:
						order_line.move_dest_id.write({'location_id': order.location_id.id})
					todo_moves.append(move)
		stock_move.action_confirm(cr, uid, todo_moves)
		stock_move.force_assign(cr, uid, todo_moves)
		wf_service.trg_validate(uid, 'stock.picking', picking_id, 'button_confirm', cr)
		return [picking_id]
	



class move_set_data(osv.osv):
	_name = "move.set.data"
	_description = "Move Set Data"
	_rec_name = "origin_move_id"
	_columns = {

		'origin_move_id'    :   fields.integer('Origin Move ID',required=False), 
		'product_id'        :   fields.many2one('product.product',required=True,string="Product"),
		'product_qty'       :   fields.float('Quantity',required=True),
		'product_uom'       :   fields.many2one('product.uom',string="UOM"),
		'location_id'       :   fields.many2one('stock.location', 'Source Location'),
		'location_dest_id'  :   fields.many2one('stock.location', 'Destination Location'),
		'type'              :   fields.char('type'),
		'no'                :   fields.integer('No'),
		'desc'              :   fields.text('Description'),
		'picking_id'        :   fields.many2one('stock.picking',string="Picking",ondelete="cascade"),
	}
	

class stock_picking_out(osv.osv):

	_inherit = "stock.picking.out"
	_columns = {
		'note_id': fields.many2one('delivery.note','Delivery Note', select=True)
	}
	
stock_picking_out()


class sale_order_line(osv.osv):
	
	_inherit = 'sale.order.line'

	_columns = {
		'product_onhand': fields.float('On Hand', digits_compute= dp.get_precision('Product UoS'), readonly=True, states={'draft': [('readonly', False)]}),
		'product_future': fields.float('Available', digits_compute= dp.get_precision('Product UoS'), readonly=True, states={'draft': [('readonly', False)]}),
		'product_uom': fields.many2one('product.uom', 'Unit of Measure ', required=True, readonly=True, states={'draft': [('readonly', False)]}),
		'product_uos': fields.many2one('product.uom', 'Product UoS'),
		'product_uom_qty': fields.float('Quantity', digits_compute= dp.get_precision('Product UoS'), required=True, readonly=True, states={'draft': [('readonly', False)]}),
	}

	_defaults = {
		'sequence': 0,
	}

	def product_uom_change_new(self, cr, uid, ids, product, product_uom, context=None):
		if product:
			product_id =self.pool.get('product.product').browse(cr,uid,product)
			if product_id.categ_id.id == 12:
				uom=product_uom
			else:
				uom=product_id.uom_id.id
		else:
			uom=1
		return {'value':{'product_uom':uom}}


	def product_id_change(self, cr, uid, ids, pricelist, product, qty=0, uom=False, qty_uos=0, uos=False, name='', partner_id=False, lang=False, update_tax=True, date_order=False, packaging=False, fiscal_position=False, flag=False, context=None):
		
		context = context or {}
		lang = lang or context.get('lang',False)
		if not  partner_id:
			raise osv.except_osv(_('No Customer Defined!'), _('Before choosing a product,\n select a customer in the sales form.'))
		warning = {}
		product_uom_obj = self.pool.get('product.uom')
		partner_obj = self.pool.get('res.partner')
		product_obj = self.pool.get('product.product')
		context = {'lang': lang, 'partner_id': partner_id}
		if partner_id:
			lang = partner_obj.browse(cr, uid, partner_id).lang
		context_partner = {'lang': lang, 'partner_id': partner_id}
		if not product:
			return {'value': {'th_weight': 0,
				'product_uos_qty': qty}, 'domain': {'product_uom': [],
				   'product_uos': []}}
		if not date_order:
			date_order = time.strftime(DEFAULT_SERVER_DATE_FORMAT)

		result = {}
		warning_msgs = ''
		product_obj = product_obj.browse(cr, uid, product, context=context_partner)
		result['product_uom'] = product_obj.uom_id.id

		uom2 = False
		if uom:
			uom2 = product_uom_obj.browse(cr, uid, uom)
			if product_obj.uom_id.category_id.id != uom2.category_id.id:
				uom = False
		if uos:
			if product_obj.uos_id:
				uos2 = product_uom_obj.browse(cr, uid, uos)
				if product_obj.uos_id.category_id.id != uos2.category_id.id:
					uos = False
			else:
				uos = False
		fpos = fiscal_position and self.pool.get('account.fiscal.position').browse(cr, uid, fiscal_position) or False
		if update_tax: #The quantity only have changed
			result['tax_id'] = self.pool.get('account.fiscal.position').map_tax(cr, uid, fpos, product_obj.taxes_id)

		tambah = ''
		if product_obj.description:
			tambah = '\n'+product_obj.description
		if not flag:
			result['name'] = '[' + product_obj.default_code + '] ' + product_obj.name_template+tambah #self.pool.get('product.product').name_get(cr, uid, [product_obj.id], context=context_partner)[0][1]+tambah
			if product_obj.description_sale:
				result['name'] += '\n'+product_obj.description_sale+tambah
		domain = {}
		if (not uom) and (not uos):
			result['product_uom'] = product_obj.uom_id.id
			if product_obj.uos_id:
				result['product_uos'] = product_obj.uos_id.id
				result['product_uos_qty'] = qty * product_obj.uos_coeff
				uos_category_id = product_obj.uos_id.category_id.id
			else:
				result['product_uos'] = False
				result['product_uos_qty'] = qty
				uos_category_id = False
			result['th_weight'] = qty * product_obj.weight
			domain = {'product_uom':
						[('category_id', '=', product_obj.uom_id.category_id.id)],
						'product_uos':
						[('category_id', '=', uos_category_id)]}
		elif uos and not uom: # only happens if uom is False
			result['product_uom'] = product_obj.uom_id and product_obj.uom_id.id
			result['product_uom_qty'] = qty_uos / product_obj.uos_coeff
			result['th_weight'] = result['product_uom_qty'] * product_obj.weight
		elif uom: # whether uos is set or not
			default_uom = product_obj.uom_id and product_obj.uom_id.id
			q = product_uom_obj._compute_qty(cr, uid, uom, qty, default_uom)
			if product_obj.uos_id:
				result['product_uos'] = product_obj.uos_id.id
				result['product_uos_qty'] = qty * product_obj.uos_coeff
			else:
				result['product_uos'] = False
				result['product_uos_qty'] = qty
			result['th_weight'] = q * product_obj.weight        # Round the quantity up

		if not uom2:
			uom2 = product_obj.uom_id
		# get unit price
		
		# if not pricelist:
		#     warn_msg = _('You have to select a pricelist or a customer in the sales form !\n'
		#             'Please set one before choosing a product.')
		#     warning_msgs += _("No Pricelist ! : ") + warn_msg +"\n\n"
		# else:
		#     price = self.pool.get('product.pricelist').price_get(cr, uid, [pricelist],
		#             product, qty or 1.0, partner_id, {
		#                 'uom': uom or result.get('product_uom'),
		#                 'date': date_order,
		#                 })[pricelist]
		#     if price is False:
		#         warn_msg = _("Cannot find a pricelist line matching this product and quantity.\n"
		#                 "You have to change either the product, the quantity or the pricelist.")

		#         warning_msgs += _("No valid pricelist line found ! :") + warn_msg +"\n\n"
		#     else:
		#         result.update({'price_unit': price})
		# if warning_msgs:
		#     warning = {
		#                'title': _('Configuration Error!'),
		#                'message' : warning_msgs
		#             }

		# SCRIPT PROTECT STOCK AVAILABEL SALES ORDER LINE
		if product_obj.not_stock == False:
			if qty > product_obj.virtual_available:
				warning_msgs += _("Not enough stock Available")
				protect = {
						'title':_('Protect Stock Product !'),
						'message': warning_msgs
					}
				# return {'value':{'product_uom_qty':0,'product_uos_qty':0} , 'warning':protect}
		result['product_onhand'] = product_obj.qty_available
		result['product_future'] = product_obj.virtual_available
		
		
		return {'value': result, 'domain': domain, 'warning': warning}

class product_template(osv.osv):
	_inherit = ["product.template","mail.thread"]
	_name = "product.template"
	_columns = {
		'categ_id': fields.many2one('product.category','Category', required=True,track_visibility='onchange'),
	}


product_template()

class product_product(osv.osv):
	_inherit = ["product.product","mail.thread"]
	_name = "product.product"
	_columns = {
		'create_date': fields.datetime('Create Date'),
		'batch_code':fields.char('Batch No', size=64),
		'expired_date' : fields.date('Expired Date'),
		'partner_code':fields.char('Partner Code', size=64),
		'partner_desc' : fields.char('Partner Description', size=254),
		'default_code' : fields.char('Part Number', size=64, select=True,track_visibility='onchange'),
		'active': fields.boolean('Active', help="If unchecked, it will allow you to hide the product without removing it.", track_visibility='onchange'),
		'name_template': fields.related('product_tmpl_id', 'name', string="Template Name", type='char', size=128, store=True, select=True,track_visibility='onchange'),
	}
	_track = {
		'name_template':{
			
		},
	}

	_order = "create_date desc"

	_sql_constraints = [
		('default_code_unique', 'unique (default_code)', 'The Part Number must be unique !'),

		('name_template_unique', 'unique (name_template)', 'The Part Name must be unique !')
	]
	
product_product()


class procurement_order(osv.osv):
	_inherit = "procurement.order"
	
	def action_confirm(self, cr, uid, ids, context=None):
		""" Confirms procurement and writes exception message if any.
		@return: True
		"""
		move_obj = self.pool.get('stock.move')
		for procurement in self.browse(cr, uid, ids, context=context):
			if procurement.product_qty <= 0.00:
				pass
				#raise osv.except_osv(_('Data Insufficient!'),
				#    _('Please check the quantity in procurement order(s) for the product "%s", it should not be 0 or less!' % procurement.product_id.name))
			if procurement.product_id.type in ('product', 'consu'):
				if not procurement.move_id:
					source = procurement.location_id.id
					if procurement.procure_method == 'make_to_order':
						source = procurement.product_id.property_stock_procurement.id
					id = move_obj.create(cr, uid, {
						'name': procurement.name,
						'location_id': source,
						'location_dest_id': procurement.location_id.id,
						'product_id': procurement.product_id.id,
						'product_qty': procurement.product_qty,
						'product_uom': procurement.product_uom.id,
						'date_expected': procurement.date_planned,
						'state': 'draft',
						'company_id': procurement.company_id.id,
						'auto_validate': True,
					})
					move_obj.action_confirm(cr, uid, [id], context=context)
					self.write(cr, uid, [procurement.id], {'move_id': id, 'close_move': 1})
		self.write(cr, uid, ids, {'state': 'confirmed', 'message': ''})
		return True

	
procurement_order()

class delivery_note(osv.osv):
	def print_dn_out(self,cr,uid,ids,context=None):
		searchConf = self.pool.get('ir.config_parameter').search(cr, uid, [('key', '=', 'base.print')], context=context)
		browseConf = self.pool.get('ir.config_parameter').browse(cr,uid,searchConf,context=context)[0]
		urlTo = str(browseConf.value)+"delivery-note/print&id="+str(ids[0])+"&uid="+str(uid)
		return {
			'type'	: 'ir.actions.client',
			'target': 'new',
			'tag'	: 'print.int.move',
			'params': {
				'redir'	: urlTo,
				'uid':uid
			},
		}
	def print_pack_list(self,cr,uid,ids,context=None):
		searchConf = self.pool.get('ir.config_parameter').search(cr, uid, [('key', '=', 'base.print')], context=context)
		browseConf = self.pool.get('ir.config_parameter').browse(cr,uid,searchConf,context=context)[0]
		urlTo = str(browseConf.value)+"delivery-note/print-pack&id="+str(ids[0])+"&uid="+str(uid)
		
		
		return {
			'type'	: 'ir.actions.client',
			'target': 'new',
			'tag'	: 'print.int.move',
			'params': {
				'redir'	: urlTo,
				'uid':uid
			},
		}

	_name = "delivery.note"

	_columns = {
		'name': fields.char('Delivery Note', required=True, size=64, readonly=True, states={'draft': [('readonly', False)]}),
		'prepare_id': fields.many2one('order.preparation', 'Order Packaging', domain=[('state', 'in', ['done'])], required=False, readonly=True, states={'draft': [('readonly', False)]}),
		'tanggal' : fields.date('Delivery Date',track_visibility='onchange'),
		'state': fields.selection([('draft', 'Draft'), ('approve', 'Approved'), ('done', 'Done'), ('cancel', 'Cancel'), ('torefund', 'To Refund'), ('refunded', 'Refunded')], 'State', readonly=True,track_visibility='onchange'),
		'note_lines': fields.one2many('delivery.note.line', 'note_id', 'Note Lines', readonly=True, states={'draft': [('readonly', False)]}),
		'poc': fields.char('Customer Reference', size=64,track_visibility='onchange'),
		'partner_id': fields.many2one('res.partner', 'Customer', domain=[('customer','=', True)], readonly=True, states={'draft': [('readonly', False)]}),
		'partner_shipping_id': fields.many2one('res.partner', 'Delivery Address', domain=[('customer','=', True)], readonly=True, states={'draft': [('readonly', False)]},track_visibility='onchange'),
		'write_date': fields.datetime('Date Modified', readonly=True),
		'write_uid':  fields.many2one('res.users', 'Last Modification User', readonly=True),
		'create_date': fields.datetime('Date Created', readonly=True),
		'create_uid':  fields.many2one('res.users', 'Creator', readonly=True),
		'packing_lines': fields.one2many('packing.list.line', 'note_id', 'Packing List'),
		'note': fields.text('Notes'),
		'terms':fields.text('Terms & Condition'),
		'attn':fields.many2one('res.partner',string="Attention"),
		'refund_id':fields.many2one('stock.picking',string="Refund No", domain=[('type','=', 'in')], readonly=True),
		'note_return_ids': fields.many2many('stock.picking','delivery_note_return','delivery_note_id',string="Note Return",readonly=True),
		'note_return_ids_proses': fields.many2many('stock.picking.in','delivery_note_return','delivery_note_id',string="Note Return",readonly=True,states={'torefund': [('readonly', False)]}),
	}
	_defaults = {
		'name': '/',
		'state': 'draft', 
	}
	# to add mail thread in footer
	_inherit = ['mail.thread']
	
	 
	_order = "name desc"

	def action_process(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids)[0]
		if context is None:
			context = {}
		"""Open the partial picking wizard"""
		context.update({
			'active_model': 'stock.picking',
			'active_ids': [val.refund_id.id],
			'active_id': len([val.refund_id.id]) and [val.refund_id.id][0] or False
		})
		
		return {
			'view_type': 'form',
			'view_mode': 'form',
			'res_model': 'stock.partial.picking',
			'type': 'ir.actions.act_window',
			'target': 'new',
			'context': context,
			'nodestroy': True,
		}

	def print_deliveryA4(self, cr, uid, ids, context=None):
		data = {}
		val = self.browse(cr, uid, ids)[0]
		data['form'] = {}
		data['ids'] = context.get('active_ids',[])
		data['form']['data'] = self.read(cr, uid, ids)[0]
		
		data['form']['data']['street'] = str(val.partner_shipping_id.street)
		data['form']['data']['jalan'] = str(val.partner_shipping_id.street2)
		data['form']['data']['phone'] = str(val.partner_shipping_id.phone)
		
		qty = ''
		product_name = ''
		product_code = ''
		for x in val.note_lines:
			qty = qty + str(x.product_qty) + ' ' + x.product_uom.name + '\n\n'
			product_name = product_name + x.name + '\n\n'
			product_code = product_code + x.product_id.code + '\n\n'
		
		data['form']['data']['qty'] = qty
		data['form']['data']['product_name'] = product_name
		data['form']['data']['product_code'] = product_code
			  
		return {
				'type': 'ir.actions.report.xml',
				'report_name': 'delivery.note.A4',
				'datas': data,
				'nodestroy':True
		}
	
	 
	# def create(self, cr, uid, vals, context=None):
	# 	# validate dn input
		
	# 	prepareExists = self.search(cr,uid,[('prepare_id','=',vals['prepare_id']),('state','not in',['cancel'])])
		
	# 	if prepareExists and vals['special']==False:
	# 		no = ""
	# 		for nt in self.browse(cr,uid,prepareExists,context):
	# 			no += "["+nt.name+"]\n"
	# 		raise osv.except_osv(_("Error!!!"),_("Deliver Note ref to requested DO NO is Exist On NO "+no))


	# 	if vals['special']==True:
	# 		rom = [0, 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
	# 		# saleid = self.pool.get('order.preparation').browse(cr, uid, vals['prepare_id']).sale_id.id
	# 		usa = 'SPC'
	# 		val = self.pool.get('ir.sequence').get(cr, uid, 'delivery.note').split('/')
	# 		use = str(self.pool.get('res.users').browse(cr, uid, uid).initial)
	# 		vals['name'] =time.strftime('%y')+ val[-1]+'C/SBM-ADM/'+usa+'-'+use+'/'+rom[int(val[2])]+'/'+val[1]
	# 		return super(delivery_note, self).create(cr, uid, vals, context=context)
	# 	else:    
	# 		# ex: 000001C/SBM-ADM/JH-NR/X/13
	# 		rom = [0, 'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII']
	# 		saleid = self.pool.get('order.preparation').browse(cr, uid, vals['prepare_id']).sale_id.id
	# 		usa = str(self.pool.get('sale.order').browse(cr, uid, saleid).user_id.initial)
	# 		val = self.pool.get('ir.sequence').get(cr, uid, 'delivery.note').split('/')
	# 		use = str(self.pool.get('res.users').browse(cr, uid, uid).initial)
	# 		vals['name'] =time.strftime('%y')+ val[-1]+'C/SBM-ADM/'+usa+'-'+use+'/'+rom[int(val[2])]+'/'+val[1]
	# 		return super(delivery_note, self).create(cr, uid, vals, context=context)
			
	def package_draft(self, cr, uid, ids, context=None):
		self.write(cr, uid, ids, {'state': 'draft'})
		return True                               
	
	def package_cancel(self, cr, uid, ids, context=None):
		self.write(cr, uid, ids, {'state': 'cancel'})
		return True                                  
		 
	def package_confirm(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]

		if val.prepare_id.sale_id.state == 'cancel' or val.prepare_id.sale_id.state == 'draft':
			raise osv.except_osv(_('Error'),_('Can\'t Change Document State, Please make sure Sale Order has been confirmed'))


		for x in val.note_lines:
			if x.product_qty <= 0:
				raise osv.except_osv(('Perhatian !'), ('Quantity product harus lebih besar dari 0 !'))
		self.write(cr, uid, ids, {'state': 'approve'})
		return True
		 
	def unlink(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		if val.state != 'draft':
			raise osv.except_osv(('Invalid action !'), ('Cannot delete a delivery note which is in state \'%s\'!') % (val.state,))
		return super(delivery_note, self).unlink(cr, uid, ids, context=context)
		  
	def prepare_change(self, cr, uid, ids, pre):
		if pre :
			res = {}; line = []
			data = self.pool.get('order.preparation').browse(cr, uid, pre)
			dnid = self.pool.get('delivery.note').search(cr, uid, [('prepare_id', '=', pre), ('state', '=', 'done')])
			for x in data.prepare_lines:
				qty = x.product_qty 
				if dnid:
					dnlid = self.pool.get('delivery.note.line').search(cr, uid, [('note_id', 'in', tuple(dnid)), ('product_id', '=', x.product_id.id)])
					if dnlid:
						dnldt = self.pool.get('delivery.note.line').browse(cr, uid, dnlid)
						qty -= sum([i.product_qty for i in dnldt])
				line.append({
							 'no': x.no,
							 'product_id' : x.product_id.id,
							 'product_qty': qty,
							 'product_uom': x.product_uom.id,
							 'name': x.name,
							 'op_line_id':x.id
							 })
			 
			res['note_lines'] = line
			res['poc'] = data.sale_id.client_order_ref
			res['tanggal'] = data.duedate
			res['partner_id'] = data.sale_id.partner_id.id
			res['partner_shipping_id'] = data.sale_id.partner_shipping_id.id
			res['attn'] = data.sale_id.attention.id
			
			return  {'value': res}

	def return_product(self, cr, uid, ids, context=None):
		res = {}
		val = self.browse(cr, uid, ids)[0]
		if val.prepare_id.sale_id.state == 'cancel' or val.prepare_id.sale_id.state == 'draft':
			raise osv.except_osv(_('Error'),_('Can\'t Processed Document, Please make sure Sale Order has been confirmed'))
		dummy, view_id = self.pool.get('ir.model.data').get_object_reference(cr, uid, 'stock', 'view_stock_return_picking_form')
		res = {
			'name':'Return Shipment',
			'view_mode': 'form',
			'view_id': view_id,
			'view_type': 'form',
			'view_name':'stock.stock_return_picking_memory',
			'res_model': 'stock.return.picking.memory',
			'type': 'ir.actions.act_window',
			'target': 'new',
			'res_id':val.prepare_id.picking_id.id,
			'domain': "[('id','=',"+str(val.prepare_id.picking_id.id)+")]",
			'key2':'client_action_multi',
			'multi':"True",
			'context':{
				'active_id':val.prepare_id.picking_id.id,
				'active_model':'stock.return.picking',
				'active_ids':val.prepare_id.picking_id.id,
			}
		}
		# print res

	def package_validate(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids, context={})[0]
		# print val.special
		if val.prepare_id.sale_id.state == 'cancel' or val.prepare_id.sale_id.state == 'draft':
			raise osv.except_osv(_('Error'),_('Can\'t Validate document, Please make sure Sale Order has been confirmed'))
		if val.special==False:
			if val.prepare_id.picking_id.state == 'confirmed' or val.prepare_id.picking_id.state == 'assigned':
				if val.prepare_id is None:
					raise osv.except_osv(('Perhatian !'), ('Input Order Packaging Untuk Validate'))
				else:
					stock_move = self.pool.get('stock.move')
					stock_picking = self.pool.get("stock.picking")

					move = [x.product_id.id for x in val.prepare_id.picking_id.move_lines]
					# print "PREPARE ======= ",val.prepare_id
					# return False
					line = [x.product_id.id for x in val.note_lines]
					err = [x for x in line if x not in move]
					# if err:
					# 	v = self.pool.get('product.product').browse(cr, uid, err)[0].default_code
					# 	raise osv.except_osv(('Invalid action !'), ('Product \'%s\' tidak ada didalam daftar order !') % (v,))
					   
					for x in val.note_lines:
						if x.product_qty <= 0:
							raise osv.except_osv(('Perhatian !'), ('Quantity product harus lebih besar dari 0 !'))
						
						for z in val.prepare_id.picking_id.move_lines:
							#print '============================',z.sale_line_id.product_uom_qty
							if x.product_id.id == z.product_id.id:
								if x.product_qty > z.sale_line_id.product_uom_qty:
									y = self.pool.get('product.product').browse(cr, uid, x.product_id.id).default_code
							   # raise osv.except_osv(('Perhatian !'), ('Quantity product \'%s\' lebih besar dari quantity order !') % (y,))
						
					partial_data = {'min_date' : val.tanggal}
					for b in val.note_lines:
						move_id = False
						# mid = stock_move.search(cr, uid, [('picking_id', '=', val.prepare_id.picking_id.id), ('product_id', '=', b.product_id.id)])[0]
						if b.op_line_id.move_id:
							mid = stock_move.search(cr, uid, [('id', '=', b.op_line_id.move_id.id)])[0]
							mad = stock_move.browse(cr, uid, mid)
						else:
							mid = stock_move.search(cr, uid, [('picking_id', '=', val.prepare_id.picking_id.id), ('product_id', '=', b.product_id.id)])[0]
							mad = stock_move.browse(cr, uid, mid)

						move_id = mid
						# if b.product_qty == mad.product_qty:
						# 	move_id = mid
						# else:
						# 	stock_move.write(cr,uid, [mid], {
						# 		'product_qty': mad.product_qty-b.product_qty}
						# 	)
						# 	move_id = stock_move.create(cr,uid, {
						# 					'name' : val.name,
						# 					'product_id': b.product_id.id,
						# 					'product_qty': b.product_qty,
						# 					'product_uom': b.product_uom.id,
						# 					'prodlot_id': mad.prodlot_id.id,
						# 					'location_id' : mad.location_id.id,
						# 					'location_dest_id' : mad.location_dest_id.id,
						# 					'picking_id': val.prepare_id.picking_id.id})
						# 	stock_move.action_confirm(cr, uid, [move_id], context)
							   
						partial_data['move%s' % (move_id)] = {
							'product_id': b.product_id.id,
							'product_qty': b.product_qty,
							'product_uom': b.product_uom.id,
							'prodlot_id': mad.prodlot_id.id}

						# self.pool.get().write(cr,uid,val.prepare_id,{'picking_id':})
					# print "CALLLLLLLLLLLLLLL",partial_data
					iddo = stock_picking.do_partial(cr, uid, [val.prepare_id.picking_id.id], partial_data)
					
					id_done = iddo.items()
					getMove = self.pool.get('stock.move').browse(cr,uid,move_id,context={})
					prepare_obj = self.pool.get('order.preparation')

					# processed_picking_id = id_done[move_id]['delivered_picking']	

					# prepare_obj.write(cr,uid,[val.prepare_id.id],{'picking_id':getMove.picking_id.id})
					prepare_obj.write(cr,uid,[val.prepare_id.id],{'picking_id':id_done[0][1]['delivered_picking']})


					stock_picking.write(cr,uid, [id_done[0][1]['delivered_picking']], {'note_id': val.id})

					# self.write(cr, uid, ids, {'state': 'done', 'picking_id': id_done[0][1]['delivered_picking']})
					self.write(cr, uid, ids, {'state': 'done'})

					print "OP PICKING TO BE",id_done[0][1]['delivered_picking']
					raise osv.except_osv('errr','eerrr')
					# raise osv.except_osv(_("TEST"),_("TEST"))


					return True
			else:
				self.write(cr, uid, ids, {'state': 'done'})
				return True
		else:
			self.write(cr, uid, ids, {'state': 'done'})
			return True
			
		return False

	def do_partial(self, cr, uid, ids, context=None):
		# print 'CALLLLLLLLLLLLLLL MOVE'
		val = self.browse(cr, uid, ids)[0]
		assert len([val.refund_id.id]) == 1, 'Partial picking processing may only be done one at a time.'
		stock_picking = self.pool.get('stock.picking')
		stock_move = self.pool.get('stock.move')
		uom_obj = self.pool.get('product.uom')
		partial = self.browse(cr, uid, [val.refund_id.id][0], context=context)
		partial_data = {
			'delivery_date' : partial.date
		}
		picking_type = partial.picking_id.type
		for wizard_line in partial.move_ids:
			line_uom = wizard_line.product_uom
			move_id = wizard_line.move_id.id

			if wizard_line.quantity < 0:
				raise osv.except_osv(_('Warning!'), _('Please provide proper Quantity.'))

			qty_in_line_uom = uom_obj._compute_qty(cr, uid, line_uom.id, wizard_line.quantity, line_uom.id)
			if line_uom.factor and line_uom.factor <> 0:
				if float_compare(qty_in_line_uom, wizard_line.quantity, precision_rounding=line_uom.rounding) != 0:
					raise osv.except_osv(_('Warning!'), _('The unit of measure rounding does not allow you to ship "%s %s", only rounding of "%s %s" is accepted by the Unit of Measure.') % (wizard_line.quantity, line_uom.name, line_uom.rounding, line_uom.name))
			if move_id:
				initial_uom = wizard_line.move_id.product_uom

				qty_in_initial_uom = uom_obj._compute_qty(cr, uid, line_uom.id, wizard_line.quantity, initial_uom.id)
				without_rounding_qty = (wizard_line.quantity / line_uom.factor) * initial_uom.factor
				if float_compare(qty_in_initial_uom, without_rounding_qty, precision_rounding=initial_uom.rounding) != 0:
					raise osv.except_osv(_('Warning!'), _('The rounding of the initial uom does not allow you to ship "%s %s", as it would let a quantity of "%s %s" to ship and only rounding of "%s %s" is accepted by the uom.') % (wizard_line.quantity, line_uom.name, wizard_line.move_id.product_qty - without_rounding_qty, initial_uom.name, initial_uom.rounding, initial_uom.name))
			else:
				seq_obj_name =  'stock.picking.' + picking_type
				move_id = stock_move.create(cr,uid,{'name' : self.pool.get('ir.sequence').get(cr, uid, seq_obj_name),
													'product_id': wizard_line.product_id.id,
													'product_qty': wizard_line.quantity,
													'product_uom': wizard_line.product_uom.id,
													'prodlot_id': wizard_line.prodlot_id.id,
													'location_id' : wizard_line.location_id.id,
													'location_dest_id' : wizard_line.location_dest_id.id,
													'picking_id': partial.picking_id.id
													},context=context)
				stock_move.action_confirm(cr, uid, [move_id], context)
			partial_data['move%s' % (move_id)] = {
				'product_id': wizard_line.product_id.id,
				'product_qty': wizard_line.quantity,
				'product_uom': wizard_line.product_uom.id,
				'prodlot_id': wizard_line.prodlot_id.id,
			}
			if (picking_type == 'in') and (wizard_line.product_id.cost_method == 'average'):
				partial_data['move%s' % (wizard_line.move_id.id)].update(product_price=wizard_line.cost,
																		product_currency=wizard_line.currency.id)
		stock_picking.do_partial(cr, uid, [partial.picking_id.id], partial_data, context=context)
	
		# return {'type': 'ir.actions.act_window_close'}


	def cancel_dn_all(self, cr, uid, ids, context=None):
		wf_service = netsvc.LocalService("workflow")
		val = self.browse(cr, uid, ids)[0]

		dn_obj = self.pool.get('delivery.note')
		dn_line_obj = self.pool.get('delivery.note.line')
		picking_obj = self.pool.get('stock.picking')
		move_obj = self.pool.get('stock.move')
		op_obj = self.pool.get('order.preparation')
		op_line_obj = self.pool.get('order.preparation.line')

		sale_obj = self.pool.get('sale.order')


		for dn in self.browse(cr,uid,ids,context=context):

			# frst searc for order id
			# find the picking not not finished yet
			# if picking where not finished yet is exist then all move will be moved into last pick where not finished yet
			pickings = self.pool.get('stock.picking').search(cr,uid,[('sale_id','=',dn.prepare_id.sale_id.id),('state','not in',['done','cancel'])],context=context)
			picking_id_to = False
			oldPick = picking_obj.browse(cr,uid,pickings,context=context)
			pickNames = [p.name for p in oldPick]
			if len(pickings) == 1:
				picking_id_to = pickings[0]
			elif len(pickings) > 1:
				raise osv.except_osv(_('Error to cancel Picking'),_('Please Contact your system administrator, Some Picking document cant be canceling'))


			for move in dn.prepare_id.picking_id.move_lines:
				cancel_move = False
				if picking_id_to:
					browsePick = picking_obj.browse(cr,uid,picking_id_to,context=context)
					# if picking must be move into draft/assigned partialed moves

					# but we need to check if order_line id is exist on next picking then we must merge move
					find_same_move = move_obj.search(cr,uid,[('product_id','=',move.product_id.id),('sale_line_id','=',move.sale_line_id.id),('state','not in',['cancel','done'])])
					print find_same_move,"FIND SAME MOVE"
					if len(find_same_move) == 1:
						same_move_obj = move_obj.browse(cr,uid,find_same_move[0],context=context)
						merge_qty = same_move_obj.product_qty + move.product_qty


						move_obj.write(cr,uid,find_same_move,{'product_qty':merge_qty})
						cancel_move = True
					elif len(find_same_move) > 1:
						
						raise osv.except_osv(_('Error!'),_('Move who have same order line and not shipped yet is more than 1, cant handle by system, please contact your system adminsitrator!'))

					if cancel_move:
						move_obj.write(cr,uid,move.id,{'state':'cancel','cancel_notes':'This move automatic moved into '+','.join(pickNames)},context=context)
						# move_obj.delete(cr,uid,move.id,context=context)
					else:
						if len(find_same_move) == 0:
							# move will be state to confirmed
							move_obj.write(cr,uid,move.id,{'picking_id':picking_id_to,'state':'confirmed'})
				else:
					move_obj.write(cr,uid,move.id,{'state':'confirmed'})

			if picking_id_to:
				# picking will cancel, in this condition picking will be not have any move lines because move lines already moved into draft/assigned/confirmed partial next picking
				picking_obj.write(cr,uid,dn.prepare_id.picking_id.id,{'state':'cancel'})

			else:
				# in this condition picking will be set as confirmed cause it not have any partial be ready to execute
				picking_obj.write(cr,uid,dn.prepare_id.picking_id.id,{'state':'confirmed'})
			
			wf_service.trg_delete(uid, 'stock.picking.basic', dn.prepare_id.picking_id.id, cr)
			wf_service.trg_create(uid, 'stock.picking.basic', dn.prepare_id.picking_id.id, cr)



			op_obj.write(cr,uid,dn.prepare_id.id,{'state':'cancel','picking_id':False})

			dn_obj.write(cr,uid,dn.id,{'state':'cancel'})

		
		# print '==============',val.prepare_id.sale_id.id


		return True


delivery_note()
 

class delivery_note_line(osv.osv):
	def _get_refunded_item(self,cr,uid,ids,field_name,arg,context={}):
		res = {}
		for item in self.browse(cr,uid,ids,context=context):
			refunded_total = 0
			for refund in item.note_line_return_ids:
				refunded_total += refund.product_qty

			if item.product_qty == refunded_total:
				self.write(cr,uid,[item.id],{'state':'donerefund'})
			res[item.id] = refunded_total
		return res

	_name = "delivery.note.line"
	_columns = {
		'no': fields.integer('No'),
		'name': fields.text('Description'),
		'note_id': fields.many2one('delivery.note', 'Delivery Note', required=True, ondelete='cascade'),
		'product_id': fields.many2one('product.product', 'Product', domain=[('sale_ok', '=', True)]),
		'product_qty': fields.float('Quantity', digits_compute=dp.get_precision('Product UoM')),
		'product_uom': fields.many2one('product.uom', 'UoM'),
		'product_packaging': fields.many2one('product.packaging', 'Packaging'),
		'op_line_id':fields.many2one('order.preparation.line','OP Line',required=True),
		'note_line_return_ids': fields.many2many('stock.move','delivery_note_line_return','delivery_note_line_id',string="Note Line Returns"),
		'refunded_item': fields.function(_get_refunded_item, string='Refunded Item', store=False),
		'state': fields.selection([('torefund', 'To Refund'), ('refunded', 'Refunded'),('donerefund', 'Done Refund')], 'State', readonly=True),

	}
		 
delivery_note_line()

class packing_list_line(osv.osv):
	_name = "packing.list.line"
	_columns = {
		'name': fields.char('Package', size=64),
		'color': fields.char('Color Code', size=64),
		'urgent':fields.char('Urgent',size=64),
		'product_lines': fields.one2many('product.list.line', 'packing_id', 'Packing List'),
		'note_id': fields.many2one('delivery.note', 'Delivery Note', required=True, ondelete='cascade'),
	}
	

	def refresh(self, cr, uid, ids, context=None):
		val = self.browse(cr, uid, ids)[0]
		for x in val.note_id.note_lines:
			self.pool.get('product.list.line').create(cr, uid, {
														  'no': x.no,
														  'name': x.name,
														  'packing_id': val.id,
														  'product_id': x.product_id.id,
														  'product_qty': x.product_qty,
														  'product_uom': x.product_uom.id,
														  'product_packaging': x.product_packaging.id,
														  })
		return True

		 
	def print_packaging(self, cr, uid, ids, context=None):
		data = {}
		val = self.browse(cr, uid, ids)[0]
		data['form'] = {}
		data['ids'] = context.get('active_ids',[])
		data['form']['data'] = self.read(cr, uid, ids)[0]
		
		no = ''; qty = ''; product = ''; weight = ''; measurement = ''
		for x in val.product_lines:
			
			no = no + str(x.no) + '\n\n'
			measurement = measurement + str(x.measurement) + '\n\n'
			weight = weight + str(x.weight) + '\n\n'
			qty = qty + str(x.product_qty) + ' ' + x.product_uom.name + '\n\n'
			product = product + x.name + '\n\n'
			 
		data['form']['data']['no'] = no
		data['form']['data']['qty'] = qty
		data['form']['data']['weight'] = weight
		data['form']['data']['product'] = product
		data['form']['data']['measurement'] = measurement
		
		data['form']['data']['name'] = val.note_id.partner_id.name
		data['form']['data']['attention'] = val.note_id.prepare_id.sale_id.attention.name
		data['form']['data']['date'] = val.note_id.create_date
		data['form']['data']['reference'] = val.note_id.name
		
		data['form']['data']['purchase'] = val.note_id.poc
		data['form']['data']['pur_date'] = val.note_id.prepare_id.sale_id.date_order
		
		
		 
		return {
				'type': 'ir.actions.report.xml',
				'report_name': 'paket.A4',
				'datas': data,
				'nodestroy':True
		}


packing_list_line()   

class product_list_line(osv.osv):
	_name = "product.list.line"
	_columns = {
		'no': fields.integer('No', size=3),
		'weight': fields.char('weight', size=128),
		'measurement': fields.char('measurement', size=128),
		'name': fields.text('Description'),
		'packing_id': fields.many2one('packing.list.line', 'Packing List', required=True, ondelete='cascade'),
		'product_id': fields.many2one('product.product', 'Product', domain=[('sale_ok', '=', True)]),
		'product_qty': fields.float('Quantity', digits_compute=dp.get_precision('Product UoM')),
		'product_uom': fields.many2one('product.uom', 'UoM'),
	}
		 
product_list_line()   


class stock_move(osv.osv):
	_inherit = "stock.move"
	_columns = {
		'no': fields.integer('No', size=3),
		'desc':fields.text('Description',required=False),
		'product_uom': fields.many2one('product.uom', 'Unit of Measure', required=True,states={'done': [('readonly', True)]}),
		'name':fields.text('Product Name',required=False),
		'set_id':fields.many2one('move.set.data',string="Set Product",ondelete="cascade")
	}

	# def onchange_product_id(self,cr,uid,ids,prd,location_id, location_dest_id, partner):
	#     hasil=self.pool.get('product.product').browse(cr,uid,[prd])[0]
	#     uom=self.pool.get('product.template').browse(cr,uid,[prd])[0]
	#     return {'value':{ 'desc':hasil.name, 'product_qty':1, 'product_uom':uom.uom_id.id} }
	def onchange_product_id(self, cr, uid, ids, prod_id=False, loc_id=False,
							loc_dest_id=False, partner_id=False):
		""" On change of product id, if finds UoM, UoS, quantity and UoS quantity.
		@param prod_id: Changed Product id
		@param loc_id: Source location id
		@param loc_dest_id: Destination location id
		@param partner_id: Address id of partner
		@return: Dictionary of values
		"""
		if not prod_id:
			return {}
		user = self.pool.get('res.users').browse(cr, uid, uid)
		lang = user and user.lang or False
		if partner_id:
			addr_rec = self.pool.get('res.partner').browse(cr, uid, partner_id)
			if addr_rec:
				lang = addr_rec and addr_rec.lang or False
		ctx = {'lang': lang}

		product = self.pool.get('product.product').browse(cr, uid, [prod_id], context=ctx)[0]
		uos_id  = product.uos_id and product.uos_id.id or False
		result = {
			'product_uom': product.uom_id.id,
			'product_uos': uos_id,
			'product_qty': 1.00,
			'product_uos_qty' : self.pool.get('stock.move').onchange_quantity(cr, uid, ids, prod_id, 1.00, product.uom_id.id, uos_id)['value']['product_uos_qty'],
			'prodlot_id' : False
		}
		if product.description:
			result['desc'] = product.name + '\n\n' + product.description
		else:
			result['desc'] = product.name

		if not ids:
			result['name'] = product.partner_ref
		if loc_id:
			result['location_id'] = loc_id
		if loc_dest_id:
			result['location_dest_id'] = loc_dest_id
		return {'value': result}


	def onchange_product_uom_new(self, cr, uid, ids, product, product_uom, context=None):
		if product:
			product_id =self.pool.get('product.product').browse(cr,uid,product)
			if product_id.categ_id.id == 12:
				uom=product_uom
			else:
				uom=product_id.uom_id.id
		else:
			uom=1
		return {'value':{'product_uom':uom}}


stock_move()


# Stock return Picking

class stock_return_picking_memory(osv.osv_memory):
	_name = "stock.return.picking.memory"
	_rec_name = 'product_id'

	_columns = {
		'product_id' : fields.many2one('product.product', string="Product", required=True),
		'quantity' : fields.float("Permintaan Return", digits_compute=dp.get_precision('Product Unit of Measure'), required=True),
		'sisa' : fields.float("Proses Return", digits_compute=dp.get_precision('Product Unit of Measure'), required=False, readonly=True),
		'wizard_id' : fields.many2one('stock.return.picking', string="Wizard"),
		'move_id' : fields.many2one('stock.move', "Move"),
		'prodlot_id': fields.related('move_id', 'prodlot_id', type='many2one', relation='stock.production.lot', string='Serial Number', readonly=True),
	}

	def cekQty(self,cr,uid,ids,minta,sisa):
		if minta>sisa:
			res = {
				'value':{
					'quantity':sisa,
				},
				'warning':{
					'title':'Qty Not Valid',
					'message':'Qty not Enough!'
				}
			}
		else:
			res = {
				'value':{
					'quantity':minta,
				},
			}
		return res



stock_return_picking_memory()


class stock_return_picking(osv.osv_memory):
	_inherit = 'stock.return.picking'
	_name = 'stock.return.picking'
	_description = 'Return Picking'
	_columns = {
		'product_return_moves' : fields.one2many('stock.return.picking.memory', 'wizard_id', 'Moves'),
		'invoice_state': fields.selection([('2binvoiced', 'To be refunded/invoiced'), ('none', 'No invoicing')], 'Invoicing',required=True),
	}

	def default_get(self, cr, uid, fields, context=None):
		"""
		 To get default values for the object.
		 @param self: The object pointer.
		 @param cr: A database cursor
		 @param uid: ID of the user currently logged in
		 @param fields: List of fields for which we want default values
		 @param context: A standard dictionary
		 @return: A dictionary with default values for all field in ``fields``
		"""
		

		result1 = []
		if context is None:
			context = {}
		res = super(stock_return_picking, self).default_get(cr, uid, fields, context=context)

		record_idx = context and context.get('active_id', False) or False

		if context.get('active_model') == 'stock.picking' or context.get('active_model') =='stock.picking.in' or context.get('active_model') =='stock.picking.out':
			record_id = context and context.get('active_id', False)
		else:
			val = self.pool.get('delivery.note').browse(cr, uid, record_idx, context=context)
			record_id = val.prepare_id.picking_id.id

		pick_obj = self.pool.get('stock.picking')
		pick = pick_obj.browse(cr, uid, record_id, context=context)
		if pick:
			if 'invoice_state' in fields:
				if pick.invoice_state=='invoiced':
					res.update({'invoice_state': '2binvoiced'})
				else:
					res.update({'invoice_state': 'none'})
			return_history = self.get_return_history(cr, uid, record_id, context)       
			for line in pick.move_lines:
				qty = line.product_qty - return_history.get(line.id, 0)
				if qty > 0:
					result1.append({'product_id': line.product_id.id, 'sisa':qty, 'quantity': qty,'move_id':line.id, 'prodlot_id': line.prodlot_id and line.prodlot_id.id or False})

			if 'product_return_moves' in fields:
				res.update({'product_return_moves': result1})
		return res

	def view_init(self, cr, uid, fields_list, context=None):
		"""
		 Creates view dynamically and adding fields at runtime.
		 @param self: The object pointer.
		 @param cr: A database cursor
		 @param uid: ID of the user currently logged in
		 @param context: A standard dictionary
		 @return: New arch of view with new columns.
		"""


		res ={}
		if context is None:
			context = {}
		record_idx = context and context.get('active_id', False)


		if context.get('active_model') == 'stock.picking' or context.get('active_model') == 'stock.picking.in' or context.get('active_model') == 'stock.picking.out':
			record_id = context and context.get('active_id', False)
		else:
			val = self.pool.get('delivery.note').browse(cr, uid, record_idx, context=context)
			record_id = val.prepare_id.picking_id.id
			context.update({
				'active_model': 'stock.picking',
				'active_ids': [val.prepare_id.picking_id.id],
				'active_id': val.prepare_id.picking_id.id
			})
			print '=============',context.get('active_id', False)

		res = super(stock_return_picking, self).view_init(cr, uid, fields_list, context=context)
		return res
	
	def get_return_history(self, cr, uid, pick_id, context=None):
		""" 
		 Get  return_history.
		 @param self: The object pointer.
		 @param cr: A database cursor
		 @param uid: ID of the user currently logged in
		 @param pick_id: Picking id
		 @param context: A standard dictionary
		 @return: A dictionary which of values.
		"""
		pick_obj = self.pool.get('stock.picking')
		pick = pick_obj.browse(cr, uid, pick_id, context=context)
		return_history = {}
		for m  in pick.move_lines:
			if m.state == 'done':
				return_history[m.id] = 0
				for rec in m.move_history_ids2:
					# only take into account 'product return' moves, ignoring any other
					# kind of upstream moves, such as internal procurements, etc.
					# a valid return move will be the exact opposite of ours:
					#     (src location, dest location) <=> (dest location, src location))
					if rec.location_dest_id.id == m.location_id.id \
						and rec.location_id.id == m.location_dest_id.id:
						return_history[m.id] += (rec.product_qty * rec.product_uom.factor)
		return return_history

	def create_returns(self, cr, uid, ids, context=None):
		""" 
		 Creates return picking.
		 @param self: The object pointer.
		 @param cr: A database cursor
		 @param uid: ID of the user currently logged in
		 @param ids: List of ids selected
		 @param context: A standard dictionary
		 @return: A dictionary which of fields with values.
		"""


		# prepare dn
		dn = self.pool.get('delivery.note')
		# call active dn
		active_dn_id = context['active_ids'][0]
		dn_obj = dn.browse(cr,uid,context['active_ids'][0],context=context)


		if context is None:
			context = {} 
		record_idx = context and context.get('active_id', False) or False

		if context.get('active_model') == 'stock.picking' or context.get('active_model') == 'stock.picking.in' or context.get('active_model') == 'stock.picking.out':
			record_id = context and context.get('active_id', False) or False
		else:
			val = self.pool.get('delivery.note').browse(cr, uid, record_idx, context=context)
			record_id = val.prepare_id.picking_id.id

		move_obj = self.pool.get('stock.move')
		pick_obj = self.pool.get('stock.picking')
		uom_obj = self.pool.get('product.uom')
		data_obj = self.pool.get('stock.return.picking.memory')
		act_obj = self.pool.get('ir.actions.act_window')
		model_obj = self.pool.get('ir.model.data')
		#  Delivery Note
		del_note = self.pool.get('delivery.note')

		wf_service = netsvc.LocalService("workflow")
		
		if context.get('active_model') == 'stock.picking' or context.get('active_model') == 'stock.picking.in' or context.get('active_model') == 'stock.picking.out':
			record_id = context and context.get('active_id', False) or False
			pick = pick_obj.browse(cr, uid, record_id, context=context)
		else:
			val = self.pool.get('delivery.note').browse(cr, uid, record_idx, context=context)
			pick = pick_obj.browse(cr, uid, val.prepare_id.picking_id.id, context=context)

		
		data = self.read(cr, uid, ids[0], context=context)
		date_cur = time.strftime('%Y-%m-%d %H:%M:%S')
		set_invoice_state_to_none = True
		returned_lines = 0
		
		#Create new picking for returned products
		seq_obj_name = 'stock.picking'
		new_type = 'internal'
		if pick.type =='out':
			new_type = 'in'
			seq_obj_name = 'stock.picking.in'
		elif pick.type =='in':
			new_type = 'out'
			seq_obj_name = 'stock.picking.out'
		new_pick_name = self.pool.get('ir.sequence').get(cr, uid, seq_obj_name)
		
		if context.get('active_model') == 'stock.picking' or context.get('active_model') ==  'stock.picking.in' or context.get('active_model') == 'stock.picking.out':
			new_picking = pick_obj.copy(cr, uid, pick.id, {
								'name': _('%s-%s-return') % (new_pick_name, pick.name),
								'move_lines': [], 
								'state':'draft', 
								'type': new_type,
								'date':date_cur,
								'invoice_state': data['invoice_state'],
								})
		else:
			new_picking = pick_obj.copy(cr, uid, pick.id, {
								'name': _('%s-%s-return') % (new_pick_name, pick.name),
								'move_lines': [], 
								'state':'draft', 
								'type': new_type,
								'date':date_cur,
								'note_id':val.id,
								'invoice_state': data['invoice_state'],
								})
			# dn.write(cr,uid,val.id,{'note_return_ids':[(0,0,{'delivery_note_id':val.id,'picking_id':new_picking})]})
			dn.write(cr,uid,val.id,{'note_return_ids':[(4,new_picking)]})

		dn_return_rel = []
		val_id = data['product_return_moves']
		
		# prepare op / to get note line id
		if context.get('active_model') == 'delivery.note':
			op_line = self.pool.get('order.preparation.line')
			dn_line = self.pool.get('delivery.note.line')
		_logger.error((val_id),"OOOOOOOOOOOO")
		for v in val_id:
			data_get = data_obj.browse(cr, uid, v, context=context)
			mov_id = data_get.move_id.id
			
			# search op and dn
			if context.get('active_model') == 'delivery.note':
				_logger.error((mov_id,"aaaaa<<<<<<<<<<<<<<<<"))

				op_line_id = op_line.search(cr,uid,[('move_id','=',mov_id)],context=context)
				if type(op_line_id)==list:
					op_line_id = op_line_id[0]

				dn_line_id = dn_line.search(cr,uid,[('op_line_id','=',op_line_id)],context=context)
				if type(dn_line_id)==list and len(dn_line_id)>0:
					dn_line_id = dn_line_id[0]

			if not mov_id:
				raise osv.except_osv(_('Warning !'), _("You have manually created product lines, please delete them to proceed"))


			# Cek Barang yang sisa & yang di input
			return_history = self.get_return_history(cr, uid, pick.id, context)
			
			qty = 0
			for line in pick.move_lines:
				qty += line.product_qty - return_history.get(line.id, 0)
			
			print '=========== YANG PERNAH DIBUAT RO============',qty

			print '==============YANG DIMINTA RO==========',data_get.quantity
			if context.get('active_model') == 'delivery.note':
				if data_get.quantity > qty:
					raise osv.except_osv(_('Warning !'), _("Product Qty Tidak Mencukupi"))
			# else:
			# 	raise osv.except_osv(_('Warning !'), _("cek AJA"))
					
			new_qty = data_get.quantity
			move = move_obj.browse(cr, uid, mov_id, context=context)
			new_location = move.location_dest_id.id
			returned_qty = move.product_qty
			for rec in move.move_history_ids2:
				returned_qty -= rec.product_qty

			if returned_qty != new_qty:
				set_invoice_state_to_none = False
			if new_qty:
				returned_lines += 1
				new_move=move_obj.copy(cr, uid, move.id, {
											'product_qty': new_qty,
											'product_uos_qty': uom_obj._compute_qty(cr, uid, move.product_uom.id, new_qty, move.product_uos.id),
											'picking_id': new_picking, 
											'state': 'draft',
											'location_id': new_location, 
											'location_dest_id': move.location_id.id,
											'date': date_cur,
				})
				move_obj.write(cr, uid, [move.id], {'move_history_ids2':[(4,new_move)]}, context=context)
				
			if context.get('active_model') == 'delivery.note':
				tpl = {'delivery_note_id':active_dn_id,'stock_picking_id':new_picking,'delivery_note_line_id':dn_line_id,'stock_move_id':new_move}
				dn_return_rel.append(tpl)

		if context.get('active_model') == 'delivery.note':
			dn_r = self.pool.get('delivery.note.line.return')
			# write into dn line rel
			for note_line_return in dn_return_rel:
				dn_r.create(cr,uid,note_line_return)

		if not returned_lines:
			raise osv.except_osv(_('Warning!'), _("Please specify at least one non-zero quantity."))

		if set_invoice_state_to_none:
			pick_obj.write(cr, uid, [pick.id], {'invoice_state':'none'}, context=context)
		wf_service.trg_validate(uid, 'stock.picking', new_picking, 'button_confirm', cr)
		pick_obj.force_assign(cr, uid, [new_picking], context)
		# Update view id in context, lp:702939

		# update Delivery Note
		if context.get('active_model') == 'delivery.note':
			val = self.pool.get('delivery.note').browse(cr, uid, record_idx, context=context)
			del_note.write(cr, uid, val.id, {'state':'torefund','refund_id':new_picking}, context=context)

		model_list = {
				'out': 'stock.picking.out',
				'in': 'stock.picking.in',
				'internal': 'stock.picking',
		}
		return {
			'domain': "[('id', 'in', ["+str(new_picking)+"])]",
			'name': _('Returned Picking'),
			'view_type':'form',
			'view_mode':'tree,form',
			'res_model': model_list.get(new_type, 'stock.picking'),
			'type':'ir.actions.act_window',
			'context':context,
		}

stock_return_picking()


class stock_invoice_onshipping(osv.osv_memory):

	def _get_journal(self, cr, uid, context=None):

		res = self._get_journal_id(cr, uid, context=context)
		if res:
			return res[0][0]
		return False

	def _get_journal_id(self, cr, uid, context=None):
		if context is None:
			context = {}
		# print context,"--------------"
		model = context.get('active_model')
		viewFromDn = False
		
		# if not model or 'stock.picking' not in model:
		if not model or 'stock.picking' not in model:
			# jika dn
			if model == 'delivery.note':
				# jika dn
				model = 'stock.picking'
				viewFromDn = True
			else:
				return []
		model_pool = self.pool.get(model)
		journal_obj = self.pool.get('account.journal')
		# res_idsx = context.get('active_ids', [])
		if not viewFromDn:
			# active_ids  = id stock_picking
			res_ids = context and context.get('active_ids', [])
		else:
			# active_ids = id dn
			# ambil refund_id.id
			dn = self.pool.get('delivery.note').browse(cr,uid,context.get('active_ids'),{})[0]

			res_ids = [dn.refund_id.id]

		vals = []
		browse_picking = model_pool.browse(cr, uid, res_ids, context=context)

		for pick in browse_picking:
			if not pick.move_lines:
				continue
			src_usage = pick.move_lines[0].location_id.usage
			dest_usage = pick.move_lines[0].location_dest_id.usage
			type = pick.type
			if type == 'out' and dest_usage == 'supplier':
				journal_type = 'purchase_refund'
			elif type == 'out' and dest_usage == 'customer':
				journal_type = 'sale'
			elif type == 'in' and src_usage == 'supplier':
				journal_type = 'purchase'
			elif type == 'in' and src_usage == 'customer':
				journal_type = 'sale_refund'
			else:
				journal_type = 'sale'

			value = journal_obj.search(cr, uid, [('type', '=',journal_type )])
			for jr_type in journal_obj.browse(cr, uid, value, context=context):
				t1 = jr_type.id,jr_type.name
				if t1 not in vals:
					vals.append(t1)
		return vals

	_name = "stock.invoice.onshipping"
	_description = "Stock Invoice Onshipping"

	_columns = {
		'journal_id': fields.selection(_get_journal_id, 'Destination Journal',required=True),
		'group': fields.boolean("Group by partner"),
		'invoice_date': fields.date('Invoiced date'),
	}

	_defaults = {
		'journal_id' : _get_journal,
	}

	def view_init(self, cr, uid, fields_list, context=None):
		if context is None:
			context = {}
		res = super(stock_invoice_onshipping, self).view_init(cr, uid, fields_list, context=context)
		pick_obj = self.pool.get('stock.picking')
		count = 0
		active_idsx = context.get('active_ids',[])

		if context.get('active_model') == 'delivery.note':
			val = self.pool.get('delivery.note').browse(cr, uid, active_idsx[0], context=context)
			active_ids = [val.refund_id.id]
		else:
			active_ids = context.get('active_ids',[])

		

		for pick in pick_obj.browse(cr, uid, active_ids, context=context):
			if pick.invoice_state != '2binvoiced':
				count += 1
		if len(active_ids) == 1 and count:
			raise osv.except_osv(_('Warning!'), _('This picking list does not require invoicing.'))
		if len(active_ids) == count:
			raise osv.except_osv(_('Warning!'), _('None of these picking lists require invoicing.'))
		return res

	def open_invoice(self, cr, uid, ids, context=None):
		if context is None:
			context = {}
		invoice_ids = []
		data_pool = self.pool.get('ir.model.data')
		res = self.create_invoice(cr, uid, ids, context=context)
		invoice_ids += res.values()
		inv_type = context.get('inv_type', False)
		action_model = False
		action = {}
		if not invoice_ids:
			raise osv.except_osv(_('Error!'), _('Please create Invoices.'))
		if inv_type == "out_invoice":
			action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree1")
		elif inv_type == "in_invoice":
			action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree2")
		elif inv_type == "out_refund":
			action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree3")
		elif inv_type == "in_refund":
			action_model,action_id = data_pool.get_object_reference(cr, uid, 'account', "action_invoice_tree4")
		if action_model:
			action_pool = self.pool.get(action_model)
			action = action_pool.read(cr, uid, action_id, context=context)
			action['domain'] = "[('id','in', ["+','.join(map(str,invoice_ids))+"])]"
		return action

	def create_invoice(self, cr, uid, ids, context=None):
		if context is None:
			context = {}
		picking_pool = self.pool.get('stock.picking')
		

		onshipdata_obj = self.read(cr, uid, ids, ['journal_id', 'group', 'invoice_date'])
		if context.get('new_picking', False):
			onshipdata_obj['id'] = onshipdata_obj.new_picking
			onshipdata_obj[ids] = onshipdata_obj.new_picking
		context['date_inv'] = onshipdata_obj[0]['invoice_date']
		active_idsx = context.get('active_ids', [])

		if context.get('active_model') == 'delivery.note':
			val = self.pool.get('delivery.note').browse(cr, uid, active_idsx[0], context=context)
			active_ids = [val.refund_id.id]
		else:
			active_ids = context.get('active_ids',[])

		
		active_picking = picking_pool.browse(cr, uid, context.get('active_id',False), context=context)
		inv_type = picking_pool._get_invoice_type(active_picking)
		context['inv_type'] = inv_type
		if isinstance(onshipdata_obj[0]['journal_id'], tuple):
			onshipdata_obj[0]['journal_id'] = onshipdata_obj[0]['journal_id'][0]
		res = picking_pool.action_invoice_create(cr, uid, active_ids,
			  journal_id = onshipdata_obj[0]['journal_id'],
			  group = onshipdata_obj[0]['group'],
			  type = inv_type,
			  context=context)
		return res

stock_invoice_onshipping()


class stock_partial_picking_line(osv.osv):

	_inherit = "stock.partial.picking.line"
	_columns = {
		'product_name':fields.text('Product Name',required=False),
	}


stock_partial_picking_line()


class stock_picking_in(osv.osv):

	_inherit = 'stock.picking.in'

	def action_process(self, cr, uid, ids, context=None):
		res = super(stock_picking_in, self).action_process(cr, uid, ids, context)

		return res
	
stock_picking_in()


class stock_partial_picking(osv.osv_memory):
	
	_inherit = "stock.partial.picking"

	def _partial_move_for(self, cr, uid, move):
		partial_move = {
			'product_id' : move.product_id.id,
			'product_name':move.name,
			'quantity' : move.product_qty if move.state == 'assigned' or move.picking_id.type == 'in' else 0,
			'product_uom' : move.product_uom.id,
			'prodlot_id' : move.prodlot_id.id,
			'move_id' : move.id,
			'location_id' : move.location_id.id,
			'location_dest_id' : move.location_dest_id.id,
		}
		if move.picking_id.type == 'in' and move.product_id.cost_method == 'average':
			partial_move.update(update_cost=True, **self._product_cost_for_average_update(cr, uid, move))
		return partial_move


class delivery_note_line_return(osv.osv):

	_name = 'delivery.note.line.return'	
	_columns = {
		'delivery_note_id': fields.many2one('delivery.note','Delivery Note', ondelete='cascade',onupdate="cascade"),
		'delivery_note_line_id': fields.many2one('delivery.note.line','Delivery Note Line',ondelete='cascade',onupdate="cascade"),
		'stock_picking_id': fields.many2one('stock.picking','Stock Picking',ondelete='cascade',onupdate="cascade"),
		'stock_move_id': fields.many2one('stock.move','Stock Move',ondelete='cascade', onupdate="cascade"),
	}

delivery_note_line_return()
