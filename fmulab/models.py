# https://realpython.com/django-social-forms-4/
from django.db import models

# Create your models here.
import datetime
from django.db import models
from django.utils import timezone
from django.contrib import admin
from django import forms


class FMUForm(forms.Form):
    exp_desc = forms.CharField(required=True,
                               widget=forms.widgets.Textarea(
                                   attrs={
                                       "placeholder": "describe your experiment ...",
                                       "class": "textarea",
                                   }
                               ),
                               label="Find FMU tutorial",
                               max_length=512)
    exp_title = forms.CharField(widget=forms.HiddenInput(), required=False)
    exp_num = forms.CharField(widget=forms.HiddenInput(), required=False)


class FMUModel(models.Model):
    # fields of the model
    exp_num = models.IntegerField()
    exp_title = models.TextField(max_length=100)
    exp_desc = models.TextField(max_length=512)

    # renames the instances of the model
    # with their title name
    def __str__(self):
        return self.exp_title
