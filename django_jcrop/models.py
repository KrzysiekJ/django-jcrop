#!/usr/bin/env python
#-*- coding:utf-8 -*-

from django.conf import settings
from django.contrib.admin.widgets import AdminFileWidget
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.core.files.storage import default_storage
from django.core.exceptions import ValidationError
from django.utils.translation import ugettext_lazy as _
from django.db import models
from django.template.loader import get_template
from django.template import Context
from django.utils.encoding import StrAndUnicode, force_unicode
from django.utils.html import escape, conditional_escape
from django.utils.safestring import mark_safe
from django import forms

import Image
from StringIO import StringIO

from django.utils.simplejson import loads


class ClearableFileInput(forms.ClearableFileInput):

    def __init__(self, *args, **kwargs):
        self.aspect_ratio = kwargs.pop('aspect_ratio', None)
        self.size = kwargs.pop('size', None)
        if self.size and not self.aspect_ratio:
            self.aspect_ratio = float(self.size[0]) / self.size[1]
        super(ClearableFileInput, self).__init__(*args, **kwargs)
            
    def value_from_datadict(self, data, files, name):
        if forms.CheckboxInput().value_from_datadict(data, files, "%s-crop" % name):
            #{"x":26,"y":40,"x2":320,"y2":150,"w":294,"h":110}
            forig = default_storage.open(data['%s-original' % name])
            im = Image.open(forig)
            w, h = im.size
            cdata = loads(data['%s-crop-data' % name])
            xr = 1. * w / cdata['image_width']
            yr = 1. * h / cdata['image_height']
            box = (cdata['x'] * xr, cdata['y'] * yr, cdata['x2'] * xr, cdata['y2'] * yr)
            box = map(int, box)
            crop = im.crop(box)
            if self.size:
                crop.thumbnail(self.size, Image.ANTIALIAS)
            sio = StringIO()
            crop.save(sio, im.format)
            sio.seek(0)
            size = len(sio.read())
            sio.seek(0)
            f = InMemoryUploadedFile(sio, name, forig.name, "image/%s" % im.format.lower(), size, "utf-8")
            files[name] = f

        upload = super(ClearableFileInput, self).value_from_datadict(data, files, name)
        if not self.is_required and forms.CheckboxInput().value_from_datadict(
            data, files, self.clear_checkbox_name(name)):
            if upload:
                # If the user contradicts themselves (uploads a new file AND
                # checks the "clear" checkbox), we return a unique marker
                # object that FileField will turn into a ValidationError.
                return forms.FILE_INPUT_CONTRADICTION
            # False signals to clear any existing value, as opposed to just None
            return False
        return upload


class JCropAdminImageWidget(ClearableFileInput):
    template_with_initial = (u'<p class="file-upload">%s</p>'
                            % ClearableFileInput.template_with_initial)
    template_with_clear = (u'<span class="clearable-file-input">%s</span>'
                           % ClearableFileInput.template_with_clear)

    class Media:
        js = (settings.STATIC_URL + "django_jcrop/js/jquery.Jcrop.min.js",
              settings.STATIC_URL + "django_jcrop/js/jquery.json-2.3.min.js", )
        css = {"all": (settings.STATIC_URL + "django_jcrop/css/jquery.Jcrop.css", )}

    def render(self, name, value, attrs=None):
        JCROP_IMAGE_WIDGET_DIMENSIONS = getattr(settings, "JCROP_IMAGE_WIDGET_DIMENSIONS", "320x320")
        JCROP_IMAGE_THUMBNAIL_DIMENSIONS = getattr(settings, "JCROP_IMAGE_THUMBNAIL_DIMENSIONS", "62x62")        
        
        substitutions = {
            'initial_text': self.initial_text,
            'input_text': self.input_text,
            'clear_template': '',
            'clear_checkbox_label': self.clear_checkbox_label,
            'aspect_ratio': self.aspect_ratio,
            'size': list(self.size)
        }
        template = u'%(input)s'
        substitutions['input'] = super(forms.ClearableFileInput, self).render(name, value, attrs)

        if value and hasattr(value, "url"):
            template = self.template_with_initial
            substitutions['input_name'] = name
            substitutions['image_value'] = value
            substitutions['image_url'] = value.url
            substitutions['initial'] = (u'<a href="%s">%s</a>'
                                        % (escape(value.url),
                                           escape(force_unicode(value))))

            widget_dimensions = [int(dim) for dim in JCROP_IMAGE_WIDGET_DIMENSIONS.split("x")]
            scale_ratio = min(float(widget_dimensions[0])/value.width, float(widget_dimensions[1])/value.height)
            substitutions['min_size'] = [scale_ratio*dim for dim in self.size]
            
            if not self.is_required:
                checkbox_name = self.clear_checkbox_name(name)
                checkbox_id = self.clear_checkbox_id(checkbox_name)
                substitutions['clear_checkbox_name'] = conditional_escape(checkbox_name)
                substitutions['clear_checkbox_id'] = conditional_escape(checkbox_id)
                substitutions['clear'] = forms.CheckboxInput().render(checkbox_name, False, attrs={'id': checkbox_id})
                substitutions['clear_template'] = self.template_with_clear % substitutions
        else:
            return mark_safe(template % substitutions)

        t = get_template("jcrop/jcrop_image_widget.html")
        substitutions.update({
            "JCROP_IMAGE_THUMBNAIL_DIMENSIONS": JCROP_IMAGE_THUMBNAIL_DIMENSIONS,
            "JCROP_IMAGE_WIDGET_DIMENSIONS": JCROP_IMAGE_WIDGET_DIMENSIONS,
        })
        c = Context(substitutions)
        return t.render(c)


class JCropImageField(models.ImageField):

    def __init__(self, *args, **kwargs):
        self.aspect_ratio = kwargs.pop('aspect_ratio', None)
        self.size = kwargs.pop('size', None)
        super(JCropImageField, self).__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        defaults = kwargs
        defaults.update({'form_class': forms.ImageField, 'widget': JCropAdminImageWidget(aspect_ratio=self.aspect_ratio, size=self.size)})
        return super(JCropImageField, self).formfield(**defaults)
