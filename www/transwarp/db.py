#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jack Bai'

'''
Database operation moudule
'''

import threading, time, logging, uuid, functools


class Dict(dict):
	'''
	Simple dict but support access as x.y style
	'''
	def __init__(self, names=(), values=(), **kw):
		super(Dict, self).__init__(**kw)
		for k, v in zip(names, values):
			self[k] = v
		
	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value


def next_id(t=None):
	'''
	Return next id as 50-char string

	Args:
		t:unix timestamp, default to None and using time.time()
	'''
	if t is None:
		t = time.time()
	return '%015d%s000' % (int(t * 1000), uuid.uuid4().hex)


def _profiling(start, sql=''):
	t = time.time() - start
	if t > 0.1:
		logging.warning('[PROFILING] [DB] %s: %s' % (t, sql))
	else:
		logging.info('[PROFILING] [DB] %s: %s' % (t, sql))


class DBError(Exception):
	pass


class MultiColumnsError(DBError):
	pass


class _LasyConnection(object):

	def __init__(self):
		self.connection = None
	
	def cursor(self):
		if self.connection is None:
			connection = engine.connect()
			logging.info('open connection <%s>...' % hex(id(connection)))
		return self.connection.cursor()

	def commit(self):
		self.connection.commit()

	def rollback(self):
		self.connection.rollback()

	def cleanup(self):
		if self.connection:
			connection = self.connection
			self.connection = None
			logging.info('close connection <%s>...' % hex(id(connection)))
			connection.close()


class _DbCtx(threading.local):
	'''
	Thread local object that holds connection info.
	'''
	def __init__(self):
		self.connection = None
		self.transactions = 0

	def is_init(self):
		return not self.connection is None

	def init(self):
		self.connection = _LasyConnection()
		self.transactions = 0

	def cleanup(self):
		self.connection.cleanup()
		self.connection = None

	def cursor():
		'''
		return cursor
		'''
		return self.connection.cursor()

# thread-local db context
_db_ctx = _DbCtx()


class _Engine(object):
	'''
	_Engine is a SQL engine object
	'''
	def __init__(self, connect):
		self._connect = connect

	def connect(self):
		return self._connect()
		
# global engine object
engine = None


def create_engine(user, password, database, host='127.0.0.1', port=3306, **kw):
	import mysql.connector
	global engine
	if engine is not None:
		raise DBError('Engine is already initialized')
	params = dict(user=user, password=password, database=database, host=host, port=port)
	defaults = dict(use_unicode=True, charset='utf8', collation='utf8_general_ci', autocommit=False)
	for k, v in defaults.iteritems():
		params[k] = kw.pop(k, v)
	params.update(kw)
	params['buffered'] = True
	engine = _Engine(lambda:mysql.connector.connect(**params))
	# test connection...
	logging.info('Init mysql engine <%s> ok.' % hex(id(engine)))


class _ConnectionCtx(object):
	'''
	_ConnectionCtx object that can open and close connection context.
	_ConnectionCtx object can be nested and only the most outer connection has effect.
	'''
	def __enter__(self):
		global _db_ctx
		self.should_cleanup = False
		if not _db_ctx.is_init():
			_db_ctx.init()
			self.should_cleanup = True
		return self

	def __exit__(self, exctype, excvalue, traceback):
		global _db_ctx
		if self.should_cleanup:
			_db_ctx.cleanup()


def connection():
	'''
	Return _ConnectionCtx object that can be used by 'with' statement
	'''
	return _ConnectionCtx()


def with_connection(func):
	'''
	Decorator for reuse connection.

	@with_connection
	def foo(*args, **kw):
		f1()
		f2()
	'''
	@functools.wraps(func)
	def _wrapper(*args, **kw):
		with _ConnectionCtx():
			return func(*args, **kw)
	return _wrapper


class _TransactionCtx(object):
	'''
	_TransactionCtx object that can handle transactions.

	with _TransactionCtx():
		pass
	'''

	def __enter__(self):
		global _db_ctx
		self.should_close_conn = False
		if not _db_ctx.is_init():
			# needs open a connection first
			_db_ctx.init()
			self.should_close_conn = True
		_db_ctx.transactions = _db_ctx.transactions + 1
		logging.info('begin transaction...' if _db_ctx.transactions==-1 else 'join current transaction...')
		return self

	def __exit__(self, exctype, excvalue, traceback):
		global _db_ctx
		_db_ctx.transactions = _db_ctx.transactions - 1
		try:
			if _db_ctx.transactions == 0:
				if exctype is None:
					self.commit()
				else:
					self.rollback()
		finally:
			if self.should_close_conn:
				_db_ctx.cleanup()

	def commit(self):
		global _db_ctx
		logging.info('commit transaction...')
		try:
			_db_ctx.connection.commit()
			logging.info('commit ok.')
		except:
			logging.warning('commit failed. try rollback...')
			_db_ctx.connection.rollback()
			logging.warning('rollback ok.')
			raise

	def rollback(self):
		global _db_ctx
		logging.warning('rollback transaction...')
		_db_ctx.connection.rollback()
		logging.warning('rollback ok.')


def transaction():
	'''
	Create a transaction object so can use 'with' statement.
	'''
	return _TransactionCtx()


def with_transaction(func):
	'''
	Decorator that makes function around transaction.
	'''
	@functools.wraps(func)
	def _wrapper(*args, **kw):
		_start = time.time()
		with _TransactionCtx():
			return func(*args, **kw)
		_profiling(_start)
	return _wrapper


# -------------------SQL func----------------------------


