#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jack Bai'

import logging, os, re, time, base64, hashlib

from transwarp.web import get, post, ctx, view, interceptor, seeother, notfound

from models import User, Blog, Comment

from apis import api, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError


@view('blogs.html')
@get('/')
def index():
	blogs = Blog.find_all()
	user = User.find_first('where email=?', 'admin@example.com')
	return dict(blogs=blogs, user=user)


@view('test_users.html')
@get('/test_users')
def test_users():
	users = User.find_all()
	return dict(users=users)


@api
@get('/api/users')
def api_get_users():
	users = User.find_by('order by created_at desc')
	for u in users:
		# replace password with '******'
		u.password = '******'
	return dict(users=users)