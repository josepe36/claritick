# -*- coding: utf-8 -*-

from django.conf.urls.defaults import *

urlpatterns = patterns('clariadmin.views',
    url(r'^new/$',                 'new', name='new_host'),
    url(r'^new/from/(-?\d+)$', 'new'),
    url(r'^modify/(-?\d+)$',          'modify'),
    url(r'^list/(all)?$',          'list_all', name='list_hosts'),
    url(r'^getExtrafieldsForm/(-?\d+)(/b)?', 'ajax_extra_fields_form'),
)
