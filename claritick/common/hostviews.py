# -*- coding: utf-8 -*-

from clariadmin.models import Host
from common.models import Client, HostChar
from django.http import HttpResponse
from django.template import RequestContext
from django.shortcuts import render_to_response
from django.contrib.auth.decorators import login_required
from django.utils import simplejson
import re

IP_ADDRESS_REGEXP = re.compile(r"^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$")

@login_required
def ajax_load_host_client(request, client_id):
    # List all the host of the current user
    host_list = HostChar.objects.filter(client=client_id)
    ip_table = []
    for host in host_list:
        host_ip = host.host.ip.split()
        for ip in host_ip:
            if IP_ADDRESS_REGEXP.match(ip):
                ip_table.append([host.host.site,ip,host.host.type,host.name])
    return render_to_response('hostclient.html', {"host_list": ip_table}, context_instance=RequestContext(request))

@login_required
def ajax_delete_host_client(request):
    # Delete an host from many to many field client host
    host = HostChar.objects.get(host=request.POST['host_id'],client=request.POST['client_id'])
    host.delete()
    return render_to_response('hostclient.html', context_instance=RequestContext(request))

@login_required
def ajax_add_host_client(request):
    # Add an host to many to many field client host
    currentclient = Client.objects.get(pk=request.POST['client_id'])
    currenthost = Host.objects.get(pk=request.POST['host_id'])
    currentname = request.POST['name']
    currentmany = HostChar(host=currenthost,client=currentclient,name=currentname)
    currentmany.save()
    test_dict = {'a': 1, 'b': 2, 'john' : 'done', 'jane' : 'doe'}
    test_dict = simplejson.dumps(test_dict)
    return HttpResponse(test_dict)
    return render_to_response('hostclient.html', {"test_value_return": currentmany},context_instance=RequestContext(request))
