# -*- coding: utf-8 -*-

from django.conf.urls.defaults import *

urlpatterns = patterns('claritick.ticket.views',
    url(r'^partial_new/$',         'partial_new', name="ticket_partial_new"),
    url(r'^new/$',                 'new', name="ticket_new"),
    url(r'^modify/(\d*)/$',          'modify', name="ticket_modify"),
    url(r'^view/$',            'list_view', name="ticket_list_view"),
    url(r'^view/(?P<view_id>\d+)/$',            'list_view', name="ticket_list_view"),
    url(r'^list/$',                'list_all', name="ticket_list"),
    url(r'^list/all/$',             'list_all', name="ticket_list_all"),
    url(r'^list/me/$',              'list_me', name="ticket_list_me"),
    url(r'^list/unassigned/$',      'list_unassigned', name="ticket_list_unassigned"),
)
