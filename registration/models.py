from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import RegexValidator, MinValueValidator
from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.template import Context
from django.template.defaultfilters import date as date_f
from django.template.loader import get_template
from django.utils.timezone import localtime
from django.utils.translation import ugettext_lazy as _
from collections import OrderedDict
import uuid
import smtplib


class Event(models.Model):
    """ Event for registration.

    Columns:
        url_name: the ID of the event used in URLs
        name: the name of the event
        text: text at begin of registration
        imprint: text at the bottom if the registration page
        registered: text after the successful registration
        email: e-mail address used as sender of automatic e-mails
        active: is the registration opened?
        admins: list of admins of this event, they can see and edit everything
        ask_shirt: ask for the t-shirt size during registration
        ask_vegetarian: ask, if the helper is vegetarian
        show_public_numbers: show the number of current and maximal helpers on
                             the registration page
    """
    url_name = models.CharField(max_length=200, unique=True,
                                validators=[RegexValidator('^[a-zA-Z0-9]+$')],
                                verbose_name=_("Name for URL"),
                                help_text=_("May contain the following chars: a-zA-Z0-9."))

    name = models.CharField(max_length=200, verbose_name=_("Event name"))

    text = models.TextField(blank=True,
                            verbose_name=_("Text before registration"),
                            help_text=_("Displayed as first text of the registration form."))

    imprint = models.TextField(blank=True, verbose_name=_('Imprint'),
                               help_text=_("Display at the bottom of the registration form."))

    registered = models.TextField(blank=True,
                                  verbose_name=_("Text after registration"),
                                  help_text=_("Displayed after registration."))

    email = models.EmailField(default='party@fs.tum.de',
                              verbose_name=_("E-Mail"),
                              help_text=_("Used as sender of e-mails."))

    active = models.BooleanField(default=False,
                                 verbose_name=_("Registration possible"))

    admins = models.ManyToManyField(User)

    ask_shirt = models.BooleanField(default=True,
                                    verbose_name=_("Ask for T-shirt size"))

    ask_vegetarian = models.BooleanField(default=True,
                                         verbose_name=_("Ask, if helper is vegetarian"))
    show_public_numbers = models.BooleanField(default=True,
                                              verbose_name=_("Show number of helpers on registration page"))

    def __str__(self):
        return self.name

    def is_admin(self, user):
        """ Check, if a user is admin of this event and returns a boolean.

        A superuser is also admin of an event.
        """
        return user.is_superuser or self.admins.filter(pk=user.pk).exists()

class Job(models.Model):
    """ A job that contains min. 1 shift.

    Columns:
        event: event of this job
        name: name of the job, e.g, Bierstand
        infection_instruction: is an instruction for the handling of food necessary?
        description: longer description of the job
    """
    event = models.ForeignKey(Event)
    name = models.CharField(max_length=200, verbose_name=_("Name"))
    infection_instruction = models.BooleanField(default=False, verbose_name=_("Instruction for the handling of food necessary"))
    description = models.TextField(blank=True, verbose_name=_("Description"))

    def __str__(self):
        return "%s (%s)" % (self.name, self.event)

    def shifts_by_day(self):
        """ Returns all shifts grouped sorted by day and sorted by time.

        The result is a dict with date objects as keys. Each item of the
        dictionary is a OrderedDict of shifts.
        """
        tmp_shifts = dict()

        # iterate over all shifts and group them by day
        # (itertools.groupby is strange...)
        for shift in self.shift_set.all():
            day = shift.begin.date()

            # add to list
            if day in tmp_shifts:
                tmp_shifts[day].append(shift)
            # or create begin list
            else:
                tmp_shifts[day] = [shift, ]

        # sort days
        ordered_shifts = OrderedDict(sorted(tmp_shifts.items(),
                                     key=lambda t: t[0]))

        # sort shifts
        for day in ordered_shifts:
            ordered_shifts[day] = sorted(ordered_shifts[day],
                                         key=lambda s : s.begin)

        return ordered_shifts


class Shift(models.Model):
    """ A shift of one job.

    Columns:
        job: job of this shift
        begin: begin of the shift
        end: end of the shift
        number: number of people
    """
    job = models.ForeignKey(Job)
    begin = models.DateTimeField(verbose_name=_("Begin"))
    end = models.DateTimeField(verbose_name=_("End"))
    number = models.IntegerField(default=0, verbose_name=_("Number of helpers"),
                                 validators=[MinValueValidator(0)])

    def __str__(self):
        return "%s %s (%s)" % (self.job.name, date_f(localtime(self.begin), 'DATETIME_FORMAT'), self.job.event)

    def time(self):
        """ Returns a string representation of the begin and end time.

        The begin contains the date and time, the end only the time.
        """
        return "%s, %s - %s" % (date_f(localtime(self.begin), 'DATE_FORMAT'),
                                date_f(localtime(self.begin), 'TIME_FORMAT'),
                                date_f(localtime(self.end), 'TIME_FORMAT'))

    def time_hours(self):
        """ Returns a string representation of the begin and end time.

        Only the time is used, the date is not shown.
        """
        return "%s - %s" % (date_f(localtime(self.begin), 'TIME_FORMAT'),
                            date_f(localtime(self.end), 'TIME_FORMAT'))

    def num_helpers(self):
        """ Returns the current number of helpers- """
        return self.helper_set.count()

    def is_full(self):
        """ Check if the shift is full and return a boolean. """
        return self.num_helpers() >= self.number

    def helpers_percent(self):
        """ Calculate the percentage of registered helpers and returns an int.

        If the maximal number of helpers for a shift is 0, 0 is returned.
        """
        if self.number == 0:
            return 0

        return int(round(self.num_helpers() / self.number * 100, 0))

@receiver(pre_delete, sender=Shift, dispatch_uid='shift_delete')
def shift_delete(sender, instance, using, **kwargs):
    """ Delete helpers without shifts, when a shift is deleted.

    This is a signal handler, that is called, when a shift is deleted. It
    deletes all helpers, that are only registered for this single shift.
    """
    # delete helpers, that have only one shift, when this shift is deleted
    for helper in instance.helper_set.all():
        if helper.shifts.count() == 1:
            helper.delete()

class Helper(models.Model):
    """ Helper in one or more shifts.

    Columns:
        shifts: all shifts of this person
        prename: the prename
        surname: the surname
        email: the e-mail address
        phone: phone number
        comment: optional comment
        shirt: t-shirt size (possible sizes are defined here)
        vegetarian: is the helper vegetarian?
        infection_instruction: status of the instruction for food handling
        timestamp: time of registration
    """

    SHIRT_S = 'S'
    SHIRT_M = 'M'
    SHIRT_L = 'L'
    SHIRT_XL = 'XL'
    SHIRT_XXL = 'XXL'
    SHIRT_S_GIRLY = 'S_GIRLY'
    SHIRT_M_GIRLY = 'M_GIRLY'
    SHIRT_L_GIRLY = 'L_GIRLY'
    SHIRT_XL_GIRLY = 'XL_GIRLY'

    SHIRT_CHOICES = (
        (SHIRT_S, 'S'),
        (SHIRT_M, 'M'),
        (SHIRT_L, 'L'),
        (SHIRT_XL, 'XL'),
        (SHIRT_XXL, 'XXL'),
        (SHIRT_S_GIRLY, 'S (girly)'),
        (SHIRT_M_GIRLY, 'M (girly)'),
        (SHIRT_L_GIRLY, 'L (girly)'),
        (SHIRT_XL_GIRLY, 'XL (girly)'),
    )

    INSTRUCTION_NO= "No"
    INSTRUCTION_YES = "Yes"
    INSTRUCTION_REFRESH = "Refresh"

    INSTRUCTION_CHOICES = (
        (INSTRUCTION_NO, _("I never got an instruction")),
        (INSTRUCTION_YES, _("I have a valid instruction")),
        (INSTRUCTION_REFRESH, _("I got a instruction by a doctor, it must be refreshed"))
    )

    INSTRUCTION_CHOICES_SHORT = (
        (INSTRUCTION_NO, _("No")),
        (INSTRUCTION_YES, _("Valid")),
        (INSTRUCTION_REFRESH, _("Refreshment"))
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    shifts = models.ManyToManyField(Shift)

    prename = models.CharField(max_length=200, verbose_name=_("Prename"))

    surname = models.CharField(max_length=200, verbose_name=_("Surname"))

    email = models.EmailField(verbose_name=_("E-Mail"))

    phone = models.CharField(max_length=200, verbose_name=_("Mobile phone"))

    comment = models.CharField(max_length=200, blank=True,
                               verbose_name=_("Comment"))

    shirt = models.CharField(max_length=20, choices=SHIRT_CHOICES,
                             default=SHIRT_S, verbose_name=_("T-shirt"))

    vegetarian = models.BooleanField(default=False,
                                     verbose_name=_("Vegetarian"),
                                     help_text=_("This helps us estimating the food for our helpers."))

    infection_instruction = models.CharField(max_length=20,
                                             choices=INSTRUCTION_CHOICES,
                                             blank=True,
                                             verbose_name=_("Instruction for the handling of food"))

    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return "%s %s" % (self.prename, self.surname)

    def get_infection_instruction_short(self):
        """ Returns the short description for the infection_instruction field. """
        for item in Helper.INSTRUCTION_CHOICES_SHORT:
            if item[0] == self.infection_instruction:
                return item[1]
        return ""

    def send_mail(self):
        """ Send a confirmation e-mail to the registered helper.

        This e-mail contains a list of the shifts, the helper registered for.
        """
        if self.shifts.count() == 0:
            return

        event = self.event

        subject_template = get_template('registration/mail_subject.txt')
        subject = subject_template.render({ 'event': event }).rstrip()

        text_template = get_template('registration/mail.txt')
        text = text_template.render({ 'user': self })

        send_mail(subject, text, event.email, [self.email],
                  fail_silently=False)

    @property
    def event(self):
        """ Returns the event, where this person helps us.

        If the helper is not registered for any shift, None is returned (this
        should not happen).
        """

        if self.shifts.count() == 0:
            return None

        return self.shifts.all()[0].job.event

    @property
    def full_name(self):
        return "%s %s" % (self.prename, self.surname)
