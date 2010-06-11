# -*- coding: utf-8 -*-

import qsstats
import datetime

from django import http
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
from django.db import models
from django.db import connection, transaction
from django.shortcuts import render_to_response, get_object_or_404, redirect
from django.template import RequestContext
from django.contrib.auth.decorators import login_required, permission_required
from django.core.urlresolvers import reverse

import django.contrib.comments
from django.contrib.comments.views.comments import post_comment

from dojango.decorators import json_response

from ticket.models import Ticket, TicketView, TicketFile
from ticket.forms import *

from common.diggpaginator import DiggPaginator
from common.models import Client, UserProfile, ClaritickUser
from common.exceptions import NoProfileException
from common.utils import user_has_perms_on_client

from backlinks.decorators import backlink_setter

INVALID_TITLE = "Invalid title"

def get_filters(request):
    if "list_filters" in request.session:
        return request.session["list_filters"]
    return {}

def set_filters(request, datas=None):
    if not "list_filters" in request.session:
        request.session["list_filters"] = {}
    if request.method == "POST":
        request.session["list_filters"] = request.POST.copy()
    if datas:
        request.session["list_filters"].update(datas)

def get_context(request):
    """
        Context commun aux listes de tickets.
    """
    return {
        "TICKET_STATE_CLOSED": settings.TICKET_STATE_CLOSED,
        "sort_order": int(not int(request.GET.get("sort_order", 1)))
    }

def get_pagination(queryset, request):
    """
        Mets en place la pagination via DiggPaginator.
    """
    paginator = DiggPaginator(queryset, settings.TICKETS_PER_PAGE, body=5, tail=2, padding=2)
    return paginator.page(request.GET.get("page", 1))

@login_required
@backlink_setter
def list_me(request, *args, **kw):
    form = None
    if not request.POST.get("assigned_to", None):
        form = SearchTicketForm({'assigned_to': request.user.id}, get_filters(request), user=request.user)
        set_filters(request, form.data)
    return list_all(request, form, *args, **kw)

@login_required
@backlink_setter
def list_unassigned(request, *args, **kw):
    filterdict = {'assigned_to__isnull': True}
    return list_all(request, None, filterdict = filterdict, *args, **kw)

@login_required
@backlink_setter
def list_nonvalide(request):
    """
        Liste des tickets à valider.
    """
    filterdict = {"validated_by__isnull": True}
    return list_all(request, filterdict=filterdict)

@login_required
@backlink_setter
def list_view(request, view_id=None):
    context = get_context(request)
    data = request.POST

    # On charge la vue de la liste
    if view_id:
        view = get_object_or_404(TicketView, pk=view_id, user=request.user)
        if request.method == "POST" and request.POST.get("validate-filters", None):
            if request.POST.get("delete_view", None):
                view.delete()
                return redirect("ticket_list_view")
            data = request.POST.copy()
        else:
            data = view.filters
            data.update({"view_name": view.name})
        context["view"] = view

    # le form de filtres
    form = SearchTicketViewForm(data, user=request.user)

    # le template a charger
    if request.user.has_perm("ticket.can_list_all") or request.user.is_superuser:
        template_name = "ticket/view.html"
    else:
        template_name = "ticket/view_small.html"

    # le form d'actions
    if request.user.has_perm("ticket.can_list_all") or request.user.is_superuser:
        action_form = TicketActionsForm(request.POST, prefix="action")
    else:
        action_form = TicketActionsSmallForm(request.POST, prefix="action")

    if action_form.process_actions(request):
        return http.HttpResponseRedirect("%s?%s" % (request.META["PATH_INFO"], request.META["QUERY_STRING"]))

    if not data.get("state"):
        qs = Ticket.open_tickets.filter(parent__isnull=True)
        cqs = Ticket.open_tickets.filter(parent__isnull=False)
    else:
        qs = Ticket.tickets.filter(parent__isnull=True)
        cqs = Ticket.tickets.filter(parent__isnull=False)

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
    filters = data.copy()
    if not request.user.has_perm("ticket.can_list_all") and data.get("text"):
        qs = qs.filter_or_child(models.Q(title__icontains=data["title"]) | models.Q(text__icontains=data["text"]))
        del filters["text"]
    qs = qs.filter_queryset(filters)

    # On va filtrer la liste des tickets en fonction de la relation user => client
    qs = qs.filter_ticket_by_user(request.user)
    cqs = cqs.filter_ticket_by_user(request.user)

    # Le tri
    qs = qs.add_order_by(request)
    cqs = cqs.add_order_by(request)

    context.update({
        "form": form,
        "action_form": action_form,
        "tickets": get_pagination(qs.get_and_child(cqs), request),
    })

    return render_to_response(template_name, context, context_instance=RequestContext(request))

@login_required
@backlink_setter
def list_all(request, form=None, filterdict=None, template_name=None, *args, **kw):
    """
        Liste tous les tickets sans aucun filtre
    """
    context = get_context(request)

    if request.user.has_perm("can_commit_full") or request.user.is_superuser:
        action_form = TicketActionsForm(request.POST, prefix="action")
    else:
        action_form = TicketActionsSmallForm(request.POST, prefix="action")

    if action_form.process_actions(request):
        return http.HttpResponseRedirect("%s?%s" % (request.META["PATH_INFO"], request.META["QUERY_STRING"]))

    if request.GET.get("reset", False) and request.session.get("list_filters", {}):
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
        qs = Ticket.open_tickets.filter(parent__isnull=True)
        cqs = Ticket.open_tickets.filter(parent__isnull=False)
    else:
        qs = Ticket.tickets.filter(parent__isnull=True)
        cqs = Ticket.tickets.filter(parent__isnull=False)


    # Form cleaned_data ?
    if form.is_valid():
        data = form.cleaned_data.copy()
        if not request.user.has_perm("ticket.can_list_all") and form.cleaned_data["text"]:
            qs = qs.filter_or_child(models.Q(title__icontains=form.cleaned_data["text"]) | models.Q(text__icontains=form.cleaned_data["text"]))
            del data["text"]
        qs = qs.filter_queryset(data)
        if data['state']:
            cqs = cqs.filter(state=data['state'])

    # unassigned / nonvalide
    if filterdict:
        qs = qs.filter_or_child(filterdict)
        cqs = cqs.filter(**filterdict)

    # On va filtrer la liste des tickets en fonction de la relation user => client
    qs = qs.filter_ticket_by_user(request.user)
    cqs = cqs.filter_ticket_by_user(request.user)

    # Le tri
    qs = qs.add_order_by(request)
    cqs = cqs.add_order_by(request)

    # TODO choisir le bon template en fonction des permissions
    if template_name is None:
        if request.user.has_perm("ticket.can_list_all") or request.user.is_superuser:
            template_name = "ticket/list.html"
        else:
            template_name = "ticket/list_small.html"

    context.update({
        "form": form, 
        "action_form": action_form,
        "tickets": get_pagination(qs.get_and_child(cqs), request),
    })
    return render_to_response(template_name or "ticket/list.html", context, context_instance=RequestContext(request))

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
    ticket.title = INVALID_TITLE
    #ticket.state = None
    ticket.state = State.objects.get(pk=settings.TICKET_STATE_NEW)
    ticket.priority = Priority.objects.get(pk=settings.TICKET_PRIORITY_NORMAL)
    
    if request.user.has_perm("ticket.add_ticket_full"):
        ticket.validated_by = request.user

    ticket.save()
    return redirect("ticket_modify", ticket_id=ticket.pk)

@permission_required("ticket.change_ticket")
@login_required
def modify(request, ticket_id):
    def exit_action():
        saveaction = request.POST.get("savebutton", "save")
        if saveaction == "save":
            return redirect("ticket_modify", ticket_id=ticket_id)
        elif saveaction == "new":
            return redirect("ticket_partial_new")
        elif saveaction == "return":
            backlinks = request.backlinks
            precedent = backlinks[-1:]
            if not precedent:
                return redirect("ticket_modify", ticket_id=ticket_id) 
            else:
                return precedent[0].redirect(request)
        else:
            raise PermissionDenied("Hacking attempt!")
    
    ticket = get_object_or_404(Ticket, pk=ticket_id)

    # Si c'est un fils rediriger vers le pêre au bon endroit
    if ticket.parent:
        return http.HttpResponseRedirect("/ticket/modify/%d/#child%s" % (ticket.parent_id, ticket_id))

    # On verifie que l'utilisateur a les droits de modifier le ticket_id
    if not user_has_perms_on_client(request.user, ticket.client):
        raise PermissionDenied

    if not ticket.text and ticket.title == INVALID_TITLE:
        ticket.title = None

    # Si le ticket n'est pas rattaché à aucun client, on l'affecte au client de l'utilisateur
    if not ticket.client:
        ticket.client = request.user.get_profile().client

    if request.user.has_perm("ticket.add_ticket_full"):
        template_name = "ticket/modify.html"
        TicketForm = NewTicketForm
    else:
        template_name = "ticket/modify_small.html"
        TicketForm = NewTicketSmallForm

    child_form = [(c, ChildForm(user=request.user, instance=c, auto_id='id_child'+str(c.id)+'_%s'),\
            django.contrib.comments.get_form()(c)) for c in ticket.child.order_by('date_open')]

    if request.method == "POST":
        if request.POST.get("_validate-ticket", None) and request.user.has_perm("ticket.can_validate_ticket")\
            and ticket.validated_by is None:
            ticket.validated_by = request.user
            ticket.save()
        form = TicketForm(request.POST, request.FILES, instance=ticket, user=request.user)
        comment_form = django.contrib.comments.get_form()(ticket) # Initialization vide
        if not request.POST.get("submit-comment", None): # Post du commentaire uniquement ?
            if form.is_valid():
                # Si l'utilisateur peut assigner ce ticket à l'utilisateur passé en POST
                if not request.user.is_superuser and form.cleaned_data["assigned_to"] and form.cleaned_data["assigned_to"]\
                        not in ClaritickUser.objects.get(pk=request.user.pk).get_child_users():
                    raise PermissionDenied()
                form.save()
                file = form.cleaned_data["file"]
                if file:
                    ticket_file = TicketFile(ticket=ticket, filename=file.name, content_type=file.content_type)
                    if file.multiple_chunks():
                        data = None
                        for chunk in file.chunks():
                            data += chunk
                    else:
                        data = file.read()
                    ticket_file.data = data
                    ticket_file.save()
                
                # Peut être qu'il ya en meme temps un commentaire
                comment_form = django.contrib.comments.get_form()(ticket, data=request.POST)
                if comment_form.is_valid():
                    post_comment(request)
                
                comment_form = django.contrib.comments.get_form()(ticket) # Initialization vide
                return exit_action()
        else:
            comment_form = django.contrib.comments.get_form()(ticket, data=request.POST)
            if comment_form.is_valid():
                post_comment(request)
                return exit_action()
    else:
        form = TicketForm(instance=ticket, user=request.user)
        comment_form  = django.contrib.comments.get_form()(ticket)
    
    # Just open
    return render_to_response(template_name, { "form": form, "ticket": ticket, "comment_form": comment_form, "child_form": child_form },
        context_instance=RequestContext(request))

@login_required
def get_file(request, file_id):
    """
        Retourne au client le TicketFile file_id avec le bon mimetype.
    """
    file = get_object_or_404(TicketFile, pk=file_id)
    
    if not user_has_perms_on_client(request.user, file.ticket.client):
        raise PermissionDenied
    response = http.HttpResponse(str(file.data), mimetype=file.content_type)
    response["Content-Disposition"] = "attachment; filename=%s" % file.filename
    return response

@permission_required("ticket.add_child")
@login_required
def ajax_new_child(request, ticket_id):
    """
    Crée un nouveau ticket fils de ticket_id
    Renvoie un formulaire HTML
     -> Formulaire modification fils si réussite (dans ce cas on
        envoie un X-Claritick-Tid avec l'id du fils crée
     -> Formulaire de création + erreur si echec avec les id de
        <div> et <form> mis à X-Claritick-Tid (envoyé par le client ajax)
    status = 201 si fils crée, sinon 200 (utilisé par le js de ticket/modify.html derière)
    """
    if not ticket_id: 
        raise PermissionDenied
    ticket = get_object_or_404(Ticket, pk=ticket_id)

    if not user_has_perms_on_client(request.user, ticket.client):
        raise PermissionDenied

    if ticket.parent:
        raise PermissionDenied("Ce ticket est déjà un fils")

    form = ChildForm(request.POST, user=request.user, auto_id="id_child_%s")
    if form.is_valid():
        child = copy_model_instance(ticket)
        child.state = form.cleaned_data['state']
        child.assigned_to = form.cleaned_data['assigned_to']
        child.title = form.cleaned_data['title']
        child.text = form.cleaned_data['text']
        child.validated_by = request.user
        child.keywords = form.cleaned_data['keywords']
        child.category = form.cleaned_data['category']
        child.opened_by = request.user
        child.date_open = datetime.datetime.now()
        child.parent = ticket
        child.project = form.cleaned_data['project']
        child.save()
        form = ChildForm(instance=child, user=request.user, auto_id="id_child"+str(child.id)+"_%s")
        form_comment = django.contrib.comments.get_form()(child)
        ret =  render_to_response("ticket/child.html",
                {"child": child, "cf": form, "cfc": form_comment },
                context_instance=RequestContext(request))
        ret["X-Claritick-Tid"] = "child%s" % (child.id)
        ret.status_code = 201 # created
    else:
        ret =  render_to_response("ticket/child.html",
                {"ticket": ticket, "cf": form, "new_child": True, "child_id": request.META["HTTP_X_CLARITICK_TID"]},
                context_instance=RequestContext(request))
    return ret

@permission_required("ticket.change_child")
@login_required
def ajax_modify_child(request, ticket_id):
    """
    Modifie ticket_id et renvoie le formulaire de
    modification + éventuelles erreurs
    """
    if not ticket_id:
        raise PermissionDenied
    ticket = get_object_or_404(Ticket, pk=ticket_id)

    if not user_has_perms_on_client(request.user, ticket.client) or not ticket.parent: # must be a child
        raise PermissionDenied

    form = ChildForm(request.POST, user=request.user, instance=ticket, auto_id="id_child_%s");
    form_comment = django.contrib.comments.get_form()(ticket, data=request.POST)

    if form_comment.is_valid():
        post_comment(request)

    form_comment = django.contrib.comments.get_form()(ticket)

    if form.is_valid():
        form.save()
        ret = render_to_response("ticket/child.html", {"child": ticket, "cf": form, "cfc": form_comment },
                context_instance=RequestContext(request))
        ret.status_code = 201
    else:
        ret = render_to_response("ticket/child.html", {"child": ticket, "cf": form, "cfc": form_comment },
                context_instance=RequestContext(request))
    return ret

@permission_required("ticket.add_child")
@login_required
def ajax_load_child(request, ticket_id):
    """
    Renvoie un formulaire HTML pour création d'un fils de ticket_id
    l'ID du <div> et <form> est construit à partir de X-Claritick-Tid
    """
    if not ticket_id:
        raise PermissionDenied
    ticket = get_object_or_404(Ticket, pk=ticket_id)

    if not user_has_perms_on_client(request.user, ticket.client):
        raise PermissionDenied
    if ticket.parent:
        raise PermissionDenied("Ce ticket est déjà un fils")

    form = ChildForm(user=request.user,
            initial={'state': ticket.state_id, 'category': ticket.category_id, 'project': ticket.project_id},
            auto_id="id_child_%s")
    return render_to_response('ticket/child.html',
            {"ticket": ticket, "cf": form, "new_child": True, "child_id": request.META["HTTP_X_CLARITICK_TID"] },
            context_instance=RequestContext(request))

@login_required
@json_response
def ajax_load_telephone(request):
    """
    Renvoie un json contenant les numéros uniques de téléphone/dernier numéro de téléphone du client/enfants
    """
    
    ret = {}
    
    client_id = request.POST.get("client_id", None)
    if not client_id:
        raise PermissionDenied
    
    client = get_object_or_404(Client, pk=client_id)
    if not user_has_perms_on_client(request.user, client):
        raise PermissionDenied
    
    # Récupère la liste des numéros
    telephones = []
    strings = []

    if settings.POSTGRESQL_VERSION >= 8.4:
        client_and_childs = Client.objects.get_childs("parent", client.pk)
    else:
        client_and_childs = [ client, ]
    
    for client in client_and_childs:
        coord = client.coordinates
        if coord and coord.telephone:
            coord_supp = ''
            if coord.postalcode or coord.city:
                coord_supp += ' (Labo '
                if coord.postalcode:
                    coord_supp += str(coord.postalcode)
                if coord.city:
                    coord_supp += ' ' + str(coord.city)
                coord_supp += ')'
            telephones.append(str(coord.telephone))
            strings.append("%s%s"% (coord.telephone, coord_supp))

    # Récupère la liste des derniers tickets
    tickets = Ticket.tickets.filter(parent__isnull=True).filter(client__in=client_and_childs)
    tickets = tickets.exclude(telephone__isnull=True).exclude(telephone='')
    tickets = tickets.filter_ticket_by_user(request.user).order_by("-id")

    for ticket in tickets:
        if not ticket.telephone in telephones:
            telephones.append(str(ticket.telephone))
            strings.append("%s (Ticket %s de %s)" % (ticket.telephone, ticket.id, ticket.client))
            if len(telephones) == 5:
                break

    ret["telephones"] = [(t,s) for t,s in zip(telephones, strings)]
    return ret

@login_required
@json_response
def ajax_graph_permonth(request):
    """
    
    """
    ret = {}
    
    today = datetime.datetime.now()
    qs = Ticket.objects.all()
    qs = qs.filter_ticket_by_user(request.user)
    if not qs:
        return ret
    
    ret["charts"] = []
    
    def get_chart(tss, series_properties):
        chart = {}
        chart["y_values"] = [ t[1] for t in tss ]
        chart["x_labels"] = [
            {'value': idx+1, 'text': t[0].strftime("%b")} \
            for idx, t in enumerate(tss)
        ]
        chart["series_properties"] = series_properties
        return chart
    
    ## Opened ticket chart
    qss = qsstats.QuerySetStats(qs, 'date_open')
    tss = qss.time_series(today-datetime.timedelta(days=360), today, interval='months')
    ret["charts"].append(get_chart(tss, series_properties = {'legend': 'Tickets ouverts'}))
    
    ## Critical tickets chart
    chart = {}
    qs = qs.filter(priority__gt=3)
    if not qs:
        return {}
    qss = qsstats.QuerySetStats(qs, 'date_open')
    tss = qss.time_series(today-datetime.timedelta(days=360), today, interval='months')
    ret["charts"].append(get_chart(tss, series_properties = {'legend': 'Tickets critiques', 'stroke': 'red'}))

    return ret

@login_required
@json_response
def ajax_graph_average_close_time(request):
    """
    
    Returns data for generating "average close time" graph
    """
    ret = {}
    
    if not request.user.is_staff:
        client_list = request.user.get_profile().get_clients()
        filterquery = """AND ticket_ticket.client_id IN (%s)""" % (",".join(map(str, [ c.id for c in client_list ])),)
    else:
        filterquery = ""
    
    rawquery = """SELECT 
        extract('epoch' from AVG((date_close - date_open)::interval)) AS delay, 
        date_trunc('month', date_open) AS date,
        priority_id
    FROM 
        ticket_ticket 
    WHERE
        state_id = 4
    AND
        date_open > (now() - interval '1 year')
    AND
        ticket_ticket.id NOT IN (SELECT id FROM ticket_ticket WHERE (date_close-date_open) > interval '40 days')
    %s
    GROUP BY 
        date, priority_id
    HAVING
        AVG((date_close - date_open)::interval) > interval '0'
    ORDER BY
        priority_id, date;""" % (filterquery,)
    
    today = datetime.datetime.now()
    current_month = today.month
    mapping = [ ((i+current_month) % 12)+1 for i in range(0,12) ]
    text_mapping = ("Jan", "Fev", "Mar", "Avr", "Mai", "Jun", "Jul", "Aou", "Sep", "Oct", "Nov", "Dec")
    
    def get_chart(serie, properties):
        chart = {}
        chart["values"] = [ {'x': mapping.index(s[1].month), 'y': s[0]/3600} for s in serie ] # En heures
        chart["properties"] = properties
        return chart
    
    cursor = connection.cursor()
    cursor.execute(rawquery)
    data = cursor.fetchall()
    #data = [(850743.80952400004, datetime.datetime(2009, 7, 1, 0, 0), 1), (5205087.4000000004, datetime.datetime(2009, 8, 1, 0, 0), 1), (28206.0, datetime.datetime(2009, 9, 1, 0, 0), 1), (143188.5, datetime.datetime(2009, 11, 1, 0, 0), 1), (127069.333333, datetime.datetime(2009, 12, 1, 0, 0), 1), (162324.0, datetime.datetime(2010, 1, 1, 0, 0), 1), (1894222.096102, datetime.datetime(2010, 3, 1, 0, 0), 1), (522988.93457899999, datetime.datetime(2009, 7, 1, 0, 0), 2), (547603.640288, datetime.datetime(2009, 8, 1, 0, 0), 2), (368607.906716, datetime.datetime(2009, 9, 1, 0, 0), 2), (561494.17058799998, datetime.datetime(2009, 10, 1, 0, 0), 2), (623945.57837700006, datetime.datetime(2009, 11, 1, 0, 0), 2), (647219.15001900005, datetime.datetime(2009, 12, 1, 0, 0), 2), (399448.89853300003, datetime.datetime(2010, 1, 1, 0, 0), 2), (507396.04899099999, datetime.datetime(2010, 2, 1, 0, 0), 2), (204780.30123700001, datetime.datetime(2010, 3, 1, 0, 0), 2), (222393.817759, datetime.datetime(2010, 4, 1, 0, 0), 2), (1595656.538462, datetime.datetime(2009, 7, 1, 0, 0), 3), (600649.68421099999, datetime.datetime(2009, 8, 1, 0, 0), 3), (287347.47619000002, datetime.datetime(2009, 9, 1, 0, 0), 3), (746089.95833299996, datetime.datetime(2009, 10, 1, 0, 0), 3), (614552.60089300002, datetime.datetime(2009, 11, 1, 0, 0), 3), (289317.22395800002, datetime.datetime(2009, 12, 1, 0, 0), 3), (367416.75990300003, datetime.datetime(2010, 1, 1, 0, 0), 3), (148866.46093199999, datetime.datetime(2010, 2, 1, 0, 0), 3), (181966.69768000001, datetime.datetime(2010, 3, 1, 0, 0), 3), (72059.588652999999, datetime.datetime(2010, 4, 1, 0, 0), 3), (1288154.0, datetime.datetime(2009, 7, 1, 0, 0), 4), (10974.5, datetime.datetime(2009, 9, 1, 0, 0), 4), (479802.11111100001, datetime.datetime(2009, 10, 1, 0, 0), 4), (357279.33333300002, datetime.datetime(2009, 11, 1, 0, 0), 4), (1157326.5, datetime.datetime(2009, 12, 1, 0, 0), 4), (482023.45454499999, datetime.datetime(2010, 1, 1, 0, 0), 4), (26748.099999999999, datetime.datetime(2010, 2, 1, 0, 0), 4), (890311.0, datetime.datetime(2010, 3, 1, 0, 0), 4), (220048.82686900001, datetime.datetime(2010, 4, 1, 0, 0), 4)]
    transaction.commit_unless_managed()
    if not data:
        return ret
    
    serie = []
    series = []
    old_priority = data[0][2]
    for d in data:
        if d[2] != old_priority:
            if serie:
                series.append(serie)
            old_priority = d[2]
            serie = []
        serie.append(d)
    
    if serie:
        series.append(serie)
    ret["series"] = [ get_chart(serie, 
        properties = {
            "legend": u"Priorité %s" % (serie[0][2],),
#            "color": Priority.objects.get(pk=int(serie[0][2])).forecolor,
#            "stroke": Priority.objects.get(pk=int(serie[0][2])).forecolor
        }) for serie in series ]
    
    ret["x_labels"] = [ {'value': idx+1, 'text': text_mapping[month-1]} for idx, month in enumerate(mapping) ]
    
    return ret
