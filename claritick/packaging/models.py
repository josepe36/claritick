# -*- coding: utf-8 -*-

from django.core.validators import RegexValidator
from django.db import models
from django.db.models import permalink

from common.models import ClientField, Client
from packaging.storage import packaging_storage

packagename_validator = RegexValidator(r"^[-+_0-9a-z]{5,}$", message=u"Nom invalide.")

class ClientPackageAuth(models.Model):
    class Meta:
        verbose_name = u"Authorisations client/packages"
    
    client = models.ForeignKey(Client, verbose_name=u"Client", blank=False)
    key = models.CharField(max_length=64, unique=True, blank=False)
    
    def __unicode__(self):
        return u"Auth for %s" % (self.client,)
    
class Platform(models.Model):
    """system platform. linux-default, linux-xorgversion, win32-default, win32-5.1, ... """
    class Meta:
        verbose_name = u"Plateforme"

    name = models.CharField(max_length=256, verbose_name=u"Nom de la plateforme", blank=False)
    identifier = models.CharField(max_length=1024, verbose_name=u"Identification plateforme", blank=False)
    description = models.TextField(verbose_name=u"Description", blank=False)

    def __unicode__(self):
        return self.name and self.name or u"Toutes"

class PackageKind(models.Model):
    """ Exemples: CLARILAB, MCA, ... """
    class Meta:
        verbose_name = u"Type de programme"

    name = models.CharField(max_length=64, verbose_name=u"Nom du package")

    def __unicode__(self):
        return self.name

class PackageTemplate(models.Model):
    class Meta:
        verbose_name = u"Modèle de paquet"

    kind = models.ForeignKey(PackageKind, verbose_name=u"Type de package", blank=False)    
    name = models.CharField(max_length=256, verbose_name=u"Nom du paquet", blank=False, validators = [ packagename_validator, ])
    short_description = models.CharField(max_length=64, verbose_name=u"Description courte", blank=False)
    description = models.TextField(verbose_name=u"Description Longue", null=True, blank=True)
    #~ client_independant = models.BooleanField(verbose_name=u"Indépendant du client", default=True)
    
    def __unicode__(self):
        return u"%s %s" % (self.kind, self.name)

class Package(models.Model):
    class Meta:
        verbose_name = u"Paquet"
        permissions = (
            ("can_access", u"Accès au système de gestion de paquet"),
        )
    
    template = models.ForeignKey(PackageTemplate, verbose_name=u"Modèle", blank=False)
    client = ClientField(Client, verbose_name=u"Client", blank=False)
    platform = models.ForeignKey(Platform, verbose_name=u"Plateforme", blank=True, null=True)
    date_add = models.DateTimeField(verbose_name=u"Date d'ajout",auto_now_add=True, blank=False)
    version_major = models.PositiveIntegerField(verbose_name=u"Majeur de version", blank=False)
    version_minor = models.PositiveIntegerField(verbose_name=u"Mineur de version", blank=False)
    revision = models.PositiveIntegerField(verbose_name=u"Release", blank=False, default=0)
    required = models.BooleanField(verbose_name=u"Requis", default=True)
    
    file = models.FileField(upload_to=".", storage=packaging_storage, blank=True, null=True)
    
    def __unicode__(self):
        # LC: Do never use and or trick to return "False" value.
        if not self.file:
            fileStr = " (No file attached)"
        else:
            fileStr = ""
        
        return u"%s pour %s %s%s%s" % (self.template.name, self.client, 
            self.version, 
            self.platform and u" plateforme %s" % (self.platform,) or u" toute plateforme",
            fileStr)
    
    @property
    def version(self):
        return u"%s.%s+%s" % (self.version_major, self.version_minor, self.revision)
    
    @property
    def sha1(self):
        digest = None
        if self.file:
            storage = self.file.storage
            if storage:
                digest = storage.sha1(self.file.name)
        return digest

    @permalink
    def download_url(self):
        return ('packaging_get_id', [ unicode(self.id), ])
