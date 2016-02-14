from django.db import models
from django.utils.encoding import python_2_unicode_compatible
from django.utils.translation import ugettext_lazy as _

from .settings import BadgeSettings


@python_2_unicode_compatible
class BadgePermission(models.Model):
    badge_settings = models.ForeignKey(
        BadgeSettings,
    )

    name = models.CharField(
        max_length=200,
        verbose_name=_("Name"),
    )

    latex_name = models.CharField(
        max_length=200,
        verbose_name=_("Name for LaTeX template"),
        help_text=_("This name is used for the LaTeX template, the prefix "
                    "\"perm-\" is added."),
    )

    def __str__(self):
        return self.name