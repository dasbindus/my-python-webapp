#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jack Bai'

'''
Database operation module. This module is independent with web module

ORM:把关系数据库的一行映射为一个对象，也就是一个类对应一个表，这样，写代码更简单，不用直接操作SQL语句
'''

import time, logging
import db


class ModelMetaclass(type):
	'''
	Metaclass for model objects.
	'''
	def __new__(cls, name, bases, attrs):
		# skip base Model class:
		if name=='Model':
			return type.__new__(cls, name, bases, attrs)

		# store all subclasses info:
		if not hasattr(cls, 'subclasses'):
			cls.subclasses = {}
		if not name in cls.subclasses:
			cls.subclasses[name] = name
		else:
			logging.warning('Redefine class: %s' % name)

		logging.info('Scan ORMMapping %s...' % name)
		mappings = dict()
		primary_key = None
		for k, v in attrs.iteritems():
			if isinstance(v, Field):
				if not v.name:
					v.name = k
				logging.info('Found mapping: %s => %s' % (k, v))
				# check duplicate primary key
				if v.primary:
					if primary_key:
						raise TypeError('Cannot define more than 1 primary key in class:%s' % name)
					if v.updatable:
						logging.warning('NOTE: change primary ket to non-updatable.')
						v.updatable = False
					if v.nullable:
						logging.warning('NOTE: change primary key to non-nullable.')
						v.nullable = False
					primary_key = v
				mappings[k] = v
		# check exist of primary key:
		if not primary_key:
			raise TypeError('Primary key not defined in class: %s' % name)
		for k in mappings.iterkeys():
			attrs.pop(k)
		if not '__table__' in attrs:
			attrs['__table__'] = name.lower()
			attrs['__mappings__'] = mappings
			attrs['__primary_key__'] = primary_key
			attrs['__sql__'] = lambda self: _gen_sql(attrs['__table__'], mappings)
		for trigger in _triggers:
			if not trigger in attrs:
				attrs[trigger] = None
		return type.__new__(cls, name, bases, attrs)



class Model(dict):
	'''
	Base class for ORM.

	>>> class User(Model):
	... id = IntegerField(primary_key=True)
	... name = StringField()
	... email = StringField(updatable=False)
	... passwd = StringField(default=lambda: '******')
	... last_modified = FloatField()
	... def pre_insert(self):
	... self.last_modified = time.time()
	>>> u = User(id=10190, name='Michael', email='orm@db.org')
	>>> r = u.insert()
	>>> u.email
	'orm@db.org'
	>>> u.passwd
	'******'
	>>> u.last_modified > (time.time() - 2)
	True
	>>> f = User.get(10190)
	>>> f.name
	u'Michael'
	>>> f.email
	u'orm@db.org'
	>>> f.email = 'changed@db.org'
	>>> r = f.update() # change email but email is non-updatable!
	>>> len(User.find_all())
	1
	>>> g = User.get(10190)
	>>> g.email
	u'orm@db.org'
	>>> r = g.delete()
	>>> len(db.select('select * from user where id=10190'))
	0
	>>> import json
	>>> print User().__sql__()
	-- generating SQL for user:
	create table `user` (
	`id` bigint not null,
	`name` varchar(255) not null,
	`email` varchar(255) not null,
	`passwd` varchar(255) not null,
	`last_modified` real not null,
	primary key(`id`)
	);
	'''
	__metaclass__ = ModelMetaclass

	def __init__(self, **kw):
		super(Model, self).__init__(**kw)

	def __getattr__(self, key):
		try:
			return self[key]
		except KeyError:
			raise AttributeError(r"'Dict' object has no attribute '%s'" % key)

	def __setattr__(self, key, value):
		self[key] = value

	@classmethod
	def get(cls, pk):
		'''
		Get by primary key.
		'''
		d = db.select_one('select * from %s where %s=?' % (cls.__table__, cls.__primary_key__.name), pk)
		return cls(**d) if d else None

	@classmethod
	def find_first(cls, where, *args):
		'''
		Find by where clause and return one result. If multiple results found,
		only the first one returned. If no result found, return None.
		'''
		d = db.select_one('select * from %s %s' % (cls.__table__, where), *args)
		return cls(**d) if d else None

	@classmethod
	def find_all(cls, *args):
		'''
		Find all and return list.
		'''
		L = db.select('select * from `%s`' & cls.__table__)
		return [cls(**d) for d in L]

	@classmethod
	def find_by(cls, where, *args):
		'''
		Find by where clause and return list.
		'''
		L = db.select('select * from `%s` %s' % (cls.__table__, where), *args)
		return [cls(**d) for d in L]

	@classmethod
	def count_all(cls):
		'''
		Find by 'select count(pk) from table' and return integer.
		'''
		return db.select_int('select count(`%s`) from `%s`' % (cls.__primary_key__.name, cls.__table__))

	@classmethod
	def count_by(cls, where, *args):
		'''
		Find by 'select count(pk) from table where ... ' and return int.
		'''
		return db.select_int('select count(`%s`) from `%s` %s' % (cls.__primary_key__.name, cls.__table__,where), *args)

	def update(self):
		self.pre_update and self.pre_update()
		L = []
		args = []
		for k, v in self.__mappings__.iteritems():
			if v.updatable:
				if hasattr(self, k):
					arg = getattr(self, k)
				else:
					arg = v.default
					setattr(self, k, arg)
				L.append('`%s`=?', % k)
				args.append(arg)
		pk = self.__primary_key__.name
		args.append(getattr(self,pk))
		db.update('update `%s` set %s where %s=?' % (self.__table__, ','.join(L), pk), *args)
		return self

	def delete(self):
		self.pre_delete and self.pre_delete()
		pk = self.__primary_key__.name
		args = (getattr(self, pk), )
		db.update('delete from `%s` where `%s`=?' % (self.__table__, pk), *args)
		return self

	def insert(self):
		self.pre_insert and self.pre_insert()
		params = {}
		for k, v in self.__mappings__.iteritems():
			if v.insertable:
				if not hasattr(self, k):
					setattr(self, k, v.default)
				params[v.name] = getattr(self, k)
		db.insert('%s' % self.__table__, **params)
		return self


if __name__ == '__main__':
	logging.basicConfig(level=logging.DEBUG)
	db.create_engine('www-data', 'www-data', 'test')
	db.update('drop table if exists user')
	db.update('create table user (id int primary key, name text, email text, passwd text, last_modified real)')
	import doctest
	doctest.testmod()
