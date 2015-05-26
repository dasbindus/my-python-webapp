#!/usr/bin/env python
# -*- coding: utf-8 -*-

__author__ = 'Jack Bai'

'''
A WSGI application entry.
'''

import logging; logging.basicConfig(level=logging.INFO)
import os, time
from datetime import datetime

from transwarp import db
from transwarp.web import WSGIApplication, Jinja2TemplateEngine

from config import configs


def datetime_filter(t):
	delta = int(time.time() - t)
	if delta < 60:
		return u'1 minutes ago'
	if delta < 3600:
		return u'%s minutes ago' % (delta // 60)
	if delta < 86400:
		return u'%s hours ago' % (delta // 3600)
	if delta < 604800:
		return u'%s days ago' % (delta // 86400)
	dt = datetime.fromtimestamp(t)
	return u'%s年%s月%s日' % (dt.year, dt.month, dt.day)


# init db(初始化数据库):
db.create_engine(**configs.db)

# init wsgi app(创建一个WSGIApplication):
wsgi = WSGIApplication(os.path.dirname(os.path.abspath(__file__)))

# 初始化jinja2模板引擎:
template_engine = Jinja2TemplateEngine(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
template_engine.add_filter('datetime', datetime_filter)

wsgi.template_engine = template_engine

# 加载带有@get/@post的URL处理函数:
import urls

wsgi.add_interceptor(urls.user_interceptor)
wsgi.add_interceptor(urls.manage_interceptor)
wsgi.add_module(urls)

# 在9000端口上启动本地测试服务器:
if __name__ == '__main__':
	wsgi.run(9000, host='0.0.0.0')
else:
	application = wsgi.get_wsgi_application()