# -*- coding: utf-8 -*-

import re

from django.contrib.auth.decorators import login_required, permission_required
from django.views.generic import create_update
from django.core.urlresolvers import reverse
from django.shortcuts import render_to_response, redirect, get_object_or_404
from django.template import RequestContext
from django.http import HttpResponse, HttpResponseBadRequest
from django.core.exceptions import PermissionDenied
from django.forms.models import modelformset_factory
from django.utils import simplejson as json

from common.models import Client, Coordinate, HostChar
from common.forms import ClientForm, CoordinateForm
from common.utils import user_has_perms_on_client
from bondecommande.models import BonDeCommande
from clariadmin.models import Host
try:
    from chuser.forms import ChuserForm
except ImportError:
    ChuserForm = None

# LC: XX: crossdependency: BAD
try:
    from packaging.models import ClientPackageAuth
except ImportError:
    print "Hummf"

@login_required
def infos_login(request):
    """
    Informations sur le client (liste d'enfants, modif mot de passe, ...)
    """
    client = request.user.my_userprofile.client
    if not client:
        raise Exception(u"Pas de client dans le profil pour l'utilisateur %s." % request.user)
    
    # First determine packageAuth client
    try:
        packageauth = ClientPackageAuth.objects.get(client__pk=client.id)
    except ClientPackageAuth.DoesNotExist:
        packageauth = None
    except NameError: # LC: Import failed
        packageauth = None

    client_qs = Client.objects.get_childs('parent', client.pk)
    
    chuserform = None
    if request.user.is_superuser or request.session.get('was_superuser', False) and ChuserForm:
        chuserform = ChuserForm(initial={'user': request.user.pk})
    
    bondecommandes = BonDeCommande.objects.all().filter_by_user(request.user)
    
    return render_to_response("common/client/infos.html", {
        "client": client,
        "clients": client_qs,
        "packageauth": packageauth,
        "chuserform": chuserform,
        "bondecommandes": bondecommandes,
    }, context_instance=RequestContext(request))

@login_required
def modify_client(request, client_id):
    user_client = request.user.my_userprofile.client
    if not user_client:
        raise Exception(u"Pas de client dans le profil pour l'utilisateur %s." % request.user)
    
    client = get_object_or_404(Client, pk=client_id)
    if not user_has_perms_on_client(request.user, client):
        raise PermissionDenied
    
    coordinate = client.coordinates or Coordinate()
    if request.method == "POST":
        client_form = ClientForm(request.POST, instance=client)
        coordinate_form = CoordinateForm(request.POST, instance=coordinate)
        if coordinate_form.is_valid() and client_form.is_valid():
            inst = coordinate_form.save()
            client.coordinates = inst
            client_form.save()
            #return redirect(reverse("common.views.modify_client"))
    else:
        client_form = ClientForm(instance=client)
        coordinate_form = CoordinateForm(instance=coordinate)
    IP_ADDRESS_REGEXP = re.compile(r"^(([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])\.){3}([0-9]|[1-9][0-9]|1[0-9]{2}|2[0-4][0-9]|25[0-5])$")
    host_list = HostChar.objects.filter(client=client_id)
    ip_table = []
    for host in host_list:
        host_ip = host.host.ip.split()
        for ip in host_ip:
            if IP_ADDRESS_REGEXP.match(ip):
                ip_table.append([host.host,ip,host.host.type,host.host.id,host.name])
    
    host_list_configure = ip_table

    host_list_qs = Host.objects.filter_by_user(request.user)
    host_list_qs = host_list_qs.filter(site__in = Client.objects.get_childs('parent', client.id))

    return render_to_response("common/client/modify.html", {
        "client": client,
        "client_form": client_form,
        "coordinate_form": coordinate_form,
        "host_list_qs": host_list_qs,
        "host_list_configure": host_list_configure,
    }, context_instance=RequestContext(request))

@login_required
def trafiquable(request):
    if not request.is_ajax():
        return HttpResponse("This method may only be called via ajax")
    data = {}
    profile = request.user.my_userprofile
    action = request.POST.get('action','get')
    id_table = request.POST.get('id_table',None)
    if id_table is None:
        data['error'] = u"Pas d'id table"
    else:
        if action == 'save':
            ordre_colonnes = json.loads(request.POST.get('liste_colonnes', None))
            if ordre_colonnes is None:
                data['error'] = u"Pas d'ordre_colonnes"
            else:
                profile.set_trafiquable(id_table, ordre_colonnes)
        elif action == 'get':
            data['ordre_colonnes'] = profile.get_trafiquable(id_table)
    if data.has_key('error') and data['error']:
        return HttpResponseBadRequest(json.dumps(data))
    return HttpResponse(json.dumps(data))
