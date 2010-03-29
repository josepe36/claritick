# -*- coding: utf-8 -*-

from django import http
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied, FieldError
from django.db import models
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.template.loader import render_to_string
from django.utils.html import escape
from django.contrib.auth.decorators import login_required, permission_required
from django.conf import settings
from django.views.generic import list_detail
from django.utils import simplejson
from django.core.urlresolvers import reverse

from claritick.ticket.models import Ticket, TicketView
from claritick.ticket.forms import *
from claritick.ticket.tables import DefaultTicketTable

from claritick.common.diggpaginator import DiggPaginator
from claritick.common.models import Client, UserProfile
from common.exceptions import NoProfileException
from common.utils import user_has_perms_on_client

def get_filters(request):
    return request.session["list_filters"]

def set_filters(request, datas=None):
    if not "list_filters" in request.session:
        request.session["list_filters"] = {}
    if request.method == "POST":
        request.session["list_filters"] = request.POST.copy()
    if datas:
        request.session["list_filters"].update(datas)

def filter_quersyset(qs, filters):
    """
        Filtre un queryset de ticket a partir d'un dictionnaire de fields lookup.
    """
    search_mapping = {
        'title': 'icontains',
        'text': 'icontains',
        'contact': 'icontains',
        'keywords': 'icontains',
    }

    d = {}
    for key, value in filters.items():
        try:
            if value:
                try:
                    lookup = search_mapping[key]
                except KeyError:
                    if isinstance(value, (list, models.query.QuerySet)):
                        lookup = "in"
                    else:
                        lookup = 'exact'
                qs = qs.filter(**{"%s__%s"%(str(key),lookup): value})
        except (AttributeError, FieldError):
            pass

    return qs

def filter_ticket_by_user(qs, user):
    """
        Filtre un queryset de ticket en fonction des clients qu'a le droit de voir l'utilisateur.
    """
    try:
        client_list = user.get_profile().get_clients()
        qs = qs.filter(client__pk__in=[x.id for x in client_list])
    except UserProfile.DoesNotExist:
        raise NoProfileException(request.user)

    return qs

@login_required
def list_me(request, *args, **kw):
    form = None
    if not request.POST.get("assigned_to", None):
        form = SearchTicketForm({'assigned_to': request.user.id}, get_filters(request), user=request.user)
        set_filters(request, form.data)
    return list_all(request, form, *args, **kw)

@login_required
def list_unassigned(request, *args, **kw):
    filterdict = {'assigned_to__isnull': True}
    #set_filters(request, filterdict)
    return list_all(request, None, filterdict = filterdict, *args, **kw)

@login_required
def list_view(request, view_id=None):
    context = {}
    data = request.POST

    # On charge la vue de la liste
    if view_id:
        view = get_object_or_404(TicketView, pk=view_id, user=request.user)
        if request.method == "POST" and request.POST.get("validate-filters", None):
            data = request.POST.copy()
        else:
            data = view.filters
            data.update({"view_name": view.name})
            #request.session["list_filters"] = data
        context["view"] = view

    # le form de filtres
    form = SearchTicketViewForm(data, user=request.user)

    # le template a charger
    if request.user.has_perm("can_commit_full") or request.user.is_superuser:
        template_name = "ticket/view.html"
    else:
        template_name = "ticket/view_small.html"

    # le form d'actions
    if request.user.has_perm("can_commit_full") or request.user.is_superuser:
        action_form = TicketActionsForm(request.POST, prefix="action")
    else:
        action_form = TicketActionsSmallForm(request.POST, prefix="action")

    if action_form.process_actions():
        return http.HttpResponseRedirect("%s?%s" % (request.META["PATH_INFO"], request.META["QUERY_STRING"]))

    if not data.get("state"):
        qs = Ticket.open_tickets.all()
    else:
        qs = Ticket.tickets.all()
    
    # On va enregistrer les criteres actuels en tant que nouvelle liste
    if request.method == "POST" and form.is_valid():
        if view_id:
            TicketView.objects.filter(pk=view_id).update(
                name=form.cleaned_data["view_name"],
                filters=form.cleaned_data
            )
        else:
            t = TicketView.objects.create(
                user=request.user,
                name=form.cleaned_data["view_name"],
                filters=form.cleaned_data
            )


        if request.POST.get("validate-filters", None):
            return redirect("ticket_list_view", view_id=view_id or t.pk)

    # On filtre la liste a partir des datas de la vue
    qs = filter_quersyset(qs, data)

    # On va filtrer la liste des tickets en fonction de la relation user => client
    qs = filter_ticket_by_user(qs, request.user)

    # Le tri
    qs = qs.order_by(request.GET.get('sort', '-id'))

    context.update({
        "form": form,
        "action_form": action_form,
    })

    return list_detail.object_list(request, queryset=qs,  paginate_by=settings.TICKETS_PER_PAGE, page=request.GET.get("page", 1),
        template_name=template_name, extra_context=context)

@login_required
def list_all(request, form=None, filterdict=None, template_name=None, context={}, *args, **kw):
    """
        Liste tous les tickets sans aucun filtre
    """
    if request.user.has_perm("can_commit_full") or request.user.is_superuser:
        action_form = TicketActionsForm(request.POST, prefix="action")
    else:
        action_form = TicketActionsSmallForm(request.POST, prefix="action")

    if action_form.process_actions():
        return http.HttpResponseRedirect("%s?%s" % (request.META["PATH_INFO"], request.META["QUERY_STRING"]))

    if request.GET.get("reset", False):
        request.session["list_filters"] = {}
        return http.HttpResponseRedirect(".")

    if not form:
        if request.method == "POST" and request.POST.get("validate-filters", None):
            form = SearchTicketForm(request.POST, user=request.user)
            if form.is_valid():
                set_filters(request, filterdict)
        else:
            form = SearchTicketForm(get_filters(request), user=request.user)

    if not get_filters(request).get("state"):
        qs = Ticket.open_tickets.all()
    else:
        qs = Ticket.tickets.all()

    # Form cleaned_data ?
    if form.is_valid():
        qs = filter_quersyset(qs, form.cleaned_data)

    # unassigned
    if filterdict:
        qs = qs.filter(**filterdict)

    # On va filtrer la liste des tickets en fonction de la relation user => client
    qs = filter_ticket_by_user(qs, request.user)

    # Le tri
    qs = qs.order_by(request.GET.get('sort', '-id'))

    # TODO choisir le bon template en fonction des permissions
    if template_name is None:
        if request.user.has_perm("can_commit_full") or request.user.is_superuser:
            template_name = "ticket/list.html"
        else:
            template_name = "ticket/list_small.html"

    context.update({
        "form": form, 
        "action_form": action_form,
    })

    return list_detail.object_list(request, queryset=qs,  paginate_by=settings.TICKETS_PER_PAGE, page=request.GET.get("page", 1),
        template_name=template_name or "ticket/list.html", extra_context=context)

@permission_required("ticket.add_ticket")
@login_required
def partial_new(request, form=None):
    """
    Create a new ticket.
    """
    if not form:
        form = PartialNewTicketForm()
    return render_to_response('ticket/partial_new.html', {'form': form }, context_instance=RequestContext(request))

@permission_required("ticket.add_ticket")
@login_required
def new(request):
    """
    Create a new ticket.
    """
    
    form = PartialNewTicketForm(request.POST)
    if not form.is_valid():
        return partial_new(request, form)
    
    ticket = form.save(commit=False)
    ticket.opened_by = request.user
    ticket.title = "Invalid title"
    #ticket.state = None
    ticket.state = State.objects.get(pk=settings.TICKET_STATE_NEW)
    ticket.priority = Priority.objects.get(pk=settings.TICKET_PRIORITY_NORMAL)
    ticket.save()
    return redirect("ticket_modify", ticket_id=ticket.pk)

@permission_required("ticket.change_ticket")
@login_required
def modify(request, ticket_id):
    ticket = get_object_or_404(Ticket, pk=ticket_id)

    # On verifie que l'utilisateur a les droits de modifier le ticket_id
    if not user_has_perms_on_client(request.user, ticket.client):
        raise PermissionDenied

    if not ticket.text:
        ticket.title = None
        #ticket.state = State.objects.get(pk=settings.TICKET_STATE_NEW)
        #ticket.priority = Priority.objects.get(pk=settings.TICKET_PRIORITY_NORMAL)
        ticket.validated_by = request.user
    
    if request.user.has_perm("ticket.add_ticket_full"):
        template_name = "ticket/modify.html"
        TicketForm = NewTicketForm
    else:
        template_name = "ticket/modify_small.html"
        TicketForm = NewTicketSmallForm

    if request.method == "POST":
        # TODO avant de sauver le ticket, retirer du request.POST toutes les infos que l'utilisateur n'a pas le droit de modifier
        form = TicketForm(request.POST, instance=ticket, user=request.user)
        if form.is_valid():
            form.save()
    else:
        form = TicketForm(instance=ticket, user=request.user)

    return render_to_response(template_name, {"form": form, "ticket": ticket}, context_instance=RequestContext(request))
